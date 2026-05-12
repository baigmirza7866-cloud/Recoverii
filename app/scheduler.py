from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "recoverii.db"

jobstores = {"default": SQLAlchemyJobStore(url=f"sqlite:///{DB_PATH}")}
scheduler = BackgroundScheduler(jobstores=jobstores)


def schedule_reminders(patient_id: int, appointment_at: datetime):
    from app.caller import make_reminder_call

    windows = [
        ("3_days", appointment_at - timedelta(days=3)),
        ("1_day",  appointment_at - timedelta(days=1)),
        ("1_hour", appointment_at - timedelta(hours=1)),
    ]

    for trigger, run_at in windows:
        if run_at > datetime.now():
            scheduler.add_job(
                func=make_reminder_call,
                trigger="date",
                run_date=run_at,
                args=[patient_id, trigger],
                id=f"patient_{patient_id}_{trigger}",
                replace_existing=True,
            )
            print(f"  Scheduled [{trigger}] call for patient {patient_id} at {run_at}")
        else:
            print(f"  Skipped [{trigger}] for patient {patient_id} — time already passed")


def cancel_reminders(patient_id: int):
    for trigger in ["3_days", "1_day", "1_hour"]:
        job_id = f"patient_{patient_id}_{trigger}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            print(f"  Cancelled [{trigger}] job for patient {patient_id}")


def start():
    if not scheduler.running:
        scheduler.start()
        print("Scheduler running — jobs will fire automatically")
