"""
The Review service's data: blinded study copies, participant sessions, ratings and quiz progress.
There is no model, strategy or score anywhere in this schema: the service never learns them.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .db import UTCDateTime, utcnow


class Base(DeclarativeBase):
    pass


class Study(Base):
    __tablename__ = "studies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # the Lab's study ID
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(16))  # expert | student | both
    seed: Mapped[int] = mapped_column(Integer)
    student_items: Mapped[int] = mapped_column(Integer)
    expert_code: Mapped[str] = mapped_column(String(32), unique=True)
    student_code: Mapped[str] = mapped_column(String(32), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    items: Mapped[list["StudyItem"]] = relationship(back_populates="study", order_by="StudyItem.position")


class StudyItem(Base):
    """A blinded copy of one question: a historical snapshot, it does not change if the Lab's copy does."""
    __tablename__ = "study_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[str] = mapped_column(ForeignKey("studies.id"), index=True)
    item_ref: Mapped[str] = mapped_column(String(36), unique=True)
    position: Mapped[int] = mapped_column(Integer)
    topic_label: Mapped[str] = mapped_column(String(300))
    domain: Mapped[str] = mapped_column(String(32))
    question: Mapped[str] = mapped_column(Text)
    options: Mapped[dict] = mapped_column(JSON)
    answer: Mapped[str] = mapped_column(String(1))
    study: Mapped[Study] = relationship(back_populates="items")


class Participant(Base):
    """An expert (identified by a pseudonym, so the review can be resumed) or an anonymous student."""
    __tablename__ = "participants"
    __table_args__ = (UniqueConstraint("study_id", "rater_name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    study_id: Mapped[str] = mapped_column(ForeignKey("studies.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # expert | student
    rater_name: Mapped[Optional[str]] = mapped_column(String(60))  # experts only; students stay anonymous
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    completion_code: Mapped[Optional[str]] = mapped_column(String(16))
    study: Mapped[Study] = relationship()


class ExpertRating(Base):
    __tablename__ = "expert_ratings"
    __table_args__ = (UniqueConstraint("participant_id", "item_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("study_items.id"))
    relevance: Mapped[int] = mapped_column(Integer)
    clarity: Mapped[int] = mapped_column(Integer)
    difficulty: Mapped[int] = mapped_column(Integer)
    distractors: Mapped[int] = mapped_column(Integer)
    key_correct: Mapped[str] = mapped_column(String(8))  # yes | no | unsure
    unusable: Mapped[bool] = mapped_column(Boolean, default=False)
    unusable_reason: Mapped[Optional[str]] = mapped_column(Text)
    comment: Mapped[Optional[str]] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class QuizStep(Base):
    """
    One question of one student's quiz, planned when the student joins. `permutation` maps the shown positions
    to the original labels ("CABD": shown A is original C), so answers are stored in original labels.
    """
    __tablename__ = "quiz_steps"
    __table_args__ = (UniqueConstraint("participant_id", "item_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("study_items.id"))
    position: Mapped[int] = mapped_column(Integer)
    permutation: Mapped[str] = mapped_column(String(4))
    served_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    answered_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    chosen_shown: Mapped[Optional[str]] = mapped_column(String(1))
    chosen_original: Mapped[Optional[str]] = mapped_column(String(1))
    correct: Mapped[Optional[bool]] = mapped_column(Boolean)
    time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    feedback_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    clarity: Mapped[Optional[int]] = mapped_column(Integer)
    helpfulness: Mapped[Optional[int]] = mapped_column(Integer)
    difficulty: Mapped[Optional[int]] = mapped_column(Integer)
    item: Mapped[StudyItem] = relationship()


class OutboxMessage(Base):
    """Events written in the same transaction as the rating or answer they announce (transactional outbox)."""
    __tablename__ = "outbox"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(String(36), unique=True)
    message_type: Mapped[str] = mapped_column(String(64))
    exchange: Mapped[str] = mapped_column(String(64))
    routing_key: Mapped[str] = mapped_column(String(128))
    body: Mapped[str] = mapped_column(Text)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    published_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(String(300))
