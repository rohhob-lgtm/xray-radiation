"""SQLAlchemy ORM models for the X-Ray Academy database."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    String, Text, Integer, DateTime, ForeignKey,
    Boolean, JSON, LargeBinary, Float, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship, Mapped, mapped_column

from .base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)  # Replit user ID
    username: Mapped[str] = mapped_column(String(256), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=True)
    profile_image: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    conversations: Mapped[list[Conversation]] = relationship(
        "Conversation", back_populates="user", cascade="all, delete-orphan"
    )
    linkedin_posts: Mapped[list[LinkedInPost]] = relationship(
        "LinkedInPost", back_populates="user", cascade="all, delete-orphan"
    )
    xray_analyses: Mapped[list[XrayAnalysis]] = relationship(
        "XrayAnalysis", back_populates="user", cascade="all, delete-orphan"
    )
    rag_documents: Mapped[list[RagDocument]] = relationship(
        "RagDocument", back_populates="user", cascade="all, delete-orphan"
    )
    research_outputs: Mapped[list[ResearchOutput]] = relationship(
        "ResearchOutput", back_populates="user", cascade="all, delete-orphan"
    )
    memory_items: Mapped[list["MemoryItem"]] = relationship(
        "MemoryItem", back_populates="user", cascade="all, delete-orphan"
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Isolates anonymous (not-logged-in) conversations per browser session —
    # anonymous visitors are never scoped by the shared user_id=NULL bucket.
    # Mutually exclusive with user_id: exactly one of the two is set.
    anon_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="New Conversation")
    # Active workspace attached to this conversation, if any — lets follow-up
    # chat turns reuse the uploaded workspace without re-uploading.
    workspace_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    user: Mapped[User | None] = relationship("User", back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(
        "Message", back_populates="conversation",
        cascade="all, delete-orphan", order_by="Message.created_at"
    )
    summaries: Mapped[list["ConversationSummary"]] = relationship(
        "ConversationSummary", back_populates="conversation",
        cascade="all, delete-orphan", order_by="ConversationSummary.created_at"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    conversation: Mapped[Conversation] = relationship("Conversation", back_populates="messages")


class LinkedInPost(Base):
    __tablename__ = "linkedin_posts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    topic: Mapped[str] = mapped_column(String(512), nullable=False)
    tone: Mapped[str] = mapped_column(String(64), nullable=False, default="professional")
    length: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    hashtags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped[User | None] = relationship("User", back_populates="linkedin_posts")


class XrayAnalysis(Base):
    __tablename__ = "xray_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    scanner_type: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    findings: Mapped[str] = mapped_column(Text, nullable=False)
    threat_level: Mapped[str] = mapped_column(String(32), nullable=False, default="low")
    recommendations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped[User | None] = relationship("User", back_populates="xray_analyses")


class RagDocument(Base):
    __tablename__ = "rag_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    document_type: Mapped[str] = mapped_column(String(64), nullable=False, default="other")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)  # float array
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # "processing" while background extraction runs; "ready" when done; "error" on failure
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    # Vision Cost Protection: pre-flight estimate computed after image extraction
    # {"model","total_images","vision_eligible","estimated_cost_usd","saved_by_filter_usd",...}
    vision_estimate: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped[User | None] = relationship("User", back_populates="rag_documents")
    images: Mapped[list["RagImage"]] = relationship(
        "RagImage", back_populates="document", cascade="all, delete-orphan"
    )
    pages: Mapped[list["RagPage"]] = relationship(
        "RagPage", back_populates="document", cascade="all, delete-orphan"
    )


class RagPage(Base):
    """
    One rendered PDF page, indexed with ColPali / OpenCLIP visual embeddings.
    Separate from RagImage (which stores individually extracted figures).
    """
    __tablename__ = "rag_pages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    doc_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rag_documents.id", ondelete="CASCADE"), nullable=False
    )
    doc_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    page_num: Mapped[int] = mapped_column(Integer, nullable=False)
    # PNG of the rendered page (PyMuPDF at 150 DPI → ~1000 px wide)
    image_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # Multi-vector visual embeddings: List[List[float]]
    #   ColQwen2 → N_patches × 128
    #   OpenCLIP → [[768-dim]]  (single-vector wrapped)
    colpali_vecs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Which backend produced the vectors (for debugging / re-indexing)
    backend: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    document: Mapped["RagDocument"] = relationship("RagDocument", back_populates="pages")


class RagImage(Base):
    """Images extracted from uploaded PDF documents, with vision captions and embeddings."""
    __tablename__ = "rag_images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    doc_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rag_documents.id", ondelete="CASCADE"), nullable=False
    )
    # Denormalised for efficient image-search without joins
    doc_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    page_num: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    image_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False, default="image/png")
    # GPT-5.4 vision caption — used for semantic search
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    # text-embedding-3-small embedding of (caption + filename + page) — for nearest-neighbour search
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Vision Cost Protection fields
    image_sha256:   Mapped[str | None]   = mapped_column(String(64),  nullable=True,  index=True)
    vision_skipped: Mapped[bool]         = mapped_column(Boolean,     nullable=False, default=False, server_default="false")
    skip_reason:    Mapped[str | None]   = mapped_column(String(64),  nullable=True)
    vision_cost_usd: Mapped[float]       = mapped_column(Float,       nullable=False, default=0.0,  server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    document: Mapped["RagDocument"] = relationship("RagDocument", back_populates="images")


class ResearchOutput(Base):
    __tablename__ = "research_outputs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    mode: Mapped[str] = mapped_column(String(64), nullable=False)   # paper_ieee, literature_review, etc.
    topic: Mapped[str] = mapped_column(String(1024), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kb_chunks_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Structured reference metadata captured at generation time (provider,
    # doi_verified, is_peer_reviewed, citation_count per accepted source) so
    # the publication-readiness gate can score real evidence quality at
    # export time instead of re-guessing it from the rendered markdown text.
    readiness_meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped[User | None] = relationship("User", back_populates="research_outputs")


class ResearchPipelineRun(Base):
    """Phase 1 research pipeline state and artifacts."""
    __tablename__ = "research_pipeline_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    mode: Mapped[str] = mapped_column(String(64), nullable=False)
    topic: Mapped[str] = mapped_column(String(2048), nullable=False)
    normalized_topic: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    current_stage: Mapped[str] = mapped_column(String(64), nullable=False, default="topic_normalization")
    artifacts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    user: Mapped[User | None] = relationship("User")


class GalleryIndex(Base):
    """
    Rich search index for every RagPage — populated by the reindex job.
    Stores AI-generated metadata (title, caption, tags, scanner model) and
    a text embedding for semantic gallery search.
    """
    __tablename__ = "gallery_index"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    rag_page_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rag_pages.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    doc_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    page_num: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    caption: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    scanner_model: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    manufacturer: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    ocr_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    image_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    thumbnail_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    page: Mapped["RagPage"] = relationship("RagPage")


class InnovationOutput(Base):
    """Stores outputs from the Innovation Engine (Patent Mode / Research Mode)."""
    __tablename__ = "innovation_outputs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    domain: Mapped[str] = mapped_column(String(128), nullable=False)
    domain_label: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    mode: Mapped[str] = mapped_column(String(32), nullable=False)   # patent | research | full
    topic: Mapped[str] = mapped_column(String(2048), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    kb_chunks_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    versions: Mapped[list["InnovationVersion"]] = relationship(
        "InnovationVersion", back_populates="innovation", cascade="all, delete-orphan",
        order_by="InnovationVersion.version_num"
    )


class TrainingProject(Base):
    """A training course generated from an uploaded equipment manual."""
    __tablename__ = "training_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Course identity
    course_title: Mapped[str] = mapped_column(String(512), nullable=False)
    manufacturer: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    equipment_model: Mapped[str] = mapped_column(String(256), nullable=False, default="")

    # Uploaded manual metadata
    manual_filename: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    manual_page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # JSON: list of {page_num, text, headings}
    extracted_pages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Course configuration (all settings stored as JSON for flexibility)
    settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Quick-access fields for list views
    audience: Mapped[str] = mapped_column(String(128), nullable=False, default="X-Ray Operators")
    training_type: Mapped[str] = mapped_column(String(128), nullable=False, default="Operator Training")
    language: Mapped[str] = mapped_column(String(32), nullable=False, default="english")
    difficulty: Mapped[str] = mapped_column(String(32), nullable=False, default="intermediate")

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    # ready | generating | complete | error
    version_num: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    slides: Mapped[list["TrainingSlide"]] = relationship(
        "TrainingSlide", back_populates="project",
        cascade="all, delete-orphan",
        order_by="TrainingSlide.slide_index",
    )


class TrainingSlide(Base):
    """One slide within a TrainingProject."""
    __tablename__ = "training_slides"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("training_projects.id", ondelete="CASCADE"), nullable=False
    )
    slide_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # title | agenda | section | objectives | content | quiz | practical | summary | references
    slide_type: Mapped[str] = mapped_column(String(32), nullable=False, default="content")
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    # JSON: list of strings (bullet points) or structured content
    content: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    speaker_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # JSON: list of page numbers cited
    source_pages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Instructor approval: pending | approved | rejected
    approval_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    project: Mapped["TrainingProject"] = relationship("TrainingProject", back_populates="slides")


class TranslationProject(Base):
    """A professional translation project — stores source, translated segments, and output files."""
    __tablename__ = "translation_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Project identity
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Source document
    source_filename: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    source_file_type: Mapped[str] = mapped_column(String(32), nullable=False, default="txt")
    source_file_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    # Path to source file on disk for large uploads; when set, source_file_data is None
    source_file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Language pair
    source_lang: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    target_lang: Mapped[str] = mapped_column(String(16), nullable=False, default="ar")

    # Translation settings
    style: Mapped[str] = mapped_column(String(32), nullable=False, default="technical")
    keep_english_terms: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    transliterate_names: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Pipeline results
    # List of {id, source, target, seg_type, memory_match, flagged, flag_reason, edited}
    segments: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_issues: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Rebuilt output files (stored as bytes)
    output_docx: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    output_pptx: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    output_xlsx: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    # Provider platform additions
    # Which provider was used: "openai" | "deepl" | "azure" | "google" | "auto"
    provider_name: Mapped[str] = mapped_column(String(32), nullable=False, default="auto")
    # Extended quality breakdown: {translation_quality, engineering_quality, consistency_score,
    # formatting_score, dnt_score, dnt_tokens_found, dnt_tokens_garbled, engineering_review_changes}
    quality_breakdown: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # List of {seg_id, before, after, reason} dicts from engineering review
    engineering_review_changes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # DNT tokens found in the source document
    dnt_tokens: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Version history: [{version_num, created_at, name, quality_score, segment_count}]
    versions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    version_num: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    # ready | translating | complete | error

    # Which backend actually produced the current output_docx/output_pptx:
    # "native_office" (real Word/PowerPoint desktop COM automation) or
    # "reconstructed" (python-docx/python-pptx rebuild). Never overstate the
    # former when the latter is what actually ran.
    formatting_fidelity: Mapped[str] = mapped_column(String(32), nullable=False, default="reconstructed")

    # ── Layout Intelligence fields ─────────────────────────────────────────────
    # layout_mode: "original" | "saved" | "reference"
    # style_profile_id: LayoutStyle.id (when layout_mode=="saved")
    # template_strength: "light" | "balanced" | "strong"
    # layout_options: dict of boolean toggle flags
    # layout_quality_score: score computed after PPTX rebuild
    layout_config: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict,
        server_default="'{}'::json",
    )
    # Bytes of an uploaded reference template (when layout_mode=="reference")
    reference_template_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


# ── Book Authoring Studio ───────────────────────────────────────────────────
# Original-book creation from a topic — NOT a translation module. Single
# language per project (no BookLanguageEdition/BookChapterEdition). Word COM
# is never a dependency here; DOCX compile uses plain python-docx via
# api.services.workspace_agent.doc_builder.

class BookProject(Base):
    """A book authoring project: metadata, outline, chapter order/state, and
    compiled/exported output — owns everything about one book."""
    __tablename__ = "book_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    topic: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")

    # draft | outline_generating | outline_ready | outline_approved |
    # chapters_in_progress | chapters_ready | compiling | compiled |
    # exported | error
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Ordered list of {chapter_number, title, summary}
    outline: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Optional read-only content sources: [{module, ref_id, label}] pointing
    # at existing Research Studio / Training / Education / Knowledge Base
    # outputs a chapter can be seeded from. Those modules are never modified.
    source_config: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    compiled_docx: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    compiled_pdf: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    compiled_html: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class BookChapter(Base):
    """One chapter's current live content and state within a BookProject."""
    __tablename__ = "book_chapters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    book_project_id: Mapped[str] = mapped_column(String(36), ForeignKey("book_projects.id", ondelete="CASCADE"), nullable=False)

    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # pending | generating | generated | edited | approved | error
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Which optional existing-module source(s) this chapter was generated from
    source_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    __table_args__ = (UniqueConstraint("book_project_id", "chapter_number", name="uq_book_chapter_number"),)


