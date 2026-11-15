from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Concept(Base):
    __tablename__ = "concepts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, default="objet")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="confirmed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Observation(Base):
    __tablename__ = "observations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    image_name: Mapped[str] = mapped_column(String(80), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    dhash: Mapped[str] = mapped_column(String(16), nullable=False)
    histogram: Mapped[list] = mapped_column(JSON, nullable=False)
    texture: Mapped[list] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="dashboard")
    candidate_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("concepts.id", ondelete="SET NULL"), nullable=True)
    candidate_label: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Example(Base):
    __tablename__ = "examples"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    concept_id: Mapped[str] = mapped_column(String(36), ForeignKey("concepts.id", ondelete="CASCADE"), index=True)
    observation_id: Mapped[str] = mapped_column(String(36), ForeignKey("observations.id", ondelete="CASCADE"), unique=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    dhash: Mapped[str] = mapped_column(String(16), nullable=False)
    histogram: Mapped[list] = mapped_column(JSON, nullable=False)
    texture: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Fact(Base):
    __tablename__ = "facts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    concept_id: Mapped[str] = mapped_column(String(36), ForeignKey("concepts.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="to_review")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DiagnosisRun(Base):
    """Snapshot of deterministic health checks; additive table, preserves V2 data."""
    __tablename__ = "diagnosis_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    findings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ImprovementProposal(Base):
    """Reviewed engineering suggestion. Never executable code."""
    __tablename__ = "improvement_proposals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(12), nullable=False)
    status: Mapped[str] = mapped_column(String(36), nullable=False, default="proposed", index=True)
    suggested_paths: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    acceptance_criteria: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EvolutionCycle(Base):
    """V3.3: immutable daily metrics snapshot and cautious same-dataset comparison."""
    __tablename__ = "evolution_cycles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    day_key: Mapped[str] = mapped_column(String(10), nullable=False, unique=True, index=True)
    code_revision: Mapped[str] = mapped_column(String(80), nullable=False, default="unversioned")
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    benchmark: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    trend: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    diagnosis_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ReleaseAssessment(Base):
    """Metadata-only approval dossier. Never an authorization to execute or deploy."""
    __tablename__ = "release_assessments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(String(36), ForeignKey("improvement_proposals.id"), index=True)
    base_revision: Mapped[str] = mapped_column(String(80), nullable=False)
    candidate_revision: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    verdict: Mapped[str] = mapped_column(String(30), nullable=False, default="insufficient_evidence")
    reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending_review")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
