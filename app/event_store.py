import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

IndexEntry = tuple[int, int]


class EventStore:
    """Append JSON events to a byte-indexed append-only log."""

    def __init__(self, log_path: str | Path = "events.log") -> None:
        self.log_path = Path(log_path)
        self.index: dict[str, IndexEntry] = {}
        self._lock = asyncio.Lock()

    async def append(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Append one event and update the in-memory byte index."""
        event = {
            **payload,
            "id": str(uuid.uuid4()),
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        serialized = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        encoded = serialized.encode("utf-8")

        async with self._lock:
            offset = self.log_path.stat().st_size if self.log_path.exists() else 0

            with self.log_path.open("ab") as log_file:
                log_file.write(encoded + b"\n")
                log_file.flush()

            self.index[event["id"]] = (offset, len(encoded))

        return event