class BookChapterVersion(Base):
    """Immutable snapshot of a chapter's content — chapter version history."""
    __tablename__ = "book_chapter_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    chapter_id: Mapped[str] = mapped_column(String(36), ForeignKey("book_chapters.id", ondelete="CASCADE"), nullable=False)

    version_num: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # ai_generate | manual_edit | regenerate
    created_by: Mapped[str] = mapped_column(String(32), nullable=False, default="ai_generate")
    note: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class BookReference(Base):
    """A citation/reference, book-wide or scoped to one chapter."""
    __tablename__ = "book_references"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    book_project_id: Mapped[str] = mapped_column(String(36), ForeignKey("book_projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("book_chapters.id", ondelete="CASCADE"), nullable=True)

    citation_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class BookFigure(Base):
    """A figure/image, book-wide or scoped to one chapter. Image bytes live
    on disk (via file_storage.py's convention) — storage_path only, no blobs
    in this table."""
    __tablename__ = "book_figures"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    book_project_id: Mapped[str] = mapped_column(String(36), ForeignKey("book_projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("book_chapters.id", ondelete="CASCADE"), nullable=True)

    caption: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    placement_note: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class BookTable(Base):
    """A data table, book-wide or scoped to one chapter."""
    __tablename__ = "book_tables"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    book_project_id: Mapped[str] = mapped_column(String(36), ForeignKey("book_projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("book_chapters.id", ondelete="CASCADE"), nullable=True)

    caption: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    # {"headers": [...], "rows": [[...], ...]}
    table_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TranslationSegment(Base):
    """Translation memory — stores source→target pairs for future reuse."""
    __tablename__ = "translation_segments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA256 of normalised source
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    target_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_lang: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    target_lang: Mapped[str] = mapped_column(String(16), nullable=False, default="ar")
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class CustomDictionaryEntry(Base):
    """Per-user custom terminology dictionary for consistent technical translation."""
    __tablename__ = "custom_dictionary_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    source_term: Mapped[str] = mapped_column(String(512), nullable=False)
    target_term: Mapped[str] = mapped_column(String(512), nullable=False)
    source_lang: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    target_lang: Mapped[str] = mapped_column(String(16), nullable=False, default="ar")
    domain: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class ProviderConfig(Base):
    """
    Translation provider API configuration, stored per user (or shared if user_id=NULL).

    Stores encrypted API keys for DeepL, Azure, Google, and OpenAI translation providers.
    """
    __tablename__ = "provider_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Which provider: "deepl" | "azure" | "google" | "openai"
    provider_name: Mapped[str] = mapped_column(String(32), nullable=False)
    # Fernet-encrypted API key (using SESSION_SECRET as key material)
    api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Whether this provider is enabled for auto-selection
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Whether this provider is the fallback when no others are configured
    is_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Priority order (lower = higher priority)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    # Max document size in MB for this provider
    max_file_size_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    # Max pages for this provider (0 = unlimited)
    max_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    # Additional provider-specific configuration: e.g. {"region": "eastus"} for Azure
    extra_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Supported language codes for this provider ([] = all)
    supported_langs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class TranslationImage(Base):
    """
    A single image extracted from a translation project document.

    Stores original bytes, GPT-4o-detected text regions (with bounding boxes
    and translated text), and the PIL-rendered translated image bytes.
    """
    __tablename__ = "translation_images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("translation_projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Source location in document
    doc_page: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False, default="other")
    # "pdf_page" | "docx_inline" | "pptx_slide" | "other"
    image_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Raw image data
    original_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    rendered_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    original_mime: Mapped[str] = mapped_column(String(64), nullable=False, default="image/png")
    width_px: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    height_px: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Detected / translated text regions — list of dicts:
    # { id, bbox: {x%,y%,w%,h%}, source_text, translated_text, confidence,
    #   font_size, font_color, is_technical_code, edited, approved, keep_english }
    regions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    # pending | processing | done | error | no_text
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


# ── Education Studio ──────────────────────────────────────────────────────────

class EducationProject(Base):
    """A reference-based education project in the upgraded Education Studio."""
    __tablename__ = "education_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    title: Mapped[str] = mapped_column(String(512), nullable=False, default="Untitled Project")
    course_title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    lesson_title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    equipment_manufacturer: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    equipment_model: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    system_type: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    technical_domain: Mapped[str] = mapped_column(String(256), nullable=False, default="")

    audience: Mapped[str] = mapped_column(String(128), nullable=False, default="operator")
    level: Mapped[str] = mapped_column(String(64), nullable=False, default="intermediate")
    depth_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="advanced")
    # overview | basic | standard | advanced | master_instructor | certification
    language: Mapped[str] = mapped_column(String(32), nullable=False, default="english")
    delivery_mode: Mapped[str] = mapped_column(String(64), nullable=False, default="classroom")

    course_duration: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    lesson_duration: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    num_sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    instructor_name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    customer: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    country_regulatory: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    prerequisites: Mapped[str] = mapped_column(Text, nullable=False, default="")
    learning_outcomes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    pass_mark: Mapped[int] = mapped_column(Integer, nullable=False, default=70)
    num_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=10)

    include_practical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    include_instructor_notes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    include_student_notes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    include_references: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    include_citations: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    include_images: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    include_tables: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    include_final_assessment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    include_answer_key: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    selected_output_types: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    # draft | generating | complete | error | archived
    quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    references: Mapped[list["EducationReference"]] = relationship(
        "EducationReference", back_populates="project", cascade="all, delete-orphan",
        order_by="EducationReference.created_at"
    )
    outputs: Mapped[list["EducationOutput"]] = relationship(
        "EducationOutput", back_populates="project", cascade="all, delete-orphan",
        order_by="EducationOutput.output_type"
    )


class EducationReference(Base):
    """A reference file uploaded to an EducationProject."""
    __tablename__ = "education_references"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("education_projects.id", ondelete="CASCADE"), nullable=False
    )

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False, default="pdf")

    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    table_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    procedure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    section_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    figure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    troubleshooting_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    doc_language: Mapped[str] = mapped_column(String(32), nullable=False, default="en")
    ocr_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    extracted_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    structure: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    raw_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    role: Mapped[str] = mapped_column(String(32), nullable=False, default="primary")
    # primary | supporting | style | terminology
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="upload")
    # upload | knowledge_base
    rag_doc_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    # pending | processing | done | error
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    project: Mapped["EducationProject"] = relationship("EducationProject", back_populates="references")


