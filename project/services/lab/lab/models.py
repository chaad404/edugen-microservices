"""
The Lab's data. It is the only owner of experiments, jobs, questions and their scores, and the only place
that knows which model wrote which question (the Review service receives blinded copies).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .db import UTCDateTime, utcnow


class Base(DeclarativeBase):
    pass


class Topic(Base):
    __tablename__ = "topics"
    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[str] = mapped_column(String(64), unique=True)
    domain: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(300))
    source_text: Mapped[Optional[str]] = mapped_column(Text)  # None for thesis topics: their texts stay private
    origin: Mapped[str] = mapped_column(String(16))  # demo | thesis | custom
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Experiment(Base):
    __tablename__ = "experiments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    origin: Mapped[str] = mapped_column(String(16))  # live | thesis_import
    status: Mapped[str] = mapped_column(String(32))  # running | completed | completed_with_failures
    questions_per_job: Mapped[int] = mapped_column(Integer)
    models: Mapped[list] = mapped_column(JSON)
    strategies: Mapped[list] = mapped_column(JSON)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    jobs: Mapped[list["Job"]] = relationship(back_populates="experiment", order_by="Job.created_at")


class Job(Base):
    """One topic x model x strategy cell. Lifecycle: queued -> dispatched -> generated -> succeeded | failed."""
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), index=True)
    topic_pk: Mapped[int] = mapped_column(ForeignKey("topics.id"))
    model: Mapped[str] = mapped_column(String(64))
    strategy: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), index=True)
    provider: Mapped[Optional[str]] = mapped_column(String(32))
    requested_model_id: Mapped[Optional[str]] = mapped_column(String(120))
    returned_model_id: Mapped[Optional[str]] = mapped_column(String(120))
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    calls: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_seconds: Mapped[Optional[float]] = mapped_column(Float)
    strategy_status: Mapped[Optional[str]] = mapped_column(String(32))
    error_kind: Mapped[Optional[str]] = mapped_column(String(32))
    error: Mapped[Optional[str]] = mapped_column(Text)
    trace: Mapped[Optional[dict]] = mapped_column(JSON)
    evaluation_attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_evaluation_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    generated_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    experiment: Mapped[Experiment] = relationship(back_populates="jobs")
    topic: Mapped[Topic] = relationship()
    items: Mapped[list["Item"]] = relationship(back_populates="job", order_by="Item.position")


class Item(Base):
    """A generated question with its automatic scores (from the Evaluator, or recorded by the thesis)."""
    __tablename__ = "items"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    question: Mapped[str] = mapped_column(Text)
    options: Mapped[dict] = mapped_column(JSON)
    answer: Mapped[str] = mapped_column(String(1))
    evidence: Mapped[Optional[str]] = mapped_column(Text)
    metrics_source: Mapped[str] = mapped_column(String(16), default="evaluator")  # evaluator | thesis
    thesis_ref: Mapped[Optional[str]] = mapped_column(String(32))
    valid: Mapped[Optional[bool]] = mapped_column(Boolean)
    validation_notes: Mapped[Optional[str]] = mapped_column(String(300))
    alignment: Mapped[Optional[float]] = mapped_column(Float)
    alignment_lexical: Mapped[Optional[float]] = mapped_column(Float)
    grade: Mapped[Optional[float]] = mapped_column(Float)
    plausibility: Mapped[Optional[float]] = mapped_column(Float)
    plausibility_lexical: Mapped[Optional[float]] = mapped_column(Float)
    diversity: Mapped[Optional[float]] = mapped_column(Float)
    flags: Mapped[Optional[list]] = mapped_column(JSON)
    quality: Mapped[Optional[int]] = mapped_column(Integer)
    checked_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    job: Mapped[Job] = relationship(back_populates="items")


class OutboxMessage(Base):
    """Messages written in the same transaction as the change they announce (transactional outbox)."""
    __tablename__ = "outbox"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(String(36), unique=True)
    message_type: Mapped[str] = mapped_column(String(64))
    exchange: Mapped[str] = mapped_column(String(64))
    routing_key: Mapped[str] = mapped_column(String(128))
    body: Mapped[str] = mapped_column(Text)
    aggregate_id: Mapped[Optional[str]] = mapped_column(String(36))
    correlation_id: Mapped[Optional[str]] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    published_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(String(300))


class InboxMessage(Base):
    """IDs of consumed messages: a redelivered message is recognised and its effect is not repeated."""
    __tablename__ = "inbox"
    message_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    message_type: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Event(Base):
    """Progress log behind the Server-Sent Events stream; the ID is the SSE event ID used for resuming."""
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(80), index=True)
    type: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_keys"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    scope: Mapped[str] = mapped_column(String(50))
    request_hash: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int] = mapped_column(Integer)
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Study(Base):
    """A blind human evaluation of sampled questions, run by the Review service."""
    __tablename__ = "studies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(16))  # expert | student | both
    status: Mapped[str] = mapped_column(String(16))  # draft | open
    seed: Mapped[int] = mapped_column(Integer)
    per_cell: Mapped[int] = mapped_column(Integer)
    student_items: Mapped[int] = mapped_column(Integer)
    source_experiments: Mapped[list] = mapped_column(JSON)
    expert_code: Mapped[Optional[str]] = mapped_column(String(32))
    student_code: Mapped[Optional[str]] = mapped_column(String(32))
    publish_error: Mapped[Optional[str]] = mapped_column(String(300))
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    published_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    items: Mapped[list["StudyItem"]] = relationship(back_populates="study", order_by="StudyItem.position")


class StudyItem(Base):
    """item_ref is the only identifier the Review service sees; the mapping to the question stays here."""
    __tablename__ = "study_items"
    item_ref: Mapped[str] = mapped_column(String(36), primary_key=True)
    study_id: Mapped[str] = mapped_column(ForeignKey("studies.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    position: Mapped[int] = mapped_column(Integer)
    study: Mapped[Study] = relationship(back_populates="items")
    item: Mapped[Item] = relationship()


class HumanRating(Base):
    __tablename__ = "human_ratings"
    __table_args__ = (UniqueConstraint("study_id", "item_ref", "rater"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[str] = mapped_column(String(36), index=True)
    item_ref: Mapped[str] = mapped_column(String(36))
    rater: Mapped[str] = mapped_column(String(64))
    relevance: Mapped[int] = mapped_column(Integer)
    clarity: Mapped[int] = mapped_column(Integer)
    difficulty: Mapped[int] = mapped_column(Integer)
    distractors: Mapped[int] = mapped_column(Integer)
    key_correct: Mapped[str] = mapped_column(String(8))  # yes | no | unsure
    unusable: Mapped[bool] = mapped_column(Boolean, default=False)
    comment: Mapped[Optional[str]] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    submitted_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class QuizAnswer(Base):
    __tablename__ = "quiz_answers"
    __table_args__ = (UniqueConstraint("study_id", "item_ref", "participant"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[str] = mapped_column(String(36), index=True)
    item_ref: Mapped[str] = mapped_column(String(36))
    participant: Mapped[str] = mapped_column(String(64))
    chosen: Mapped[str] = mapped_column(String(1))  # the original option label, not the shuffled position
    correct: Mapped[bool] = mapped_column(Boolean)
    time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    submitted_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class QuizFeedback(Base):
    __tablename__ = "quiz_feedback"
    __table_args__ = (UniqueConstraint("study_id", "item_ref", "participant"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[str] = mapped_column(String(36), index=True)
    item_ref: Mapped[str] = mapped_column(String(36))
    participant: Mapped[str] = mapped_column(String(64))
    clarity: Mapped[int] = mapped_column(Integer)
    helpfulness: Mapped[int] = mapped_column(Integer)
    difficulty: Mapped[int] = mapped_column(Integer)
    submitted_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
