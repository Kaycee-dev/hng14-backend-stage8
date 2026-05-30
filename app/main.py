from typing import Annotated, Any

from fastapi import Body, FastAPI, HTTPException, status

from app.event_store import EventStore

app = FastAPI()
event_store = EventStore()


@app.post("/events", status_code=status.HTTP_201_CREATED)
async def create_event(payload: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
    """Append a JSON object event and return the stored event."""
    return await event_store.append(payload)


@app.get("/events/{event_id}")
async def get_event(event_id: str) -> dict[str, Any]:
    """Return one event by id from the in-memory byte index."""
    event = event_store.get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    return event


@app.get("/stats")
async def get_stats() -> dict[str, int]:
    """Return the in-memory event count and on-disk log size."""
    bytes_written = event_store.log_path.stat().st_size if event_store.log_path.exists() else 0
    return {"total": len(event_store.index), "bytes": bytes_written}
