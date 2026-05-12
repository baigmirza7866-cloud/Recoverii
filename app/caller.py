"""
CALLER — makes outbound calls via Retell AI.

Flow:
  1. Fetch patient from DB
  2. POST to Retell API → Retell dials the patient
  3. Retell AI agent speaks the reminder using dynamic variables
     (patient name, appointment time are injected per-call)
  4. Patient verbally says "confirm" or "cancel"
  5. Retell agent triggers our /webhook/retell tool call
  6. We update DB status and cancel remaining scheduled calls
"""

import os
import httpx
from datetime import datetime
from app.database import get_connection

RETELL_API_KEY     = os.getenv("RETELL_API_KEY")
RETELL_AGENT_ID    = os.getenv("RETELL_AGENT_ID")    # created in Retell dashboard
RETELL_FROM_NUMBER = os.getenv("RETELL_FROM_NUMBER")  # your Retell phone number
APP_BASE_URL       = os.getenv("APP_BASE_URL")


def make_reminder_call(patient_id: int, trigger: str):
    """
    Makes one outbound call for a patient.
    `trigger` is '3_days', '1_day', or '1_hour'.
    """
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

    appt_dt = datetime.fromisoformat(patient["appointment_at"])
    appt_str = appt_dt.strftime("%A %B %d at %I:%M %p")

    # Log the attempt
    conn.execute("""
        INSERT INTO call_logs (patient_id, trigger, called_at)
        VALUES (?, ?, ?)
    """, (patient_id, trigger, datetime.now().isoformat()))
    conn.commit()

    try:
        response = httpx.post(
            "https://api.retellai.com/v2/create-phone-call",
            headers={
                "Authorization": f"Bearer {RETELL_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from_number": RETELL_FROM_NUMBER,
                "to_number": patient["phone"],
                "agent_id": RETELL_AGENT_ID,

                # These fill in the {{placeholders}} in your Retell agent prompt
                "retell_llm_dynamic_variables": {
                    "patient_name":     patient["name"],
                    "appointment_time": appt_str,
                    "patient_id":       str(patient_id),
                    "trigger":          trigger,
                },

                # Retell sends call events to this webhook
                "webhook_url": f"{APP_BASE_URL}/webhook/retell",
            },
            timeout=10,
        )
        response.raise_for_status()
        call_data = response.json()
        call_id = call_data.get("call_id")

        conn.execute("""
            UPDATE call_logs SET twilio_sid = ?
            WHERE patient_id = ? AND trigger = ?
            ORDER BY id DESC LIMIT 1
        """, (call_id, patient_id, trigger))
        conn.commit()

        print(f"Retell call placed to {patient['name']} ({patient['phone']}) — call_id: {call_id}")

    except Exception as e:
        print(f"Retell call failed for patient {patient_id}: {e}")
    finally:
        conn.close()
