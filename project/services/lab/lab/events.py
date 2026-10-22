"""
Progress events behind Server-Sent Events (course chapter 9.3). Events are stored, so a client that
reconnects with Last-Event-ID (or ?after=) receives what it missed instead of losing it.
"""
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Event


def record_event(session: Session, channel: str, type_: str, data: dict) -> Event:
    event = Event(channel=channel, type=type_, data=data)
    session.add(event)
    return event


def events_after(session: Session, channel: str, after: int, limit: int = 200) -> list[Event]:
    return list(session.scalars(select(Event).where(Event.channel == channel, Event.id > after)
                                .order_by(Event.id).limit(limit)))


def as_dict(event: Event) -> dict:
    return {"id": event.id, "type": event.type, "data": event.data, "created_at": event.created_at.isoformat()}


def sse_frame(event: Event) -> str:
    return f"id: {event.id}\nevent: {event.type}\ndata: {json.dumps(event.data)}\n\n"