class EducationOutput(Base):  # noqa: F811
    """A single generated output (lesson plan, quiz, PPTX, etc.) for an EducationProject."""
    __tablename__ = "education_outputs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("education_projects.id", ondelete="CASCADE"), nullable=False
    )

    output_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")

    citations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    quality_issues: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    technical_accuracy_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_coverage_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    citation_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lo_alignment_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    output_docx: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    output_pptx: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    project: Mapped["EducationProject"] = relationship("EducationProject", back_populates="outputs")


# ── Innovation ────────────────────────────────────────────────────────────────

class InnovationVersion(Base):
    """A saved draft/version of an InnovationOutput, optionally in a specific language."""
    __tablename__ = "innovation_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    innovation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("innovation_outputs.id", ondelete="CASCADE"), nullable=False
    )
    version_num: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")  # en | ar | bilingual
    note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    innovation: Mapped["InnovationOutput"] = relationship("InnovationOutput", back_populates="versions")


class TranslationUsage(Base):
    """Per-job OpenAI API usage & estimated-cost record (admin dashboard).

    Never stores document contents or API keys — metadata only.
    """
    __tablename__ = "translation_usage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    project_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    project_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    est_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    segments_total: Mapped[int] = mapped_column(Integer, default=0)
    segments_translated: Mapped[int] = mapped_column(Integer, default=0)
    memory_hits: Mapped[int] = mapped_column(Integer, default=0)
    duration_secs: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    # Character-based billing (DeepL Free tier: 500K chars/month at $0)
    chars_translated: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    # ── Per-stage token breakdown (actual API values, not estimates) ────────────
    translate_in_tokens: Mapped[int] = mapped_column(Integer, default=0)
    translate_out_tokens: Mapped[int] = mapped_column(Integer, default=0)
    translate_cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    review_in_tokens: Mapped[int] = mapped_column(Integer, default=0)
    review_out_tokens: Mapped[int] = mapped_column(Integer, default=0)
    review_cached_tokens: Mapped[int] = mapped_column(Integer, default=0)

    # ── Stage wall-clock times (seconds, measured at pipeline runtime) ──────────
    stage_extract_s: Mapped[float] = mapped_column(Float, default=0.0)
    stage_translate_s: Mapped[float] = mapped_column(Float, default=0.0)
    stage_review_s: Mapped[float] = mapped_column(Float, default=0.0)
    stage_rebuild_s: Mapped[float] = mapped_column(Float, default=0.0)
    stage_validate_s: Mapped[float] = mapped_column(Float, default=0.0)

    # ── API call counts ─────────────────────────────────────────────────────────
    api_calls_translate: Mapped[int] = mapped_column(Integer, default=0)
    api_calls_review: Mapped[int] = mapped_column(Integer, default=0)

    # ── Segment & document detail ───────────────────────────────────────────────
    segments_reviewed: Mapped[int] = mapped_column(Integer, default=0)
    memory_misses: Mapped[int] = mapped_column(Integer, default=0)
    source_pages: Mapped[int] = mapped_column(Integer, default=0)


class UnifiedUsageLog(Base):
    """
    Single source of truth for ALL OpenAI API calls across every platform feature.

    Previously untracked features (Innovation Engine, Training Generator, Gallery
    Reindex, RAG Vision, Image Translator, LinkedIn, X-Ray Analysis, mandatory-section
    builder) now write here so the Cost Dashboard captures 100% of OpenAI spend.
    """
    __tablename__ = "openai_usage_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feature: Mapped[str] = mapped_column(String(64), index=True)
    sub_feature: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ChatUsage(Base):
    """Per-request AI Chat token & cost tracker (all values from actual API or char estimate)."""
    __tablename__ = "chat_usage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True, unique=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)   # general | research | ...
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)        # GENERAL_CHAT | RAG_QA | ...
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    est_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rag_chunks_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_secs: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    finish_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class AppSetting(Base):
    """Admin-configurable key-value settings store (budget, markup, etc.)."""
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


# ── Self-Learning System ───────────────────────────────────────────────────────

class DocumentHash(Base):
    """SHA-256 content fingerprint — prevents reprocessing the same file twice."""
    __tablename__ = "document_hashes"

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class StudyJob(Base):
    """Tracks the 11-phase document-study pipeline for a single RagDocument."""
    __tablename__ = "study_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    doc_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Pipeline status: pending | studying | scored | awaiting_approval | approved | rejected
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")

    # Phase 2 — extracted entities
    extracted_systems: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    extracted_components: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    extracted_procedures: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    extracted_terminology: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    extracted_warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    extracted_specs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    extracted_fault_codes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    extracted_abbreviations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Phase 3 — semantic understanding
    document_purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    intended_audience: Mapped[str | None] = mapped_column(String(256), nullable=True)
    prerequisite_knowledge: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    difficulty_level: Mapped[str | None] = mapped_column(String(32), nullable=True)  # beginner/intermediate/advanced
    new_information: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    overlapping_docs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    contradictions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    missing_topics: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Phase 4 — knowledge graph nodes/edges (raw extraction before persistence)
    graph_nodes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    graph_edges: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Phase 6 — training profile
    learning_objectives: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    instructor_notes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    quiz_ideas: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    practical_scenarios: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    common_mistakes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    hands_on_exercises: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    field_tips: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Phase 7 — quality scores (0–100 each)
    score_educational_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_technical_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_image_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_diagram_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_reference_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_safety_coverage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_maintenance_coverage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_overall: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Phase 11 — per-document report counts
    report_concepts: Mapped[int] = mapped_column(Integer, default=0)
    report_systems: Mapped[int] = mapped_column(Integer, default=0)
    report_components: Mapped[int] = mapped_column(Integer, default=0)
    report_procedures: Mapped[int] = mapped_column(Integer, default=0)
    report_troubleshooting: Mapped[int] = mapped_column(Integer, default=0)
    report_images_understood: Mapped[int] = mapped_column(Integer, default=0)
    report_new_info_count: Mapped[int] = mapped_column(Integer, default=0)
    report_duplicate_info_count: Mapped[int] = mapped_column(Integer, default=0)
    report_graph_nodes_added: Mapped[int] = mapped_column(Integer, default=0)
    report_graph_edges_added: Mapped[int] = mapped_column(Integer, default=0)

    # Admin review
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # GPT usage (for cost tracking)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    model_used: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Owner-trusted auto-integration lifecycle
    # archived=True → knowledge excluded from future generation (soft-delete)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    # Timestamp set at the moment the GPT call begins — None means job was created
    # but the pipeline never actually started (e.g. server restarted).
    # If status == 'studying' and started_at is None (or updated_at == created_at),
    # the job is orphaned and should be marked stalled.
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class KnowledgeNode(Base):
    """Persistent knowledge graph node — a concept, component, system, etc."""
    __tablename__ = "knowledge_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # node_type (actual values produced by api.services.research_brain's
    # extraction layers — see local_extraction._VALID_NODE_TYPES, the single
    # source of truth): Equipment | Manufacturer | Standard | Procedure |
    # Fault | Solution | Warning | Specification | System | Subsystem |
    # Component | Function | Safety | Failure | Cause | Repair | Product |
    # Patent | Training | Paper | Author | Institution (last 6 added Phase
    # 2B.5 for Manufacturer Intelligence + Scientific Literature Learning).
    node_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_doc_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    study_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # approved=True once the admin approves the study job that created this node
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # ── Knowledge Evolution Engine (Phase 2A) — additive, optional fields ────
    # A node is never deleted when superseded — a new version is created and
    # linked via supersedes_id/replaced_by_id, and the old one's status flips
    # to "deprecated". Populated by api.services.research_brain.knowledge_versioning;
    # study_service.py's existing writer path leaves these at their defaults.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5, server_default="0.5")
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # current | deprecated | experimental | historical
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="current", server_default="current")
    supersedes_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_nodes.id", ondelete="SET NULL"), nullable=True
    )
    replaced_by_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_nodes.id", ondelete="SET NULL"), nullable=True
    )
    research_topic_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_topics.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Phase 2B.0 — which extraction layer produced this node's first version:
    # local_ollama | deterministic | paid_provider. Null for pre-2B.0 rows.
    provider_used: Mapped[str | None] = mapped_column(String(24), nullable=True)


