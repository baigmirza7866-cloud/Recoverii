"""
SCHEDULER — teaches you HOW the 3-call timing works.

When a patient is added, we schedule 3 jobs:
  - 3 days before appointment
  - 1 day before appointment
  - 1 hour before appointment

APScheduler runs in the background and fires each job at the right time.
Each job calls → caller.py → Twilio → patient's phone.
"""

from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "recoverii.db"

# Jobs are stored in the DB so they survive server restarts
jobstores = {
    "default": SQLAlchemyJobStore(url=f"sqlite:///{DB_PATH}")
}

scheduler = BackgroundScheduler(jobstores=jobstores)


def schedule_reminders(patient_id: int, appointment_at: datetime):
    """
    Called once when a patient is added.
    Creates 3 scheduled jobs — one for each reminder window.
    """
    from app.caller import make_reminder_call

    reminders = [
        ("3_days", appointment_at - timedelta(days=3)),
        ("1_day",  appointment_at - timedelta(days=1)),
        ("1_hour", appointment_at - timedelta(hours=1)),
    ]

    for trigger_name, run_at in reminders:
        # Only schedule if the reminder time is still in the future
        if run_at > datetime.now():
            scheduler.add_job(
                func=make_reminder_call,
                trigger="date",          # fire once at a specific time
                run_date=run_at,
                args=[patient_id, trigger_name],
                id=f"patient_{patient_id}_{trigger_name}",
                replace_existing=True,
            )
            print(f"  Scheduled {trigger_name} call for patient {patient_id} at {run_at}")
        else:
            print(f"  Skipped {trigger_name} for patient {patient_id} (time already passed)")


def cancel_reminders(patient_id: int):
    """Remove all pending jobs for a patient (e.g. if they cancel)."""
    for trigger in ["3_days", "1_day", "1_hour"]:
        job_id = f"patient_{patient_id}_{trigger}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            print(f"  Cancelled {trigger} job for patient {patient_id}")


def start():
    if not scheduler.running:
        scheduler.start()
        print("Scheduler started — watching for upcoming calls...")
