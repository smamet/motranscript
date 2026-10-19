from datetime import datetime, timezone

from apps.annotator.config import get_settings

HEARTBEAT_FILE = ".worker_heartbeat"


def touch_heartbeat() -> None:
    path = get_settings().data_dir / HEARTBEAT_FILE
    path.write_text(datetime.now(timezone.utc).isoformat())


def read_heartbeat() -> datetime | None:
    path = get_settings().data_dir / HEARTBEAT_FILE
    if not path.exists():
        return None
    try:
        ts = datetime.fromisoformat(path.read_text().strip())
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def is_worker_alive(max_age_sec: float = 15.0) -> bool:
    ts = read_heartbeat()
    if ts is None:
        return False
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    return age <= max_age_sec