class KnowledgeEdge(Base):
    """Directed relationship between two knowledge graph nodes."""
    __tablename__ = "knowledge_edges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    from_node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    to_node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # relationship type (actual values produced — see
    # local_extraction._VALID_RELATIONSHIPS, the single source of truth):
    # uses | connected_to | produces | requires | references | contains |
    # causes | repairs | triggers | prevents | manufactures | authored_by |
    # affiliated_with | cites (last 4 added Phase 2B.5).
    relationship: Mapped[str] = mapped_column(String(64), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # ── Knowledge Evolution Engine (Phase 2A) — additive, optional fields ───
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5, server_default="0.5")
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="current", server_default="current")
    # Phase 2B.0 — see KnowledgeNode.provider_used.
    provider_used: Mapped[str | None] = mapped_column(String(24), nullable=True)


class SlideCorrection(Base):
    """Instructor correction record — before/after diff for a training slide."""
    __tablename__ = "slide_corrections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # Reference to slide — can be TrainingSlide.id or EducationOutput.id
    slide_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    slide_type: Mapped[str] = mapped_column(String(32), nullable=False, default="training")  # training | education
    original_content: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    corrected_content: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    correction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # weight: instructor corrections gain weight > 1.0; starts at 1.0
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TerminologyEntry(Base):
    """Domain-specific term extracted from uploaded documents — the platform's vocabulary bank."""
    __tablename__ = "terminology_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    term: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    # abbreviation | equipment | component | procedure | safety | specification | general
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_doc_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ImageClassification(Base):
    """OpenCLIP-derived category label for an extracted RagImage (zero API cost)."""
    __tablename__ = "image_classifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    image_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rag_images.id", ondelete="CASCADE"),
        nullable=False, index=True, unique=True,
    )
    # component | warning | operation | maintenance | safety | x-ray |
    # detector | conveyor | generator | monitor | ui | diagram | unknown
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    model: Mapped[str] = mapped_column(String(64), nullable=False, default="keyword")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class LayoutStyle(Base):
    """PPTX layout style profile extracted from an uploaded presentation."""
    __tablename__ = "layout_styles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    source_doc_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # JSON: slide_width_in, slide_height_in, theme_colors, title_font_name,
    #       title_font_size, body_font_name, body_font_size, bg_color
    properties: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PptxPresentationIndex(Base):
    """Presentation-level metadata for PPTX files in the knowledge base."""
    __tablename__ = "pptx_presentation_index"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    doc_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, unique=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    course_title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    course_type: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    target_audience: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    equipment_family: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    equipment_name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    equipment_model: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    manufacturer: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    language: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    slide_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    main_topics: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Source control flags
    source_status: Mapped[str] = mapped_column(String(64), nullable=False, default="unverified")
    trusted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    manufacturer_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    internal_training_reference: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    visual_template: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    arabic_formatting_example: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    obsolete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    do_not_use: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class PptxSlideIndex(Base):
    """Slide-level index for targeted PPTX retrieval during course generation."""
    __tablename__ = "pptx_slide_index"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    doc_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    presentation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    slide_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    slide_title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    slide_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    speaker_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    table_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    image_captions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    diagram_labels: Mapped[str] = mapped_column(Text, nullable=False, default="")
    equipment_name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    equipment_model: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    manufacturer: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    training_category: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    language: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    visual_layout_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_status: Mapped[str] = mapped_column(String(64), nullable=False, default="unverified")
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)



class ExamPattern(Base):
    """Question/answer pattern extracted from an exam reference document."""
    __tablename__ = "exam_patterns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_doc_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    source_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # bloom_level: remember | understand | apply | analyze | evaluate | create
    bloom_level: Mapped[str] = mapped_column(String(32), nullable=False, default="remember")
    # difficulty: easy | medium | hard
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    distractor_quality: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    topic: Mapped[str | None] = mapped_column(String(256), nullable=True)
    options: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class VisionCostLog(Base):
    """Audit record for every GPT Vision decision: actual call, cache hit, or local skip."""
    __tablename__ = "vision_cost_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    image_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rag_images.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    doc_id:       Mapped[str]        = mapped_column(String(36),  nullable=False, index=True)
    doc_filename: Mapped[str]        = mapped_column(String(512), nullable=False)
    page_num:     Mapped[int]        = mapped_column(Integer,     nullable=False, default=1)
    image_sha256: Mapped[str | None] = mapped_column(String(64),  nullable=True)
    model:        Mapped[str]        = mapped_column(String(64),  nullable=False, default="gpt-4o")

    # Token & cost breakdown
    prompt_tokens:     Mapped[int]   = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int]   = mapped_column(Integer, nullable=False, default=0)
    cost_usd:          Mapped[float] = mapped_column(Float,   nullable=False, default=0.0)

    # Decision flags
    cache_hit:   Mapped[bool]        = mapped_column(Boolean, nullable=False, default=False)
    skipped:     Mapped[bool]        = mapped_column(Boolean, nullable=False, default=False)
    skip_reason: Mapped[str | None]  = mapped_column(String(64), nullable=True)

    # Money saved (vs. what it would have cost without the guard)
    saved_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PlatformConfig(Base):
    """
    Key-value configuration store for runtime platform settings.

    Used by the Vision kill switch and other emergency toggles that must survive
    server restarts without requiring environment variable changes.

    Keys of interest:
      vision_enabled  — "true" / "false"  (default: "false")
    """
    __tablename__ = "platform_config"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class CostIncident(Base):
    """
    Permanent financial incident record — never deleted, never hidden.

    Each row represents one billing anomaly: unexpected runaway costs,
    unprotected API floods, or model mis-configurations that led to
    measurable financial impact.
    """
    __tablename__ = "cost_incidents"

    id:               Mapped[str]        = mapped_column(String(36),  primary_key=True, default=_uuid)
    incident_date:    Mapped[datetime]   = mapped_column(DateTime(timezone=True), nullable=False, default=_now, index=True)
    feature:          Mapped[str]        = mapped_column(String(128), nullable=False, index=True)
    model:            Mapped[str | None] = mapped_column(String(64),  nullable=True)
    # List of OpenAI request IDs if captured
    openai_request_ids: Mapped[list]    = mapped_column(JSON,         nullable=False, default=list)
    total_cost_usd:   Mapped[float]     = mapped_column(Float,        nullable=False, default=0.0)
    api_calls:        Mapped[int]        = mapped_column(Integer,      nullable=False, default=0)
    vision_calls:     Mapped[int]        = mapped_column(Integer,      nullable=False, default=0)
    images_processed: Mapped[int]        = mapped_column(Integer,      nullable=False, default=0)
    prompt_tokens:    Mapped[int]        = mapped_column(Integer,      nullable=False, default=0)
    completion_tokens: Mapped[int]       = mapped_column(Integer,      nullable=False, default=0)
    cached_tokens:    Mapped[int]        = mapped_column(Integer,      nullable=False, default=0)
    root_cause:       Mapped[str | None] = mapped_column(Text,         nullable=True)
    resolution:       Mapped[str | None] = mapped_column(Text,         nullable=True)
    # open | investigating | resolved | monitoring
    status:           Mapped[str]        = mapped_column(String(32),   nullable=False, default="resolved")
    fixed_by:         Mapped[str | None] = mapped_column(String(256),  nullable=True)
    # low | medium | high | critical
    severity:         Mapped[str]        = mapped_column(String(16),   nullable=False, default="high")
    notes:            Mapped[str | None] = mapped_column(Text,         nullable=True)
    created_at:       Mapped[datetime]   = mapped_column(DateTime(timezone=True), default=_now)
    updated_at:       Mapped[datetime]   = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class ProtectionConfigLog(Base):
    """
    Immutable audit trail for every protection configuration change.

    Written whenever: kill switch is toggled, limits are changed,
    model routing is reconfigured. Provides the 'Historical Protection
    Validation' required by the financial audit spec.
    """
    __tablename__ = "protection_config_log"

    id:          Mapped[str]        = mapped_column(String(36),  primary_key=True, default=_uuid)
    config_key:  Mapped[str]        = mapped_column(String(128), nullable=False, index=True)
    old_value:   Mapped[str | None] = mapped_column(Text,        nullable=True)
    new_value:   Mapped[str | None] = mapped_column(Text,        nullable=True)
    user_id:     Mapped[str | None] = mapped_column(String(128), nullable=True)
    reason:      Mapped[str | None] = mapped_column(Text,        nullable=True)
    # api | env | default | seed | kill_switch
    source:      Mapped[str]        = mapped_column(String(64),  nullable=False, default="api")
    changed_at:  Mapped[datetime]   = mapped_column(DateTime(timezone=True), default=_now, index=True)


