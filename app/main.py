from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Body, FastAPI, HTTPException, status

from app.event_store import EventStore

event_store = EventStore()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Recover the event index before the API starts serving requests."""
    event_store.recover()
    yield


app = FastAPI(lifespan=lifespan)


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
    return await event_store.stats()
