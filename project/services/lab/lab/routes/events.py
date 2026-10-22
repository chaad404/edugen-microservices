"""
Progress of experiments and studies, two ways (course chapter 9):
- GET /events: polling with a cursor, for any HTTP client
- GET /events/stream: Server-Sent Events; resumes from Last-Event-ID (or ?after=) because events are stored
"""
import asyncio
import time
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from ..deps import get_session
from ..events import as_dict, events_after, sse_frame
from ..schemas import CHANNEL_PATTERN
from ..security import require_operator, verify_stream_ticket

router = APIRouter(tags=["events"])
POLL_SECONDS = 1.0
KEEPALIVE_SECONDS = 15.0


@router.get("/events", dependencies=[Depends(require_operator)], summary="Events of a channel after a cursor")
def list_events(channel: str = Query(pattern=CHANNEL_PATTERN), after: int = Query(0, ge=0),
                session: Session = Depends(get_session)):
    events = events_after(session, channel, after)
    return {"channel": channel, "events": [as_dict(e) for e in events], "last_id": events[-1].id if events else after}


@router.get("/events/stream", summary="Server-Sent Events of a channel (needs a stream ticket)")
async def stream(request: Request, channel: str = Query(pattern=CHANNEL_PATTERN), ticket: str = Query(max_length=2000),
                 after: int = Query(0, ge=0), last_event_id: Optional[str] = Header(default=None)):
    verify_stream_ticket(ticket, channel)
    start = int(last_event_id) if last_event_id and last_event_id.isdigit() else after
    session_factory = request.app.state.session_factory
    max_seconds = request.app.state.stream_max_seconds

    def fetch(cursor: int) -> list[tuple[int, str]]:
        with session_factory() as session:
            return [(e.id, sse_frame(e)) for e in events_after(session, channel, cursor)]

    async def frames():
        cursor, quiet, opened = start, 0.0, time.monotonic()
        yield "retry: 3000\n\n"
        # Bounded lifetime: the browser reconnects with Last-Event-ID, which also spreads long connections over instances
        while time.monotonic() - opened < max_seconds and not await request.is_disconnected():
            batch = await run_in_threadpool(fetch, cursor)
            for event_id, frame in batch:
                cursor = event_id
                yield frame
            quiet = 0.0 if batch else quiet + POLL_SECONDS
            if quiet >= KEEPALIVE_SECONDS:
                quiet = 0.0
                yield ": keep-alive\n\n"  # comment line: some proxies drop idle connections
            await asyncio.sleep(POLL_SECONDS)

    return StreamingResponse(frames(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
