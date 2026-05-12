import os
import csv
import io
from datetime import datetime
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.database import init_db, get_connection
from app.scheduler import schedule_reminders, cancel_reminders, start as start_scheduler

app = FastAPI(title="Recoverii — Clinic Reminder Caller")
templates = Jinja2Templates(directory="templates")

CLINIC_ID = os.getenv("CLINIC_ID", "demo_clinic")


@app.on_event("startup")
def startup():
    init_db()
    start_scheduler()


# ─── PATIENTS ───────────────────────────────────────────────────────────────────

@app.post("/patients")
def add_patient(
    name: str = Form(...),
    phone: str = Form(...),
    appointment_at: str = Form(...),
):
    appt_dt = datetime.fromisoformat(appointment_at)
    conn    = get_connection()
    cursor  = conn.execute(
        "INSERT INTO patients (clinic_id, name, phone, appointment_at) VALUES (?, ?, ?, ?)",
        (CLINIC_ID, name, phone, appt_dt.isoformat()),
    )
    patient_id = cursor.lastrowid
    conn.commit()
    conn.close()

    schedule_reminders(patient_id, appt_dt)
    return RedirectResponse(url="/", status_code=303)


@app.post("/patients/import")
async def import_csv(file: UploadFile = File(...)):
    """
    Bulk import patients from a CSV file.
    Expected columns: name, phone, appointment_at
    appointment_at format: YYYY-MM-DD HH:MM  (e.g. 2026-06-01 09:30)
    """
    content = await file.read()
    reader  = csv.DictReader(io.StringIO(content.decode("utf-8")))

    imported = 0
    errors   = []

    conn = get_connection()
    for i, row in enumerate(reader, start=2):  # row 1 is header
        try:
            name    = row["name"].strip()
            phone   = row["phone"].strip()
            appt_dt = datetime.fromisoformat(row["appointment_at"].strip())

            cursor = conn.execute(
                "INSERT INTO patients (clinic_id, name, phone, appointment_at) VALUES (?, ?, ?, ?)",
                (CLINIC_ID, name, phone, appt_dt.isoformat()),
            )
            patient_id = cursor.lastrowid
            conn.commit()

            schedule_reminders(patient_id, appt_dt)
            imported += 1

        except Exception as e:
            errors.append(f"Row {i}: {e}")

    conn.close()

    if errors:
        return JSONResponse({"imported": imported, "errors": errors}, status_code=207)

    return RedirectResponse(url="/", status_code=303)


@app.delete("/patients/{patient_id}")
def delete_patient(patient_id: int):
    cancel_reminders(patient_id)
    conn = get_connection()
    conn.execute("DELETE FROM call_logs WHERE patient_id = ?", (patient_id,))
    conn.execute("DELETE FROM patients WHERE id = ? AND clinic_id = ?", (patient_id, CLINIC_ID))
    conn.commit()
    conn.close()
    return JSONResponse({"status": "deleted"})


# ─── RETELL WEBHOOKS ────────────────────────────────────────────────────────────

@app.post("/webhook/retell")
async def retell_events(request: Request):
    """Receives call lifecycle events from Retell (call_started, call_ended, call_analyzed)."""
    payload     = await request.json()
    event       = payload.get("event")
    call        = payload.get("data", {})
    call_id     = call.get("call_id")
    end_reason  = call.get("end_call_reason") or call.get("call_status", "")

    print(f"Retell event={event} call_id={call_id} reason={end_reason}")

    if event == "call_ended":
        outcome_map = {
            "user_hangup":           "no_answer",
            "agent_hangup":          "no_answer",
            "voicemail_reached":     "no_answer",
            "no_answer":             "no_answer",
            "call_transfer":         "no_answer",
            "error_inbound_webhook": "failed",
        }
        outcome = outcome_map.get(end_reason, "no_answer")

        conn = get_connection()
        log  = conn.execute(
            "SELECT * FROM call_logs WHERE call_id = ?", (call_id,)
        ).fetchone()

        if log and log["outcome"] == "pending":
            conn.execute(
                "UPDATE call_logs SET outcome = ? WHERE call_id = ?", (outcome, call_id)
            )
            conn.commit()
        conn.close()

    return JSONResponse({"status": "ok"})


@app.post("/webhook/confirm")
async def patient_confirmed(request: Request):
    """
    Retell agent calls this tool when the patient says they want to confirm.
    Set this up as a Custom Tool in the Retell dashboard.
    Required tool parameter: patient_id (string)
    """
    payload    = await request.json()
    patient_id = int(payload.get("patient_id", 0))

    if not patient_id:
        return JSONResponse({"error": "missing patient_id"}, status_code=400)

    conn = get_connection()
    conn.execute("UPDATE patients SET status = 'confirmed' WHERE id = ?", (patient_id,))
    conn.execute("""
        UPDATE call_logs SET outcome = 'confirmed'
        WHERE patient_id = ? AND outcome = 'pending'
        ORDER BY id DESC LIMIT 1
    """, (patient_id,))
    conn.commit()
    conn.close()

    cancel_reminders(patient_id)
    print(f"Patient {patient_id} CONFIRMED")

    return JSONResponse({"message": "Appointment confirmed. Thank you!"})


@app.post("/webhook/cancel")
async def patient_cancelled(request: Request):
    """
    Retell agent calls this tool when the patient says they want to cancel.
    Required tool parameter: patient_id (string)
    """
    payload    = await request.json()
    patient_id = int(payload.get("patient_id", 0))

    if not patient_id:
        return JSONResponse({"error": "missing patient_id"}, status_code=400)

    conn = get_connection()
    conn.execute("UPDATE patients SET status = 'cancelled' WHERE id = ?", (patient_id,))
    conn.execute("""
        UPDATE call_logs SET outcome = 'cancelled'
        WHERE patient_id = ? AND outcome = 'pending'
        ORDER BY id DESC LIMIT 1
    """, (patient_id,))
    conn.commit()
    conn.close()

    cancel_reminders(patient_id)
    print(f"Patient {patient_id} CANCELLED")

    return JSONResponse({"message": "Appointment cancelled."})


# ─── DASHBOARD ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    conn = get_connection()
    patients = conn.execute("""
        SELECT p.*,
               COUNT(cl.id)                                        AS calls_made,
               SUM(CASE WHEN cl.outcome = 'confirmed'  THEN 1 END) AS confirmed_calls,
               SUM(CASE WHEN cl.outcome = 'no_answer'  THEN 1 END) AS missed_calls
        FROM   patients p
        LEFT JOIN call_logs cl ON cl.patient_id = p.id
        WHERE  p.clinic_id = ?
        GROUP  BY p.id
        ORDER  BY p.appointment_at
    """, (CLINIC_ID,)).fetchall()
    conn.close()

    return templates.TemplateResponse("dashboard.html", {
        "request":  request,
        "patients": [dict(p) for p in patients],
    })
