from datetime import datetime, timedelta, timezone

from apps.annotator.worker import heartbeat


def test_is_worker_alive_when_recent(tmp_path, monkeypatch):
    monkeypatch.setattr(
        heartbeat,
        "get_settings",
        lambda: type("S", (), {"data_dir": tmp_path})(),
    )
    (tmp_path / heartbeat.HEARTBEAT_FILE).write_text(datetime.now(timezone.utc).isoformat())
    assert heartbeat.is_worker_alive(max_age_sec=15.0)


def test_is_worker_dead_when_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(
        heartbeat,
        "get_settings",
        lambda: type("S", (), {"data_dir": tmp_path})(),
    )
    old = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    (tmp_path / heartbeat.HEARTBEAT_FILE).write_text(old)
    assert not heartbeat.is_worker_alive(max_age_sec=15.0)


def test_is_worker_dead_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        heartbeat,
        "get_settings",
        lambda: type("S", (), {"data_dir": tmp_path})(),
    )
    assert not heartbeat.is_worker_alive()