class UploadSession(Base):
    """
    Tracks a chunked upload in progress.
    Created by POST /api/rag/upload/start, updated by each chunk PUT,
    finalized by POST /api/rag/upload/{session_id}/complete.
    """
    __tablename__ = "upload_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    total_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # bytes
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # bytes
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # JSON list of booleans — True = chunk received
    received_chunks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # uploading | complete | expired
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploading")
    temp_dir: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    document_type: Mapped[str] = mapped_column(String(64), nullable=False, default="other")
    # Set when /complete succeeds — used for safe idempotent re-delivery
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Set for all terminal outcomes (normal upload AND duplicate) to enable
    # idempotent re-delivery without touching temp files a second time
    result_doc_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class ProcessingJob(Base):
    """
    Persistent background job for large file processing.
    Survives server restarts — unlike asyncio.create_task which is killed on reload.

    Lifecycle: queued → extracting → studying → integrating → completed
                                   ↘ failed | paused | cancelled
    """
    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    doc_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rag_documents.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    # queued | extracting | studying | integrating | completed | failed | paused | cancelled | awaiting_cost_approval
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    current_stage: Mapped[str] = mapped_column(String(256), nullable=False, default="Queued")
    current_batch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_batches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # JSON checkpoint — stores last successful batch index and accumulated text
    checkpoint_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cost_incurred_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ai_calls_made: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    document: Mapped["RagDocument"] = relationship("RagDocument")


class LearningReport(Base):
    """Periodic (or on-demand) platform learning progress report."""
    __tablename__ = "learning_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    report_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TrainingCourseReport(Base):
    """A generated Training Course Report (course-completion/certification record)."""
    __tablename__ = "training_course_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    template: Mapped[str] = mapped_column(String(64), nullable=False, default="standard_completion")
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    customer: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    system_type: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    instructor: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    start_date: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    end_date: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    # draft | final
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    output_language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")

    # Full structured form input (section A-E fields, attendees, doc refs)
    form_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # {section_key: narrative_text} — AI-drafted, user-editable
    narrative: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    docx_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    docx_filename: Mapped[str] = mapped_column(String(512), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


# ── AI Chat Workspace agent (file/folder upload → inspect → generate) ────────

class Workspace(Base):
    """A per-user file/folder workspace attached to the AI Chat agent."""
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, default="Workspace")
    # active | archived
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    total_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    files: Mapped[list["WorkspaceFile"]] = relationship(
        "WorkspaceFile", back_populates="workspace", cascade="all, delete-orphan"
    )
    tasks: Mapped[list["WorkspaceTask"]] = relationship(
        "WorkspaceTask", back_populates="workspace", cascade="all, delete-orphan"
    )
    generated_files: Mapped[list["GeneratedFile"]] = relationship(
        "GeneratedFile", back_populates="workspace", cascade="all, delete-orphan"
    )


class WorkspaceFile(Base):
    """One uploaded file inside a workspace, with its relative folder path preserved."""
    __tablename__ = "workspace_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False, default="application/octet-stream")
    extension: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    # pending | processing | ready | error | unsupported | skipped
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    extracted_text_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    errors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    workspace: Mapped[Workspace] = relationship("Workspace", back_populates="files")


class WorkspaceTask(Base):
    """One agent turn/run against a workspace — persisted for history, audit, and polling."""
    __tablename__ = "workspace_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    user_instruction: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # queued | uploading | extracting | indexing | analyzing | generating | validating
    # | completed | completed_with_warnings | failed | cancelled
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    plan: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    result_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    workspace: Mapped[Workspace] = relationship("Workspace", back_populates="tasks")
    events: Mapped[list["TaskEvent"]] = relationship(
        "TaskEvent", back_populates="task", cascade="all, delete-orphan", order_by="TaskEvent.created_at"
    )


class TaskEvent(Base):
    """A single progress/audit event within a WorkspaceTask (plan, tool_call, tool_result, stage, error)."""
    __tablename__ = "task_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspace_tasks.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    task: Mapped[WorkspaceTask] = relationship("WorkspaceTask", back_populates="events")


class GeneratedFile(Base):
    """A downloadable file produced by the workspace agent (Excel/Word/PPTX/PDF/CSV/JSON/MD/TXT)."""
    __tablename__ = "generated_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("workspace_tasks.id", ondelete="SET NULL"), nullable=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_file_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    workspace: Mapped[Workspace] = relationship("Workspace", back_populates="generated_files")


# ── Connectors (Enterprise Connector Framework) ─────────────────────────────────

class Connector(Base):
    """A registered platform connector (Canva, Google Drive, SFTP, etc.).

    `capabilities`/`category`/`auth_strategy_type` are a denormalized snapshot
    of the provider's ConnectorManifest (api/services/connectors/manifest.py)
    so /api/connectors can list every provider's declared capabilities without
    instantiating each connector class per request.
    """
    __tablename__ = "connectors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="custom")
    auth_strategy_type: Mapped[str] = mapped_column(String(32), nullable=False, default="no_auth")
    icon: Mapped[str] = mapped_column(String(16), nullable=False, default="🔌")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_sync: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_health_check: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Snapshot of ConnectorManifest.capabilities (see manifest.as_dict()["capabilities"])
    capabilities: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # Non-secret provider config: API base URLs, docs links, etc.
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class UserConnectorAccount(Base):
    """One user's connection to one connector.

    `encrypted_credentials` is a single Fernet-encrypted JSON blob whose shape
    is defined by the connector's AuthStrategy (access/refresh token for
    OAuth2, an API key, SSH key material, a local folder path, custom
    headers, ...) — this is what lets every auth strategy share one storage
    column instead of the schema growing a new pair of columns per provider.
    """
    __tablename__ = "user_connector_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "connector_id", name="uq_user_connector"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    connector_id: Mapped[str] = mapped_column(String(36), ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False, index=True)

    external_user_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # Best available human-readable account identifier (email, display name,
    # username, or folder path) — meaning varies per auth strategy.
    external_account_email: Mapped[str | None] = mapped_column(String(256), nullable=True)

    encrypted_credentials: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    granted_scopes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # connected | disconnected | error | expired
    connection_status: Mapped[str] = mapped_column(String(32), nullable=False, default="disconnected")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class ConnectorEvent(Base):
    """Unified audit log for every connector event — never stores tokens or full payloads."""
    __tablename__ = "connector_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    connector_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("connectors.id", ondelete="SET NULL"), nullable=True, index=True)
    # action | sync | health | auth
    event_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # success | error
    request_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    response_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class ConnectorSyncState(Base):
    """Per-user-per-connector incremental sync cursor, driving the background SyncScheduler."""
    __tablename__ = "connector_sync_state"
    __table_args__ = (
        UniqueConstraint("user_id", "connector_id", name="uq_user_connector_sync"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    connector_id: Mapped[str] = mapped_column(String(36), ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False, index=True)
    cursor: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # success | error
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    sync_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=900)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class DesignWorkflow(Base):
    """One AI-generated Canva design request, tracked across follow-up edits
    ("change the title", "use another template", "switch to Arabic", ...) so
    those turns act on the same design instead of starting a fresh one."""
    __tablename__ = "design_workflows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)

    design_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # autofill_brand_template | render_and_import | render_only
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    # {title, subtitle, bullets, palette, language, direction, width, height}
    structured_spec: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    canva_design_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    canva_brand_template_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_export_urls: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


# ── Agent Orchestrator (intent → plan → provider/connector steps) ──────────────

class AgentRun(Base):
    """One orchestrator-executed chat request — the plan, its steps, and outcome."""
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True)
    source_module: Mapped[str] = mapped_column(String(64), nullable=False, default="ai_chat")
    intent: Mapped[str] = mapped_column(String(64), nullable=False)
    plan: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    current_step_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # planning | awaiting_confirmation | running | completed | failed | cancelled | partially_completed
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planning")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inputs: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    outputs: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_usage: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    steps: Mapped[list["AgentStep"]] = relationship(
        "AgentStep", back_populates="run", cascade="all, delete-orphan", order_by="AgentStep.created_at"
    )
    artifacts: Mapped[list["AgentArtifact"]] = relationship(
        "AgentArtifact", back_populates="run", cascade="all, delete-orphan", order_by="AgentArtifact.created_at"
    )


class AgentStep(Base):
    """One step of an AgentRun's plan (a single provider/connector action)."""
    __tablename__ = "agent_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    depends_on: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confirmation_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # pending | running | completed | failed | skipped | cancelled
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    run: Mapped[AgentRun] = relationship("AgentRun", back_populates="steps")


class AgentArtifact(Base):
    """One real, verified output file/object produced by an AgentRun."""
    __tablename__ = "agent_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # png | pdf | canva_design | drive_file
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    run: Mapped[AgentRun] = relationship("AgentRun", back_populates="artifacts")


# ── Knowledge Library: persistent folder sources for the AI Training Center ──

class KnowledgeLibraryFolder(Base):
    """A registered local folder that the AI Training Center can (re-)scan on demand."""
    __tablename__ = "knowledge_library_folders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    path: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # idle | scanning | completed | error
    scan_status: Mapped[str] = mapped_column(String(16), nullable=False, default="idle")
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # {"discovered": int, "queued": int, "skipped_duplicate": int, "skipped_unsupported": int, "errors": [str]}
    last_scan_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ── Global AI Brain: persistent memory ────────────────────────────────────────

