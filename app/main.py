"""
MAIN — FastAPI web server.

Endpoints:
  POST /patients              → add patient, triggers scheduler
  GET  /patients              → list all (dashboard data)
  POST /webhook/retell        → Retell sends call events here
  POST /webhook/confirm       → Retell agent tool call: patient confirmed
  POST /webhook/cancel        → Retell agent tool call: patient cancelled
  GET  /                      → HTML dashboard
"""

import os
from datetime import datetime
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.templating import Jinja2Templates

from app.database import init_db, get_connection
from app.scheduler import schedule_reminders, cancel_reminders, start as start_scheduler

app = FastAPI(title="Recoverii — Clinic Reminder Caller")
templates = Jinja2Templates(directory="templates")

CLINIC_ID      = os.getenv("CLINIC_ID", "demo_clinic")
RETELL_API_KEY = os.getenv("RETELL_API_KEY", "")


# ─── STARTUP ────────────────────────────────────────────────────────────────────

@app.on_event("startup")
def startup():
    init_db()
    start_scheduler()


# ─── PATIENT MANAGEMENT ─────────────────────────────────────────────────────────

@app.post("/patients")
def add_patient(
    name: str = Form(...),
    phone: str = Form(...),
    appointment_at: str = Form(...),
):
    """Add a patient and schedule their 3 reminder calls."""
    appt_dt = datetime.fromisoformat(appointment_at)

    conn = get_connection()
    cursor = conn.execute("""
        INSERT INTO patients (clinic_id, name, phone, appointment_at)
        VALUES (?, ?, ?, ?)
    """, (CLINIC_ID, name, phone, appt_dt.isoformat()))
    patient_id = cursor.lastrowid
    conn.commit()
    conn.close()

    schedule_reminders(patient_id, appt_dt)
    return {"patient_id": patient_id, "message": "Patient added and reminders scheduled"}


@app.get("/patients")
def list_patients():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM patients WHERE clinic_id = ? ORDER BY appointment_at", (CLINIC_ID,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── RETELL WEBHOOKS ────────────────────────────────────────────────────────────

@app.post("/webhook/retell")
async def retell_events(request: Request):
    """
    Retell posts call lifecycle events here:
      call_started, call_ended, call_analyzed

    We use call_ended to mark no-answer / failed calls.
    Confirmation/cancellation come via the tool-call webhooks below.
    """
    # Optional: verify the request is from Retell
    # retell_signature = request.headers.get("x-retell-signature")
    # verify_retell_signature(retell_signature, await request.body(), RETELL_API_KEY)

    payload = await request.json()
    event   = payload.get("event")
    call    = payload.get("data", {})

    call_id    = call.get("call_id")
    to_number  = call.get("to_number")
    call_status = call.get("end_call_reason") or call.get("call_status")

    print(f"Retell event: {event} | call_id: {call_id} | status: {call_status}")

    if event == "call_ended":
        # Find the call log by call_id (stored in twilio_sid column)
        conn = get_connection()
        log = conn.execute(
            "SELECT * FROM call_logs WHERE twilio_sid = ?", (call_id,)
        ).fetchone()

        if log and log["outcome"] == "pending":
            # Map Retell end reasons to our outcomes
            outcome_map = {
                "user_hangup":      "no_answer",
                "agent_hangup":     "no_answer",
                "call_transfer":    "no_answer",
                "voicemail_reached":"no_answer",
                "no_answer":        "no_answer",
                "error_inbound_webhook": "failed",
            }
            outcome = outcome_map.get(call_status, "no_answer")
            conn.execute(
                "UPDATE call_logs SET outcome = ? WHERE twilio_sid = ?",
                (outcome, call_id)
            )
            conn.commit()
        conn.close()

    return JSONResponse({"status": "ok"})


@app.post("/webhook/confirm")
async def patient_confirmed(request: Request):
    """
    Called by the Retell agent as a tool/function when patient says 'confirm'.
    In Retell dashboard, add a custom tool that POSTs to this URL.
    Tool parameters: patient_id (string)
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
    print(f"Patient {patient_id} confirmed via Retell agent")

    # Retell expects a response — the agent uses this to continue the conversation
    return JSONResponse({"message": "confirmed"})


@app.post("/webhook/cancel")
async def patient_cancelled(request: Request):
    """
    Called by the Retell agent as a tool/function when patient says 'cancel'.
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
    print(f"Patient {patient_id} cancelled via Retell agent")

    return JSONResponse({"message": "cancelled"})


# ─── DASHBOARD ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    conn = get_connection()
    patients = conn.execute("""
        SELECT p.*,
               COUNT(cl.id) as calls_made
        FROM patients p
        LEFT JOIN call_logs cl ON cl.patient_id = p.id
        WHERE p.clinic_id = ?
        GROUP BY p.id
        ORDER BY p.appointment_at
    """, (CLINIC_ID,)).fetchall()
    conn.close()

    return templates.TemplateResponse("dashboard.html", {
        "request":  request,
        "patients": [dict(p) for p in patients],
    })
