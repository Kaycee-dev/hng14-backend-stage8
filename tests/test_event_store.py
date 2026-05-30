import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app import main as main_module
from app.event_store import EventStore


def test_post_event_returns_201_with_id_and_created_at(tmp_path, monkeypatch) -> None:
    store = EventStore(tmp_path / "events.log")
    monkeypatch.setattr(main_module, "event_store", store)

    with TestClient(main_module.app) as client:
        response = client.post("/events", json={"x": 1})

    assert response.status_code == 201
    body = response.json()
    assert body["x"] == 1
    uuid.UUID(body["id"])

    created_at = datetime.fromisoformat(body["createdAt"])
    assert created_at.tzinfo is not None
    assert created_at.utcoffset() == timezone.utc.utcoffset(created_at)


def test_append_writes_one_json_line_to_events_log(tmp_path) -> None:
    store = EventStore(tmp_path / "events.log")

    event = asyncio.run(store.append({"likerName": "Chidé 🎉"}))

    raw = (tmp_path / "events.log").read_bytes()
    assert raw.endswith(b"\n")
    assert raw.count(b"\n") == 1
    assert json.loads(raw[:-1].decode("utf-8")) == event


def test_index_entry_has_correct_offset_and_byte_length(tmp_path) -> None:
    store = EventStore(tmp_path / "events.log")

    event = asyncio.run(store.append({"likerName": "Chidé 🎉"}))
    raw = (tmp_path / "events.log").read_bytes()
    json_bytes = raw[:-1]
    json_text = json_bytes.decode("utf-8")

    assert store.index[event["id"]] == (0, len(json_bytes))
    assert len(json_bytes) == len(json_text.encode("utf-8"))
    assert len(json_bytes) != len(json_text)