class MemoryItem(Base):
    """
    A durable memory unit — a preference, decision, pinned note, or an
    automatically-captured project event. Only ever written for authenticated
    users (persistent memory is gated to login; anonymous sessions never get
    rows here — see api.services.identity.MemoryScope).

    `module` tags which platform module the memory belongs to ("general" for
    Chat, "translation", "training", "research", "patent", "physics",
    "education" for later phases) so search can be scoped per-module or
    across the whole Global AI Brain.
    """
    __tablename__ = "memory_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(64), nullable=False, default="general", index=True)
    # preference | decision | pinned | project_event | note
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="note")
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # explicit | project_event | document
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="explicit")
    # Free-form reference to the origin (conversation_id, project id, doc_id, …)
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    user: Mapped["User"] = relationship("User", back_populates="memory_items")


class ConversationSummary(Base):
    """
    A rolling summary of a block of conversation messages, generated every
    N messages (default 20-30) so long conversations stay searchable and
    bounded without ever deleting the raw Message rows. Generated for both
    authenticated and anonymous conversations — it's conversation-scoped, not
    identity-scoped.
    """
    __tablename__ = "conversation_summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    covers_from_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    covers_to_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    message_count_covered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="summaries")


# ── Hybrid Workspace Awareness: indexing freshness tracking ──────────────────

class IndexedResource(Base):
    """
    Freshness/version tracking for every indexable thing the Global AI Brain
    can search: workspace files, RAG documents, knowledge-base folder
    entries, connector-synced items. One row per resource.

    Driven by api.services.workspace_index — trigger points across the app
    call mark_dirty() on the relevant event (upload/edit/delete/KB scan/
    connector sync/explicit refresh/...); a background sweep and pre-response
    freshness check consume the dirty queue via reindex_dirty(), incrementally
    re-embedding only what actually changed (content_hash comparison).
    """
    __tablename__ = "indexed_resources"
    __table_args__ = (
        UniqueConstraint("resource_type", "resource_id", name="uq_indexed_resource"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # workspace_file | rag_document | kb_folder_entry | connector_item
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    resource_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Human-readable label for search results (filename, doc title, ...)
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    # Cached extracted text used for keyword+embedding search — the source
    # tables (WorkspaceFile, connector items) don't carry embeddings
    # themselves, so this is the one place that makes every resource type
    # uniformly searchable regardless of its underlying schema.
    content_preview: Mapped[str] = mapped_column(Text, nullable=False, default="")
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding_model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # clean | dirty | indexing | error
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="dirty", index=True)
    dirty_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


# ── Cognitive Layer (Phase 2): Task Memory ────────────────────────────────────

class ProjectTask(Base):
    """
    A human work-item with an Open/In Progress/Blocked/Completed lifecycle —
    distinct from WorkspaceTask (one agent execution run against a
    workspace). Authenticated-only, same as MemoryItem.
    """
    __tablename__ = "project_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(64), nullable=False, default="general", index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # open | in_progress | blocked | completed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    workspace_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True
    )
    linked_file_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # Forward-compatible placeholder — no git integration exists yet (same
    # treatment Phase 1 gave the git-based workspace-awareness triggers).
    linked_commit_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ── Cognitive Layer (Phase 2): Knowledge Graph ────────────────────────────────
# Deliberately separate from KnowledgeNode/KnowledgeEdge above, which is an
# admin-curated document-concept graph (Manual/System/Component/Failure/...,
# gated by StudyJob approval) — a different vocabulary and workflow from the
# users/projects/files/modules/bugs/decisions/documents relationship graph
# built here.

class CognitiveNode(Base):
    """One entity in the cross-cutting relationship graph (user, project,
    file, module, bug, decision, document, conversation, or task)."""
    __tablename__ = "cognitive_nodes"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_ref", name="uq_cognitive_node"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # user | project | file | module | bug | decision | document | conversation | task
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # id of the referenced row in its own table (WorkspaceFile.id, MemoryItem.id, ...)
    entity_ref: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    module: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    # For semantic relationship traversal — cosine-ranked alongside graph edges.
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CognitiveEdge(Base):
    """Directed relationship between two CognitiveNodes."""
    __tablename__ = "cognitive_edges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    from_node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cognitive_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    to_node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cognitive_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # created_by | belongs_to | references | fixed_by | depends_on | discussed_in | ...
    relationship: Mapped[str] = mapped_column(String(64), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ── Autonomous Research Agent (Learning Hub → Autonomous Research mode) ────────
# A self-directed research "mission": generate queries from a mission statement,
# discover candidate sources (free academic APIs + curated trusted domains),
# crawl them via api.services.web_crawler.crawl(), score/dedupe, and ingest
# accepted content as ordinary RagDocument rows — the existing shared
# retrieve_chunks() path (rag_service.py, already used by chat.py and every
# other section) picks it up with zero changes to retrieval itself. Modeled on
# ProcessingJob's checkpoint/status pattern (job_runner.py) for pause/resume/
# restart safety, and on ConnectorSyncState's next_run_at polling pattern for
# continuous-learning scheduling.

class ResearchMission(Base):
    """One autonomous research job: a mission statement plus its run state."""
    __tablename__ = "research_missions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    mission_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_topic: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    # quick_scan | deep_research | continuous_learning
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="quick_scan")
    languages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)          # ["en","ar"]
    content_types: Mapped[list] = mapped_column(JSON, nullable=False, default=list)      # ["web","pdf","docx",...]
    free_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # queued | claimed | running | paused | retry_waiting | completed | stopped |
    # failed | cancelled | archived (claimed/retry_waiting/cancelled/archived
    # added in Phase 2B.2.1 — see mission_queue.py)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    current_phase: Mapped[str] = mapped_column(String(64), nullable=False, default="queued")

    # {max_pages, max_files, max_storage_mb, max_depth, min_relevance_score, min_quality_score}
    limits: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # {frequency: manual|6h|daily|weekly, next_run_at: iso str|null}
    schedule: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # {generated_queries, next_query_index, next_queue_offset, ...} — resumability, mirrors ProcessingJob.checkpoint_data
    checkpoint: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    pages_discovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_discovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_ingested: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicates_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    storage_used_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Always 0.0 in Free Mode — no paid call is ever attempted, so there is nothing to estimate.
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    # Phase 2B.1 — {auto_queue_curiosity, max_curiosity_jobs_per_mission,
    # min_knowledge_gain, min_priority, daily_curiosity_limit}. Null = use the
    # platform defaults in api.config (same "unset means default" convention
    # as `schedule` above).
    curiosity_settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ── Phase 2B.2.1 — bounded resume queue / atomic claim / provider throttle ──
    # See api.services.research_agent.mission_queue. Existing rows default to
    # priority=100 (correct — they were all user-initiated) and origin="user".
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    # user | curiosity | scheduled | test — a real stored fact set at creation
    # time, not inferred from mission_text, so "test missions never auto-resume
    # in production" is enforced by construction.
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    # Distinct from created_at — reset each time the mission re-enters the
    # queue (e.g. after a lease expires), used for ORDER BY priority, queued_at.
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    claim_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resume_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Transient | RateLimited | Authentication | Permanent | Validation |
    # Network | ProviderUnavailable | Cancelled — used for dead-letter decisions.
    last_attempt_error_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # ── Autonomous Internet Learning + Manufacturer/Scientific Intelligence (Phase 2B.5) ──
    # Mission-level coverage-target auto-continue loop — see
    # api.services.research_agent.job_runner.run_mission()'s bounded outer
    # loop and api.services.research_brain.gap_detector.aggregate_coverage().
    coverage_target: Mapped[float] = mapped_column(Float, nullable=False, default=70.0)
    max_coverage_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    coverage_rounds_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Set from ResearchPlan.normalized_understanding["matched_manufacturer"]
    # (planner.py's generalized, not-just-hardcoded-list detection) — threaded
    # into graph extraction's manufacturer hint and source_trust's
    # manufacturer-domain trust cap.
    detected_manufacturer: Mapped[str | None] = mapped_column(String(128), nullable=True)

    user: Mapped[User | None] = relationship("User")
    queue_items: Mapped[list["ResearchQueueItem"]] = relationship(
        "ResearchQueueItem", back_populates="mission", cascade="all, delete-orphan"
    )
    sources: Mapped[list["ResearchSource"]] = relationship(
        "ResearchSource", back_populates="mission", cascade="all, delete-orphan"
    )
    files: Mapped[list["ResearchFile"]] = relationship(
        "ResearchFile", back_populates="mission", cascade="all, delete-orphan"
    )
    activity_log: Mapped[list["ResearchActivityLog"]] = relationship(
        "ResearchActivityLog", back_populates="mission", cascade="all, delete-orphan"
    )


class ResearchQueueItem(Base):
    """One discovered URL pending (or done) crawling within a mission."""
    __tablename__ = "research_queue_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mission_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_missions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_domain: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    discovered_via: Mapped[str] = mapped_column(String(512), nullable=False, default="")  # query text that found it
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # pending | fetching | done | rejected | error
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Which ResearchTopic (Phase 2A research_brain plan) this URL was discovered
    # for — lets graph extraction attribute new facts back to a topic so the
    # Gap Detector can compute real per-topic coverage. Null for items enqueued
    # before Sub-Phase 2A or outside the planner (e.g. Manual Source crawls).
    topic_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_topics.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    # Phase 2B.5 — rich metadata already returned by the free academic APIs
    # (title/authors/publisher/DOI/abstract/year/citation_count/peer-review/
    # open-access), carried from discover_sources() to
    # crawler_orchestrator.process_next_queue_item() instead of being
    # discarded down to a bare URL. Null for ordinary web-discovered items.
    academic_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    mission: Mapped[ResearchMission] = relationship("ResearchMission", back_populates="queue_items")


