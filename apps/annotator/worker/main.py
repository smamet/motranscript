import threading
import time

from apps.annotator.config import get_settings
from apps.annotator.db.session import SessionLocal
from apps.annotator.pipeline.transcription_job import TranscriptionJob, recover_stale_jobs
from apps.annotator.worker.heartbeat import touch_heartbeat

HEARTBEAT_INTERVAL_SEC = 10.0


def _heartbeat_loop(stop: threading.Event, interval: float) -> None:
    while not stop.wait(interval):
        touch_heartbeat()


def run() -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        n = recover_stale_jobs(db)
        if n:
            print(f"Recovered {n} job(s) interrupted by restart — will resume from queue")
    finally:
        db.close()

    stop_heartbeat = threading.Event()
    heartbeat_thread = threading.Thread(
        target=_heartbeat_loop,
        args=(stop_heartbeat, HEARTBEAT_INTERVAL_SEC),
        name="worker-heartbeat",
        daemon=True,
    )
    heartbeat_thread.start()
    touch_heartbeat()

    print("MoTranscript worker started (pending jobs resume on restart)")
    try:
        while True:
            touch_heartbeat()
            db = SessionLocal()
            try:
                runner = TranscriptionJob(db)
                processed = runner.run_pending_jobs()
            finally:
                db.close()
            if not processed:
                time.sleep(settings.worker_poll_interval)
    finally:
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=1.0)


if __name__ == "__main__":
    run()
