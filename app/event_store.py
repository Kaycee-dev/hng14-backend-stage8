import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

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

    def get(self, event_id: str) -> dict[str, Any] | None:
        """Read one event directly from its indexed byte offset."""
        entry = self.index.get(event_id)
        if entry is None:
            return None

        offset, length = entry
        with self.log_path.open("rb") as log_file:
            log_file.seek(offset)
            raw = log_file.read(length)

        return cast(dict[str, Any], json.loads(raw.decode("utf-8")))

    async def stats(self) -> dict[str, int]:
        """Return an atomic snapshot of event count and log byte size."""
        async with self._lock:
            bytes_written = self.log_path.stat().st_size if self.log_path.exists() else 0
            return {"total": len(self.index), "bytes": bytes_written}

    def recover(self) -> int:
        """Rebuild the in-memory byte index from the append-only log."""
        self.index.clear()

        if not self.log_path.exists():
            print("Recovered 0 events from events.log", flush=True)
            return 0

        recovered_count = 0
        offset = 0

        with self.log_path.open("rb") as log_file:
            raw_line = log_file.readline()
            while raw_line:
                line_len = len(raw_line)
                content = raw_line[:-1] if raw_line.endswith(b"\n") else raw_line
                length = len(content)
                next_line = log_file.readline()
                is_last_line = not next_line

                if length == 0:
                    offset += line_len
                    raw_line = next_line
                    continue

                try:
                    event = json.loads(content.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    if is_last_line:
                        print(
                            "Skipped 1 incomplete trailing record in events.log",
                            file=sys.stderr,
                            flush=True,
                        )
                        break
                    raise

                self.index[event["id"]] = (offset, length)
                recovered_count += 1
                offset += line_len
                raw_line = next_line

        print(f"Recovered {recovered_count} events from events.log", flush=True)
        return recovered_count