class ResearchSource(Base):
    """A crawled/discovered source (web page or document landing page) with its quality score."""
    __tablename__ = "research_sources"
    __table_args__ = (
        UniqueConstraint("mission_id", "url", name="uq_research_source_mission_url"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mission_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_missions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    domain: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    publisher: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # 0-100
    # authoritative | high_quality | useful | low_confidence | rejected
    quality_label: Mapped[str] = mapped_column(String(24), nullable=False, default="useful")
    quality_reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    license_note: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    # False for low_confidence/rejected sources until a human approves them (never auto-merged).
    accepted_into_kb: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # ── Dynamic Source Trust (Phase 2B.3) ───────────────────────────────────
    # quality_score/quality_label above are the STATIC score (unchanged,
    # computed once at crawl time). These are the DYNAMIC and EFFECTIVE
    # layers on top of it — see api.services.source_trust.source_trust_service,
    # the only path allowed to write them.
    dynamic_trust_score: Mapped[float] = mapped_column(Float, nullable=False, default=50.0)  # 0-100, neutral start
    effective_trust_score: Mapped[float] = mapped_column(Float, nullable=False, default=50.0)  # 0-100
    # authoritative | high_trust | trusted | useful | unproven | questionable | low_trust | rejected
    trust_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unproven")
    trust_algorithm_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_trust_calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Top reasons behind the current score, for chat/API display without a
    # separate SourceTrustHistory query — e.g. [{"reason_code": ..., "delta": ...}].
    trust_signal_summary: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Deterministic independence-grouping key — content_hash if present, else
    # f"doi:{source_doi}" if extractable, else this source's own id (a family
    # of one). Never a fuzzy/invented grouping — see source_trust_service.
    source_family_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    source_doi: Mapped[str | None] = mapped_column(String(256), nullable=True)

    mission: Mapped[ResearchMission] = relationship("ResearchMission", back_populates="sources")
    files: Mapped[list["ResearchFile"]] = relationship(
        "ResearchFile", back_populates="source", cascade="all, delete-orphan"
    )


class ResearchFile(Base):
    """One ingestible unit of content found at a source (the page itself, or a linked PDF/DOCX/etc.)."""
    __tablename__ = "research_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mission_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_missions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    file_type: Mapped[str] = mapped_column(String(32), nullable=False, default="html")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    publication_date: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    detected_language: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # discovered | downloaded | rejected | duplicate | ingested | error
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="discovered")
    # False when only the link + metadata may legally be stored (no local copy retained).
    downloaded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rag_document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("rag_documents.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    mission: Mapped[ResearchMission] = relationship("ResearchMission", back_populates="files")
    source: Mapped[ResearchSource] = relationship("ResearchSource", back_populates="files")


class ResearchActivityLog(Base):
    """Append-only activity/warning/error log for a mission — backs the Activity Log / Errors tabs."""
    __tablename__ = "research_activity_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mission_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_missions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="info")  # info | warning | error
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    mission: Mapped[ResearchMission] = relationship("ResearchMission", back_populates="activity_log")


# ── Knowledge Evolution Engine (Phase 2A) ───────────────────────────────────
# Plans a mission into a ranked topic tree BEFORE any discovery/crawl happens
# (api.services.research_brain.planner), and versions the existing
# KnowledgeNode/KnowledgeEdge graph as evidence accumulates
# (api.services.research_brain.knowledge_versioning) — facts are never
# deleted, only superseded. Built on top of Phase 1's ResearchMission/
# ResearchSource, not a parallel system.

class ResearchPlan(Base):
    """The AI Research Brain's plan for one mission — built before any search happens."""
    __tablename__ = "research_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mission_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_missions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # {"normalized_topic": str, "template": "manufacturer"|"generic", "matched_manufacturer": str|None}
    normalized_understanding: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    topics: Mapped[list["ResearchTopic"]] = relationship(
        "ResearchTopic", back_populates="plan", cascade="all, delete-orphan"
    )


class ResearchTopic(Base):
    """One node in the mission's topic tree — a subtopic the plan decided to research."""
    __tablename__ = "research_topics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mission_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_missions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    parent_topic_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_topics.id", ondelete="SET NULL"), nullable=True
    )
    rank: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    dependencies: Mapped[list] = mapped_column(JSON, nullable=False, default=list)  # list of topic ids
    # pending | researching | covered | gap
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # {expected_sources, expected_pdfs, expected_manuals, expected_standards,
    #  expected_papers, expected_duration_minutes, expected_knowledge_gain}
    estimates: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    research_questions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # {"queries": [...], "source_type_priority": [...]}
    search_strategy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    coverage_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    # Phase 2B.4 — links this mission-scoped topic to its cross-mission
    # TopicResearchMemory row (matched/created by normalized topic_key at
    # plan time). Nullable/additive: pre-2B.4 topics simply have no memory.
    topic_memory_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("topic_research_memory.id", ondelete="SET NULL"), nullable=True, index=True
    )

    plan: Mapped[ResearchPlan] = relationship("ResearchPlan", back_populates="topics")


class KnowledgeEvidence(Base):
    """Links a KnowledgeNode or KnowledgeEdge to a ResearchSource that supports or conflicts with it."""
    __tablename__ = "knowledge_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # Exactly one of node_id/edge_id is set.
    node_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=True, index=True
    )
    edge_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_edges.id", ondelete="CASCADE"), nullable=True, index=True
    )
    research_source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # True = this source supports the fact; False = this source conflicts with it.
    supports: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CuriosityQuestion(Base):
    """A self-generated research question — the Curiosity Engine (Phase 2B.1).

    Generated deterministically after a mission completes (gap-driven from
    api.services.research_brain.gap_detector, or from an unexplained-term
    scan), never auto-executed without limits — see
    api.services.research_brain.curiosity_engine.apply_curiosity_settings().
    A Queued question spawns an ordinary ResearchMission (spawned_mission_id)
    through the exact same path a user-started mission uses.
    """
    __tablename__ = "curiosity_questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mission_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_missions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    related_topic_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_topics.id", ondelete="SET NULL"), nullable=True
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_reference: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    # Missing | Weakly Covered | Outdated | Conflicting | Mentioned but Unexplained | Needs Verification
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="Missing")
    priority_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    expected_knowledge_gain: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Same shape as ResearchTopic.estimates.
    estimated_research_cost: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    estimated_storage_mb: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Suggested | Approved | Queued | Researching | Resolved | Rejected | Deferred
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="Suggested")
    spawned_mission_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_missions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


# ── Knowledge Governance Layer (Phase 2B.2) ─────────────────────────────────
# api.services.knowledge_governance.governance_service.KnowledgeGovernanceService
# is the ONLY path allowed to write to KnowledgeNode/KnowledgeEdge — both
# existing write sites (research_brain.knowledge_versioning and
# study_service.approve_study_job) are retrofitted to delegate to it rather
# than writing directly. These three tables are what it writes alongside
# every fact/edge change; none of them replace or alter KnowledgeNode/Edge.

class KnowledgeProvenance(Base):
    """Where a fact/edge came from — recorded on every governance write.

    Fields the current extraction pipeline cannot supply (page/section/
    paragraph/sentence_offset — no extractor produces this granularity yet)
    are left null rather than invented.
    """
    __tablename__ = "knowledge_provenance"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    node_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=True, index=True
    )
    edge_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_edges.id", ondelete="CASCADE"), nullable=True, index=True
    )
    mission_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_missions.id", ondelete="SET NULL"), nullable=True
    )
    source_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_sources.id", ondelete="SET NULL"), nullable=True
    )
    # local_ollama | deterministic | paid_provider (Phase 2B.0 vocabulary, reused)
    provider_used: Mapped[str | None] = mapped_column(String(24), nullable=True)
    # The specific function/module that produced this write, e.g.
    # "deterministic_extraction.deterministic_extract" or "study_service.approve_study_job"
    extractor_used: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    knowledge_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    original_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    original_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    document_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String(512), nullable=True)
    paragraph: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sentence_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_service: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence_at_write: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class KnowledgeConflict(Base):
    """A detected disagreement between claims about the same subject.

    Neither claim is ever deleted — both claim_a/claim_b persist here
    regardless of resolution_status. Safety-critical subjects always carry
    human_review_required=True, unconditionally (api.services.knowledge_governance
    .conflict_resolver.SAFETY_KEYWORDS), regardless of type or severity.
    """
    __tablename__ = "knowledge_conflicts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    subject_node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    predicate: Mapped[str] = mapped_column(String(256), nullable=False, default="description")
    claim_a: Mapped[str] = mapped_column(Text, nullable=False)
    claim_b: Mapped[str] = mapped_column(Text, nullable=False)
    source_a_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_sources.id", ondelete="SET NULL"), nullable=True
    )
    source_b_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_sources.id", ondelete="SET NULL"), nullable=True
    )
    # Numerical | Procedural | Historical | Version | Safety | Terminology | Manufacturer | Standard | Source
    conflict_type: Mapped[str] = mapped_column(String(32), nullable=False, default="Terminology")
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")  # low|medium|high|critical
    # Open | Automatically Resolved | Needs Review | Accepted Difference | Superseded | Unresolvable
    resolution_status: Mapped[str] = mapped_column(String(32), nullable=False, default="Open")
    recommended_interpretation: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class KnowledgeAuditLog(Base):
    """Immutable, append-only record of every KnowledgeGovernanceService
    operation. No update/delete CRUD helper exists for this table anywhere
    in the codebase, by design — that omission is what "no deletion from
    the audit trail" means in practice."""
    __tablename__ = "knowledge_audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    node_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_nodes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    edge_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_edges.id", ondelete="SET NULL"), nullable=True, index=True
    )
    service: Mapped[str] = mapped_column(String(64), nullable=False)
    # create_fact | update_fact | version_fact | create_edge | update_edge |
    # register_evidence | archive_fact | rollback
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    old_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    mission_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_missions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


