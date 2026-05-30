from typing import Annotated, Any

from fastapi import Body, FastAPI, status

from app.event_store import EventStore

app = FastAPI()
event_store = EventStore()


@app.post("/events", status_code=status.HTTP_201_CREATED)
async def create_event(payload: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
    """Append a JSON object event and return the stored event."""
    return await event_store.append(payload)
