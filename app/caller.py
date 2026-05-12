import os
import httpx
from datetime import datetime
from app.database import get_connection


def make_reminder_call(patient_id: int, trigger: str):
    """
    Makes one outbound Retell AI call for a patient.
    trigger is '3_days', '1_day', or '1_hour'.
    """
    # Read env here (not at module level) so .env is always loaded first
    api_key     = os.getenv("RETELL_API_KEY")
    agent_id    = os.getenv("RETELL_AGENT_ID")
    from_number = os.getenv("RETELL_FROM_NUMBER")
    base_url    = os.getenv("APP_BASE_URL")

    conn = get_connection()
    patient = conn.execute(
        "SELECT * FROM patients WHERE id = ?", (patient_id,)
    ).fetchone()

    if not patient:
        print(f"Patient {patient_id} not found — skipping call")
        conn.close()
        return

    if patient["status"] in ("confirmed", "cancelled"):
        print(f"Patient {patient_id} already {patient['status']} — skipping {trigger} call")
        conn.close()
        return

    appt_dt  = datetime.fromisoformat(patient["appointment_at"])
    appt_str = appt_dt.strftime("%A %B %d at %I:%M %p")

    conn.execute("""
        INSERT INTO call_logs (patient_id, trigger, called_at)
        VALUES (?, ?, ?)
    """, (patient_id, trigger, datetime.now().isoformat()))
    conn.commit()

    try:
        response = httpx.post(
            "https://api.retellai.com/v2/create-phone-call",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from_number": from_number,
                "to_number":   patient["phone"],
                "agent_id":    agent_id,
                "retell_llm_dynamic_variables": {
                    "patient_name":     patient["name"],
                    "appointment_time": appt_str,
                    "patient_id":       str(patient_id),
                    "trigger":          trigger,
                },
                "webhook_url": f"{base_url}/webhook/retell",
            },
            timeout=10,
        )
        response.raise_for_status()
        retell_call_id = response.json().get("call_id")

        conn.execute("""
            UPDATE call_logs SET call_id = ?
            WHERE patient_id = ? AND trigger = ?
            ORDER BY id DESC LIMIT 1
        """, (retell_call_id, patient_id, trigger))
        conn.commit()

        print(f"Call placed → {patient['name']} ({patient['phone']}) [{trigger}] call_id={retell_call_id}")

    except Exception as e:
        print(f"Retell call failed for patient {patient_id}: {e}")
    finally:
        conn.close()
