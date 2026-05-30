import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

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


def test_get_existing_event_returns_200_with_original_payload(tmp_path, monkeypatch) -> None:
    store = EventStore(tmp_path / "events.log")
    stored_event = asyncio.run(store.append({"x": 1}))
    monkeypatch.setattr(main_module, "event_store", store)

    with TestClient(main_module.app) as client:
        response = client.get(f"/events/{stored_event['id']}")

    assert response.status_code == 200
    assert response.json() == stored_event


def test_get_unknown_id_returns_404(tmp_path, monkeypatch) -> None:
    store = EventStore(tmp_path / "events.log")
    monkeypatch.setattr(main_module, "event_store", store)

    with TestClient(main_module.app) as client:
        response = client.get("/events/does-not-exist")

    assert response.status_code == 404


def test_unicode_payload_round_trips_byte_for_byte(tmp_path, monkeypatch) -> None:
    store = EventStore(tmp_path / "events.log")
    stored_event = asyncio.run(store.append({"likerName": "Chidé 🎉"}))
    monkeypatch.setattr(main_module, "event_store", store)

    with TestClient(main_module.app) as client:
        response = client.get(f"/events/{stored_event['id']}")

    assert response.status_code == 200
    assert response.json()["likerName"] == stored_event["likerName"]


def test_stats_returns_total_and_bytes(tmp_path, monkeypatch) -> None:
    log_path = tmp_path / "events.log"
    store = EventStore(log_path)

    async def append_events() -> None:
        await store.append({"x": 1})
        await store.append({"likerName": "Chidé 🎉"})

    asyncio.run(append_events())
    monkeypatch.setattr(main_module, "event_store", store)

    with TestClient(main_module.app) as client:
        response = client.get("/stats")

    assert response.status_code == 200
    assert response.json() == {
        "total": len(store.index),
        "bytes": os.path.getsize(log_path),
    }


def test_stats_with_empty_store_returns_zero_zero(tmp_path, monkeypatch) -> None:
    store = EventStore(tmp_path / "events.log")
    monkeypatch.setattr(main_module, "event_store", store)

    with TestClient(main_module.app) as client:
        response = client.get("/stats")

    assert response.status_code == 200
    assert response.json() == {"total": 0, "bytes": 0}


def test_recovery_rebuilds_index_for_existing_events(tmp_path) -> None:
    log_path = tmp_path / "events.log"
    store = EventStore(log_path)

    async def append_events() -> None:
        await store.append({"x": 1})
        await store.append({"likerName": "Chidé 🎉"})
        await store.append({"x": 3})

    asyncio.run(append_events())
    original_index = dict(store.index)

    recovered_store = EventStore(log_path)
    recovered_count = recovered_store.recover()

    assert recovered_count == len(original_index)
    for event_id, entry in original_index.items():
        assert recovered_store.index[event_id] == entry


def test_recovery_handles_missing_trailing_newline(tmp_path) -> None:
    log_path = tmp_path / "events.log"
    store = EventStore(log_path)

    async def append_events() -> list[dict[str, Any]]:
        return [
            await store.append({"x": 1}),
            await store.append({"likerName": "Chidé 🎉"}),
        ]

    stored_events = asyncio.run(append_events())
    raw = log_path.read_bytes()
    log_path.write_bytes(raw[:-1])

    recovered_store = EventStore(log_path)
    recovered_count = recovered_store.recover()

    assert recovered_count == len(stored_events)
    assert recovered_store.get(stored_events[-1]["id"]) == stored_events[-1]


def test_recovery_skips_corrupt_trailing_line(tmp_path, capsys) -> None:
    log_path = tmp_path / "events.log"
    store = EventStore(log_path)

    async def append_events() -> list[dict[str, Any]]:
        return [
            await store.append({"x": 1}),
            await store.append({"likerName": "Chidé 🎉"}),
        ]

    stored_events = asyncio.run(append_events())
    with log_path.open("ab") as log_file:
        log_file.write(b'{"x":3')

    recovered_store = EventStore(log_path)
    recovered_count = recovered_store.recover()

    captured = capsys.readouterr()
    assert recovered_count == 2
    assert captured.out.strip() == "Recovered 2 events from events.log"
    assert captured.err.strip() == "Skipped 1 incomplete trailing record in events.log"
    for stored_event in stored_events:
        assert recovered_store.get(stored_event["id"]) == stored_event


def test_recovery_logs_correct_count(tmp_path, capsys) -> None:
    log_path = tmp_path / "events.log"
    store = EventStore(log_path)

    async def append_events() -> None:
        await store.append({"x": 1})
        await store.append({"likerName": "Chidé 🎉"})

    asyncio.run(append_events())

    recovered_store = EventStore(log_path)
    recovered_store.recover()

    captured = capsys.readouterr()
    assert captured.out.strip() == "Recovered 2 events from events.log"


def test_full_restart_round_trip(tmp_path) -> None:
    log_path = tmp_path / "events.log"
    store = EventStore(log_path)

    async def append_events() -> list[dict[str, Any]]:
        return [
            await store.append({"x": 1}),
            await store.append({"likerName": "Chidé 🎉"}),
            await store.append({"x": 3}),
        ]

    stored_events = asyncio.run(append_events())

    recovered_store = EventStore(log_path)
    recovered_count = recovered_store.recover()

    assert recovered_count == len(stored_events)
    for stored_event in stored_events:
        assert recovered_store.get(stored_event["id"]) == stored_event