# ── Dynamic Source Trust (Phase 2B.3) ───────────────────────────────────────

class SourceTrustHistory(Base):
    """Immutable, append-only record of every trust-score change. No
    update/delete CRUD helper exists for this table anywhere in the
    codebase, by design — same enforcement-by-omission convention as
    KnowledgeAuditLog above."""
    __tablename__ = "source_trust_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    old_static_score: Mapped[float] = mapped_column(Float, nullable=False)
    new_static_score: Mapped[float] = mapped_column(Float, nullable=False)
    old_dynamic_score: Mapped[float] = mapped_column(Float, nullable=False)
    new_dynamic_score: Mapped[float] = mapped_column(Float, nullable=False)
    old_effective_score: Mapped[float] = mapped_column(Float, nullable=False)
    new_effective_score: Mapped[float] = mapped_column(Float, nullable=False)
    delta: Mapped[float] = mapped_column(Float, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(48), nullable=False)
    reason_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    related_mission_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_missions.id", ondelete="SET NULL"), nullable=True
    )
    related_evidence_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_evidence.id", ondelete="SET NULL"), nullable=True
    )
    related_conflict_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_conflicts.id", ondelete="SET NULL"), nullable=True
    )
    related_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    service_name: Mapped[str] = mapped_column(String(64), nullable=False)
    calculation_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class SourceUserReview(Base):
    """One row per (source_id, user_id) — re-reviewing upserts this row.
    The append-only trail of what a review DID to trust lives in
    SourceTrustHistory, not here; this table only holds current state."""
    __tablename__ = "source_user_reviews"
    __table_args__ = (
        UniqueConstraint("source_id", "user_id", name="uq_source_user_review"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # Trusted | Useful | Questionable | Rejected — null means reset (no active review).
    review_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class TrustRecalculationJob(Base):
    """Bounded work queue for trust recalculation — same atomic-claim
    pattern as ResearchMission's resume queue (Phase 2B.2.1), a distinct
    small worker rather than forcing this job type through
    MissionQueueManager (which is coupled to ResearchMission's own state
    machine)."""
    __tablename__ = "trust_recalculation_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    research_source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # pending | claimed | running | completed | failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    reason: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claim_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


# ── Research Memory & Knowledge Freshness (Phase 2B.4) ──────────────────────
# Cross-mission memory for a *logical* topic (keyed by a normalized topic
# label, see api.services.research_brain.research_memory.normalize_topic_key),
# distinct from ResearchTopic which is per-mission bookkeeping. Every mission
# that plans "the same" topic links its ResearchTopic row here via
# topic_memory_id and accumulates into the SAME row, which is what lets the
# next research pass be incremental instead of starting from scratch.

class TopicResearchMemory(Base):
    """What the system already knows it has researched for one logical topic."""
    __tablename__ = "topic_research_memory"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    topic_key: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)
    # Standards | Manuals | Research Papers | Manufacturer Docs | Safety Documents
    content_category: Mapped[str] = mapped_column(String(32), nullable=False, default="Manuals")
    last_research: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_update: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    search_queries: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    providers_used: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # Bounded recent-activity list: [{url, content_hash, etag, last_modified, visited_at}, ...]
    # NOT the source of truth for dedup (DocumentHash/ResearchSource are) —
    # this is just enough to skip known-unchanged URLs and show recent activity.
    visited_sources: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    downloaded_files_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_hashes_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extracted_graph_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generated_embeddings_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_facts_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_facts_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conflicts_found_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    knowledge_gain: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    next_refresh: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    # Fresh | Acceptable | Aging | Outdated | Unknown
    freshness_status: Mapped[str] = mapped_column(String(16), nullable=False, default="Unknown", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


# ── Proactive AI Scientist (Phase 2B.8) ─────────────────────────────────────
# Surfaces what the platform already learns (gap_detector, curiosity_engine,
# research_memory, governance provenance/trust — all pre-existing) without
# any new discovery pipeline. Written only by
# api.services.research_brain.ai_scientist.classify_and_alert() /
# sweep_for_new_missions() / maybe_generate_weekly_brief().

class ScientificAlert(Base):
    """One proactively surfaced, documented finding — never a raw claim:
    every alert carries the KnowledgeNode/ResearchSource ids it was derived
    from (related_node_ids/related_source_ids) so it can always be traced
    back to real, already-governed graph content."""
    __tablename__ = "scientific_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # Scientific Alert | Weekly Research Brief | Technology Update |
    # Knowledge Gap | Training Impact | Suggested Research Question
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # Dedup key — api.services.research_brain.research_memory.normalize_topic_key()
    # of the discovery's subject, same keying convention TopicResearchMemory
    # already uses for "is this the same topic" comparisons.
    topic_key: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    mission_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_missions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    related_node_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    related_source_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # Lowest effective_trust_score among cited sources — lets the summary
    # (and any future UI) badge a low-trust finding as unproven rather than
    # present it as settled fact.
    min_trust_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # New | Read | Dismissed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="New")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


# ── Knowledge Health (Phase 2B.9) ───────────────────────────────────────────
# A cached, periodically-refreshed score per scope — read-only aggregation
# over signals every prior phase already produces (coverage, freshness,
# trust, conflicts, provenance, extraction failures, curiosity questions).
# Written only by api.services.research_brain.knowledge_health.run_health_audit()
# on the existing MissionScheduler tick; chat/API reads are cache reads of
# this table, never live recomputation, so Knowledge Health can never slow
# down AI Chat regardless of how large the graph gets.

class KnowledgeHealthSnapshot(Base):
    """One scope's most recent health score. Upserted (not appended) per
    scope_type+scope_key — this table holds the LATEST view, not a history."""
    __tablename__ = "knowledge_health_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # Domain | Topic | Manufacturer | Product | Overall
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # content_category / TopicResearchMemory.topic_key / manufacturer label /
    # product KnowledgeNode id / "overall" — unique together with scope_type.
    scope_key: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    scope_label: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Healthy | Good | Needs Attention | Weak | Critical | Unknown
    classification: Mapped[str] = mapped_column(String(16), nullable=False, default="Unknown", index=True)
    # Raw per-factor breakdown (coverage/freshness/trust/conflicts/etc.) —
    # every number in the score traces back to something in here.
    signals: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    recommended_actions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


# ── Autonomous Internet Learning + Manufacturer/Scientific Intelligence (Phase 2B.5) ──
# Structured per-paper/thesis metadata — 1:1 with a ResearchSource whose
# discovery came from the free academic APIs (perform_hybrid_external_research)
# rather than a bare web crawl. Populated by
# api.services.research_brain.paper_extraction.py's deterministic section
# extractor, called from crawler_orchestrator.py only for open-access
# sources (never for paywalled content — see is_open_access below, which
# mirrors the ExternalSource field of the same name that gated ingestion in
# the first place).

class AcademicPaperMetadata(Base):
    """Structured knowledge extracted from one academic paper/thesis —
    not just the abstract. Never stores full paywalled text; is_open_access
    records what was actually legally available at ingestion time."""
    __tablename__ = "academic_paper_metadata"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    research_source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_sources.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    title: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    authors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    institution_or_journal: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    degree_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    publication_year: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    doi_or_repo_id: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    abstract: Mapped[str] = mapped_column(Text, nullable=False, default="")
    research_problem: Mapped[str] = mapped_column(Text, nullable=False, default="")
    methodology: Mapped[str] = mapped_column(Text, nullable=False, default="")
    equipment_components: Mapped[str] = mapped_column(Text, nullable=False, default="")
    results: Mapped[str] = mapped_column(Text, nullable=False, default="")
    limitations: Mapped[str] = mapped_column(Text, nullable=False, default="")
    future_work: Mapped[str] = mapped_column(Text, nullable=False, default="")
    citations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_open_access: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SiteVisit(Base):
    """One row per (visitor, day) — lightweight anonymous visit counter.

    Powers the admin dashboard's visitor metric without any user login. The
    visitor id is a random first-party cookie value (no personal data). A unique
    (visitor_id, day) constraint means each browser counts once per calendar day.
    """
    __tablename__ = "site_visit"
    __table_args__ = (UniqueConstraint("visitor_id", "day", name="uq_visit_visitor_day"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    visitor_id: Mapped[str] = mapped_column(String(64), index=True)
    day: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD (UTC)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
