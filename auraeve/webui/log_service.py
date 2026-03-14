from __future__ import annotations

import asyncio
import csv
import io
import json
from datetime import datetime
from typing import Any, AsyncIterator

from auraeve.observability import get_observability


class LogWebService:
    def __init__(self) -> None:
        self._obs = get_observability()

    def tail(self, cursor: int | None, limit: int, max_bytes: int) -> dict[str, Any]:
        return self._obs.tail(cursor=cursor, limit=limit, max_bytes=max_bytes)

    def search(
        self,
        *,
        levels: list[str] | None = None,
        subsystems: list[str] | None = None,
        kinds: list[str] | None = None,
        text: str | None = None,
        session_key: str | None = None,
        run_id: str | None = None,
        channel: str | None = None,
        ts_from: str | None = None,
        ts_to: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> dict[str, Any]:
        return self._obs.search(
            levels=levels,
            subsystems=subsystems,
            kinds=kinds,
            text=text,
            session_key=session_key,
            run_id=run_id,
            channel=channel,
            ts_from_ms=self._to_ms(ts_from),
            ts_to_ms=self._to_ms(ts_to),
            limit=limit,
            offset=offset,
        )

    def stats(self, ts_from: str | None = None, ts_to: str | None = None) -> dict[str, Any]:
        return self._obs.stats(ts_from_ms=self._to_ms(ts_from), ts_to_ms=self._to_ms(ts_to))

    def context(self, event_id: str, before: int = 20, after: int = 20) -> dict[str, Any]:
        return self._obs.context(event_id=event_id, before=before, after=after)

    def export(
        self,
        *,
        export_format: str,
        levels: list[str] | None = None,
        subsystems: list[str] | None = None,
        kinds: list[str] | None = None,
        text: str | None = None,
        session_key: str | None = None,
        run_id: str | None = None,
        channel: str | None = None,
        ts_from: str | None = None,
        ts_to: str | None = None,
        limit: int = 5000,
    ) -> tuple[str, str, str]:
        events = self._obs.export_events(
            levels=levels,
            subsystems=subsystems,
            kinds=kinds,
            text=text,
            session_key=session_key,
            run_id=run_id,
            channel=channel,
            ts_from_ms=self._to_ms(ts_from),
            ts_to_ms=self._to_ms(ts_to),
            limit=limit,
        )
        fmt = export_format.strip().lower()
        if fmt == "csv":
            return self._as_csv(events)
        return self._as_jsonl(events)

    async def subscribe(
        self,
        *,
        levels: list[str] | None = None,
        subsystems: list[str] | None = None,
        text: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        sub_id, queue = self._obs.subscribe(levels=levels, subsystems=subsystems, text=text)
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15.0)
                except TimeoutError:
                    yield {"type": "ping"}
                    continue
                yield {"type": "event", "event": item}
        finally:
            self._obs.unsubscribe(sub_id)

    @staticmethod
    def _to_ms(value: str | None) -> int | None:
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value)
            return int(dt.timestamp() * 1000)
        except ValueError:
            return None

    @staticmethod
    def _as_jsonl(events: list[dict[str, Any]]) -> tuple[str, str, str]:
        payload = "\n".join(json.dumps(item, ensure_ascii=False) for item in events)
        name = f"auraeve-logs-{datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl"
        return payload, "application/x-ndjson; charset=utf-8", name

    @staticmethod
    def _as_csv(events: list[dict[str, Any]]) -> tuple[str, str, str]:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ts", "level", "kind", "subsystem", "sessionKey", "runId", "channel", "message", "attrs"])
        for item in events:
            writer.writerow(
                [
                    item.get("ts", ""),
                    item.get("level", ""),
                    item.get("kind", ""),
                    item.get("subsystem", ""),
                    item.get("sessionKey", ""),
                    item.get("runId", ""),
                    item.get("channel", ""),
                    item.get("message", ""),
                    json.dumps(item.get("attrs", {}), ensure_ascii=False),
                ]
            )
        name = f"auraeve-logs-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
        return output.getvalue(), "text/csv; charset=utf-8", name
