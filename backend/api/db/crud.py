"""CRUD operations for all database models."""
from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, func, or_, update

from .models import (
    User, Conversation, Message, LinkedInPost, XrayAnalysis, RagDocument, ResearchOutput,
    ResearchPipelineRun, RagImage, RagPage,
    Workspace, WorkspaceFile, WorkspaceTask, TaskEvent, GeneratedFile,
    Connector, UserConnectorAccount, ConnectorEvent, ConnectorSyncState, DesignWorkflow,
    MemoryItem, ConversationSummary, IndexedResource,
    ProjectTask, CognitiveNode, CognitiveEdge,
    AgentRun, AgentStep, AgentArtifact,
    ResearchMission, ResearchQueueItem, ResearchSource, ResearchFile, ResearchActivityLog,
    ResearchPlan, ResearchTopic, KnowledgeEvidence, KnowledgeNode, KnowledgeEdge,
    CuriosityQuestion,
    KnowledgeProvenance, KnowledgeConflict, KnowledgeAuditLog,
    SourceTrustHistory, SourceUserReview, TrustRecalculationJob,
    TopicResearchMemory,
    AcademicPaperMetadata,
    ScientificAlert,
    KnowledgeHealthSnapshot,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uid() -> str:
    return str(uuid.uuid4())


# ──────────────────────────────────────────────────────────
# Users
# ──────────────────────────────────────────────────────────

def upsert_user(db: Session, user_id: str, username: str, name: Optional[str] = None, profile_image: Optional[str] = None) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.username = username
        if name:
            user.name = name
        if profile_image:
            user.profile_image = profile_image
    else:
        user = User(id=user_id, username=username, name=name, profile_image=profile_image)
        db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user(db: Session, user_id: str) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


# ──────────────────────────────────────────────────────────
# Conversations
# ──────────────────────────────────────────────────────────

def create_conversation(
    db: Session,
    user_id: Optional[str] = None,
    title: Optional[str] = None,
    anon_session_id: Optional[str] = None,
) -> Conversation:
    conv = Conversation(
        id=_uid(), user_id=user_id, anon_session_id=(anon_session_id if not user_id else None),
        title=title or "New Conversation",
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def get_conversation(db: Session, conversation_id: str) -> Optional[Conversation]:
    return db.query(Conversation).filter(Conversation.id == conversation_id).first()


def list_conversations(
    db: Session,
    user_id: Optional[str] = None,
    anon_session_id: Optional[str] = None,
) -> List[Conversation]:
    """
    Authenticated callers pass user_id and see only their own conversations.
    Anonymous callers pass anon_session_id and see only that browser
    session's conversations — never the shared user_id=NULL bucket.
    """
    q = db.query(Conversation)
    if user_id:
        q = q.filter(Conversation.user_id == user_id)
    elif anon_session_id:
        q = q.filter(Conversation.anon_session_id == anon_session_id)
    else:
        # No identity at all — isolate to nothing rather than leaking every
        # anonymous visitor's conversations into one list.
        return []
    return q.order_by(desc(Conversation.updated_at)).all()


def delete_conversation(db: Session, conversation_id: str) -> bool:
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        return False
    db.delete(conv)
    db.commit()
    return True


def add_message(db: Session, conversation_id: str, role: str, content: str, image_url: Optional[str] = None) -> Message:
    msg = Message(id=_uid(), conversation_id=conversation_id, role=role, content=content, image_url=image_url)
    db.add(msg)
    # Update conversation title from first user message
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if conv and role == "user" and conv.title == "New Conversation":
        conv.title = content[:80] + ("…" if len(content) > 80 else "")
    if conv:
        conv.updated_at = _now()
    db.commit()
    db.refresh(msg)
    return msg


def get_messages(db: Session, conversation_id: str) -> List[Message]:
    return db.query(Message).filter(Message.conversation_id == conversation_id).order_by(Message.created_at).all()


def get_message(db: Session, message_id: str) -> Optional[Message]:
    return db.query(Message).filter(Message.id == message_id).first()


def conversation_to_dict(conv: Conversation) -> dict:
    msgs = conv.messages
    return {
        "id": conv.id,
        "title": conv.title,
        "created_at": conv.created_at.isoformat(),
        "message_count": len(msgs),
        "last_message": msgs[-1].content[:100] if msgs else None,
        "workspace_id": conv.workspace_id,
    }


# ──────────────────────────────────────────────────────────
# LinkedIn Posts
# ──────────────────────────────────────────────────────────

def create_linkedin_post(db: Session, user_id: Optional[str], topic: str, tone: str, length: str, content: str, hashtags: List[str]) -> LinkedInPost:
    post = LinkedInPost(id=_uid(), user_id=user_id, topic=topic, tone=tone, length=length, content=content, hashtags=hashtags)
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


def list_linkedin_posts(db: Session, user_id: Optional[str] = None) -> List[LinkedInPost]:
    q = db.query(LinkedInPost)
    if user_id:
        q = q.filter(LinkedInPost.user_id == user_id)
    return q.order_by(desc(LinkedInPost.created_at)).all()


def delete_linkedin_post(db: Session, post_id: str) -> bool:
    post = db.query(LinkedInPost).filter(LinkedInPost.id == post_id).first()
    if not post:
        return False
    db.delete(post)
    db.commit()
    return True


def linkedin_post_to_dict(post: LinkedInPost) -> dict:
    return {
        "id": post.id,
        "topic": post.topic,
        "tone": post.tone,
        "length": post.length,
        "content": post.content,
        "hashtags": post.hashtags or [],
        "created_at": post.created_at.isoformat(),
    }


# ──────────────────────────────────────────────────────────
# X-ray Analyses
# ──────────────────────────────────────────────────────────

def create_xray_analysis(db: Session, user_id: Optional[str], filename: str, scanner_type: str,
                          findings: str, threat_level: str, recommendations: List[str], image_url: Optional[str] = None) -> XrayAnalysis:
    analysis = XrayAnalysis(
        id=_uid(), user_id=user_id, filename=filename, scanner_type=scanner_type,
        findings=findings, threat_level=threat_level, recommendations=recommendations, image_url=image_url
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


def list_xray_analyses(db: Session, user_id: Optional[str] = None) -> List[XrayAnalysis]:
    q = db.query(XrayAnalysis)
    if user_id:
        q = q.filter(XrayAnalysis.user_id == user_id)
    return q.order_by(desc(XrayAnalysis.created_at)).all()


def delete_xray_analysis(db: Session, analysis_id: str) -> bool:
    a = db.query(XrayAnalysis).filter(XrayAnalysis.id == analysis_id).first()
    if not a:
        return False
    db.delete(a)
    db.commit()
    return True


def xray_analysis_to_dict(a: XrayAnalysis) -> dict:
    return {
        "id": a.id,
        "filename": a.filename,
        "scanner_type": a.scanner_type,
        "findings": a.findings,
        "threat_level": a.threat_level,
        "recommendations": a.recommendations or [],
        "image_url": a.image_url,
        "created_at": a.created_at.isoformat(),
    }


# ──────────────────────────────────────────────────────────
# RAG Documents
# ──────────────────────────────────────────────────────────

def create_rag_document(db: Session, user_id: Optional[str], filename: str,
                         document_type: str, content: str,
                         embedding: Optional[List[float]] = None,
                         status: str = "ready") -> RagDocument:
    doc = RagDocument(
        id=_uid(), user_id=user_id, filename=filename,
        document_type=document_type, content=content,
        embedding=embedding, word_count=len(content.split()),
        status=status,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Hybrid Workspace Awareness trigger #10 (Knowledge Base updates) and a
    # safety net for automatic document indexing generally: every RagDocument
    # creation path (regular /rag uploads, knowledge_library folder scans)
    # goes through this one function, so the background sweep will pick up
    # and embed any document whose caller forgot to fire embed_and_store.
    from api.services.workspace_index import mark_dirty
    mark_dirty(db, "rag_document", doc.id, reason="document_created")

    # Cognitive Layer (Phase 2): Knowledge Graph — document uploaded_by user.
    if user_id:
        from api.services import graph_service
        from api.services.identity import MemoryScope
        scope = MemoryScope(user_id=user_id, anon_session_id=None, is_persistent=True)
        graph_service.link_sync(
            db, scope, ("document", doc.id), ("user", user_id), relationship="uploaded_by",
            from_label=filename,
        )

    return doc


def list_rag_documents(db: Session, user_id: Optional[str] = None) -> List[RagDocument]:
    q = db.query(RagDocument)
    if user_id:
        q = q.filter(RagDocument.user_id == user_id)
    return q.order_by(desc(RagDocument.created_at)).all()


def get_all_rag_documents(db: Session) -> List[RagDocument]:
    """Load all documents for retrieval (no user filter — shared knowledge base)."""
    return db.query(RagDocument).order_by(RagDocument.created_at).all()


def update_rag_document(
    db: Session,
    doc_id: str,
    filename: Optional[str] = None,
    document_type: Optional[str] = None,
    content: Optional[str] = None,
) -> Optional[RagDocument]:
    doc = db.query(RagDocument).filter(RagDocument.id == doc_id).first()
    if not doc:
        return None
    if filename is not None:
        doc.filename = filename
    if document_type is not None:
        doc.document_type = document_type
    if content is not None:
        doc.content = content
        doc.word_count = len(content.split())
        doc.embedding = None  # invalidate embedding so it is regenerated
    db.commit()
    db.refresh(doc)
    return doc


def delete_rag_document(db: Session, doc_id: str) -> bool:
    doc = db.query(RagDocument).filter(RagDocument.id == doc_id).first()
    if not doc:
        return False
    db.delete(doc)
    db.commit()
    return True


# ──────────────────────────────────────────────────────────
# RAG Images
# ──────────────────────────────────────────────────────────

def store_rag_image(
    db: Session,
    doc_id: str,
    doc_filename: str,
    filename: str,
    page_num: int,
    image_index: int,
    image_data: bytes,
    mime_type: str = "image/jpeg",
    image_sha256: Optional[str] = None,
    vision_skipped: bool = False,
    skip_reason: Optional[str] = None,
) -> RagImage:
    img = RagImage(
        id=_uid(),
        doc_id=doc_id,
        doc_filename=doc_filename,
        filename=filename,
        page_num=page_num,
        image_index=image_index,
        image_data=image_data,
        mime_type=mime_type,
        image_sha256=image_sha256,
        vision_skipped=vision_skipped,
        skip_reason=skip_reason,
    )
    db.add(img)
    db.commit()
    db.refresh(img)
    return img


def get_all_rag_images(db: Session) -> List[RagImage]:
    """Return all extracted images across all documents (shared knowledge base)."""
    return db.query(RagImage).order_by(RagImage.created_at).all()


def get_rag_image(db: Session, image_id: str) -> Optional[RagImage]:
    return db.query(RagImage).filter(RagImage.id == image_id).first()


def update_rag_image_embedding(
    db: Session,
    image_id: str,
    caption: str,
    embedding: Optional[List[float]],
) -> Optional[RagImage]:
    img = db.query(RagImage).filter(RagImage.id == image_id).first()
    if not img:
        return None
    img.caption = caption
    img.embedding = embedding
    db.commit()
    db.refresh(img)
    return img


# ──────────────────────────────────────────────────────────
# RagPage (ColPali visual index)
# ──────────────────────────────────────────────────────────

def create_rag_page(
    db: Session,
    *,
    doc_id: str,
    doc_filename: str,
    page_num: int,
    image_data: bytes,
) -> "RagPage":
    from api.db.models import RagPage
    page = RagPage(
        doc_id=doc_id,
        doc_filename=doc_filename,
        page_num=page_num,
        image_data=image_data,
    )
    db.add(page)
    db.commit()
    db.refresh(page)
    return page


def get_rag_page(db: Session, page_id: str) -> Optional["RagPage"]:
    from api.db.models import RagPage
    return db.query(RagPage).filter(RagPage.id == page_id).first()


def get_all_rag_pages(db: Session) -> List["RagPage"]:
    from api.db.models import RagPage
    return db.query(RagPage).order_by(RagPage.doc_filename, RagPage.page_num).all()


def update_rag_page_vecs(
    db: Session,
    page_id: str,
    colpali_vecs: List[List[float]],
    backend: str = "",
) -> Optional["RagPage"]:
    from api.db.models import RagPage
    page = db.query(RagPage).filter(RagPage.id == page_id).first()
    if not page:
        return None
    page.colpali_vecs = colpali_vecs
    page.backend = backend
    db.commit()
    db.refresh(page)
    return page


def rag_document_to_dict(doc: RagDocument) -> dict:
    return {
        "id": doc.id,
        "filename": doc.filename,
        "document_type": doc.document_type,
        "content_preview": doc.content[:300] + ("…" if len(doc.content) > 300 else ""),
        "word_count": doc.word_count,
        "status": getattr(doc, "status", "ready"),
        "vision_estimate": getattr(doc, "vision_estimate", None),
        "created_at": doc.created_at.isoformat(),
    }


# ──────────────────────────────────────────────────────────
# Research Outputs
# ──────────────────────────────────────────────────────────

def create_research_output(
    db: Session,
    output_id: str,
    user_id: Optional[str],
    mode: str,
    topic: str,
    content: str,
    kb_chunks_used: int = 0,
    readiness_meta: Optional[dict] = None,
) -> ResearchOutput:
    out = ResearchOutput(
        id=output_id,
        user_id=user_id,
        mode=mode,
        topic=topic,
        content=content,
        word_count=len(content.split()),
        kb_chunks_used=kb_chunks_used,
        readiness_meta=readiness_meta,
    )
    db.add(out)
    db.commit()
    db.refresh(out)
    return out


def list_research_outputs(
    db: Session, user_id: Optional[str] = None
) -> List[ResearchOutput]:
    q = db.query(ResearchOutput)
    if user_id:
        q = q.filter(ResearchOutput.user_id == user_id)
    return q.order_by(desc(ResearchOutput.created_at)).all()


def delete_research_output(db: Session, output_id: str) -> bool:
    out = db.query(ResearchOutput).filter(ResearchOutput.id == output_id).first()
    if not out:
        return False
    db.delete(out)
    db.commit()
    return True


def research_output_to_dict(out: ResearchOutput) -> dict:
    from api.services.research_service import RESEARCH_MODE_LABELS
    return {
        "id": out.id,
        "mode": out.mode,
        "mode_label": RESEARCH_MODE_LABELS.get(out.mode, out.mode),
        "topic": out.topic,
        "content": out.content,
        "word_count": out.word_count,
        "created_at": out.created_at.isoformat(),
    }


# ──────────────────────────────────────────────────────────
# Research Pipeline Runs (Phase 1)
# ──────────────────────────────────────────────────────────

def create_research_pipeline_run(
    db: Session,
    *,
    run_id: str,
    user_id: Optional[str],
    mode: str,
    topic: str,
    normalized_topic: str,
    artifacts: dict,
    status: str = "running",
    current_stage: str = "topic_normalization",
) -> ResearchPipelineRun:
    run = ResearchPipelineRun(
        id=run_id,
        user_id=user_id,
        mode=mode,
        topic=topic,
        normalized_topic=normalized_topic,
        status=status,
        current_stage=current_stage,
        artifacts=artifacts,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_research_pipeline_run(db: Session, run_id: str) -> Optional[ResearchPipelineRun]:
    return db.query(ResearchPipelineRun).filter(ResearchPipelineRun.id == run_id).first()


def list_research_pipeline_runs(db: Session, user_id: Optional[str] = None) -> List[ResearchPipelineRun]:
    q = db.query(ResearchPipelineRun)
    if user_id:
        q = q.filter(ResearchPipelineRun.user_id == user_id)
    return q.order_by(desc(ResearchPipelineRun.created_at)).all()


def update_research_pipeline_run(
    db: Session,
    run_id: str,
    *,
    artifacts: Optional[dict] = None,
    status: Optional[str] = None,
    current_stage: Optional[str] = None,
    normalized_topic: Optional[str] = None,
    last_error: Optional[str] = None,
) -> Optional[ResearchPipelineRun]:
    run = get_research_pipeline_run(db, run_id)
    if not run:
        return None
    if artifacts is not None:
        run.artifacts = artifacts
    if status is not None:
        run.status = status
    if current_stage is not None:
        run.current_stage = current_stage
    if normalized_topic is not None:
        run.normalized_topic = normalized_topic
    if last_error is not None:
        run.last_error = last_error
    db.commit()
    db.refresh(run)
    return run


# ──────────────────────────────────────────────────────────
# AI Chat Workspace (file/folder agent workspace)
# ──────────────────────────────────────────────────────────

def create_workspace(db: Session, user_id: str, name: str = "Workspace", conversation_id: Optional[str] = None) -> Workspace:
    ws = Workspace(id=_uid(), user_id=user_id, name=name, conversation_id=conversation_id)
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws


def get_workspace(db: Session, workspace_id: str, user_id: str) -> Optional[Workspace]:
    """Always scoped to the owning user — the sole per-request ownership check."""
    return db.query(Workspace).filter(Workspace.id == workspace_id, Workspace.user_id == user_id).first()


def list_workspaces(db: Session, user_id: str) -> List[Workspace]:
    return db.query(Workspace).filter(Workspace.user_id == user_id).order_by(desc(Workspace.updated_at)).all()


def touch_workspace(db: Session, workspace_id: str) -> None:
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if ws:
        ws.updated_at = _now()
        db.commit()


def recompute_workspace_totals(db: Session, workspace_id: str) -> None:
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        return
    files = db.query(WorkspaceFile).filter(WorkspaceFile.workspace_id == workspace_id).all()
    ws.total_files = len(files)
    ws.total_size_bytes = sum(f.size_bytes for f in files)
    ws.updated_at = _now()
    db.commit()


def delete_workspace(db: Session, workspace_id: str, user_id: str) -> bool:
    ws = get_workspace(db, workspace_id, user_id)
    if not ws:
        return False
    db.delete(ws)
    db.commit()
    return True


def link_conversation_workspace(db: Session, conversation_id: str, workspace_id: str) -> None:
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if conv:
        conv.workspace_id = workspace_id
        db.commit()


def add_workspace_file(
    db: Session,
    workspace_id: str,
    *,
    relative_path: str,
    original_filename: str,
    mime_type: str,
    extension: str,
    size_bytes: int,
    checksum: str,
    storage_path: str,
) -> WorkspaceFile:
    wf = WorkspaceFile(
        id=_uid(), workspace_id=workspace_id, relative_path=relative_path,
        original_filename=original_filename, mime_type=mime_type, extension=extension,
        size_bytes=size_bytes, checksum=checksum, storage_path=storage_path,
        parse_status="pending",
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)

    # Hybrid Workspace Awareness triggers #1 (file uploaded) and #4 (folder
    # imported, incl. zip-extracted entries) — single choke point since every
    # file-add path (direct upload, zip extraction) goes through this function.
    # Lazy import: workspace_index imports this module, so importing it here
    # at call time (not module load time) avoids a circular import.
    from api.services.workspace_index import mark_dirty
    mark_dirty(db, "workspace_file", wf.id, workspace_id, reason="upload")

    # Cognitive Layer (Phase 2): Knowledge Graph — file belongs_to project
    # (Workspace maps to "project" in the users/projects/files/modules/bugs/
    # decisions/documents vocabulary). Same single-choke-point pattern as
    # mark_dirty above.
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if ws and ws.user_id:
        from api.services import graph_service
        from api.services.identity import MemoryScope
        scope = MemoryScope(user_id=ws.user_id, anon_session_id=None, is_persistent=True)
        graph_service.link_sync(
            db, scope, ("file", wf.id), ("project", workspace_id), relationship="belongs_to",
            from_label=original_filename, to_label=ws.name,
        )

    return wf


def get_workspace_file(db: Session, file_id: str, workspace_id: str) -> Optional[WorkspaceFile]:
    return db.query(WorkspaceFile).filter(WorkspaceFile.id == file_id, WorkspaceFile.workspace_id == workspace_id).first()


def list_workspace_files(db: Session, workspace_id: str) -> List[WorkspaceFile]:
    return db.query(WorkspaceFile).filter(WorkspaceFile.workspace_id == workspace_id).order_by(WorkspaceFile.relative_path).all()


def update_workspace_file_status(
    db: Session,
    file_id: str,
    *,
    parse_status: str,
    extracted_text_path: Optional[str] = None,
    errors: Optional[List[str]] = None,
    warnings: Optional[List[str]] = None,
) -> Optional[WorkspaceFile]:
    wf = db.query(WorkspaceFile).filter(WorkspaceFile.id == file_id).first()
    if not wf:
        return None
    wf.parse_status = parse_status
    if extracted_text_path is not None:
        wf.extracted_text_path = extracted_text_path
    if errors is not None:
        wf.errors = errors
    if warnings is not None:
        wf.warnings = warnings
    db.commit()
    db.refresh(wf)
    return wf


def delete_workspace_file(db: Session, file_id: str, workspace_id: str) -> bool:
    wf = get_workspace_file(db, file_id, workspace_id)
    if not wf:
        return False
    db.delete(wf)
    db.commit()
    return True


def workspace_file_to_dict(wf: WorkspaceFile) -> dict:
    return {
        "id": wf.id,
        "workspace_id": wf.workspace_id,
        "relative_path": wf.relative_path,
        "original_filename": wf.original_filename,
        "mime_type": wf.mime_type,
        "extension": wf.extension,
        "size_bytes": wf.size_bytes,
        "checksum": wf.checksum,
        "parse_status": wf.parse_status,
        "errors": wf.errors or [],
        "warnings": wf.warnings or [],
        "created_at": wf.created_at.isoformat(),
    }


def workspace_to_dict(ws: Workspace) -> dict:
    return {
        "id": ws.id,
        "user_id": ws.user_id,
        "conversation_id": ws.conversation_id,
        "name": ws.name,
        "status": ws.status,
        "total_files": ws.total_files,
        "total_size_bytes": ws.total_size_bytes,
        "created_at": ws.created_at.isoformat(),
        "updated_at": ws.updated_at.isoformat(),
    }


def create_task(db: Session, workspace_id: str, user_instruction: str, conversation_id: Optional[str] = None) -> WorkspaceTask:
    task = WorkspaceTask(
        id=_uid(), workspace_id=workspace_id, conversation_id=conversation_id,
        user_instruction=user_instruction, status="queued",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_task(db: Session, task_id: str, workspace_id: str) -> Optional[WorkspaceTask]:
    return db.query(WorkspaceTask).filter(WorkspaceTask.id == task_id, WorkspaceTask.workspace_id == workspace_id).first()


def update_task_status(
    db: Session, task_id: str, status: str,
    plan: Optional[List[dict]] = None, result_summary: Optional[str] = None,
) -> Optional[WorkspaceTask]:
    task = db.query(WorkspaceTask).filter(WorkspaceTask.id == task_id).first()
    if not task:
        return None
    task.status = status
    if plan is not None:
        task.plan = plan
    if result_summary is not None:
        task.result_summary = result_summary
    task.updated_at = _now()
    db.commit()
    db.refresh(task)
    return task


def append_task_event(db: Session, task_id: str, event_type: str, message: str, payload: Optional[dict] = None) -> TaskEvent:
    ev = TaskEvent(id=_uid(), task_id=task_id, event_type=event_type, message=message, payload=payload)
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def list_task_events(db: Session, task_id: str) -> List[TaskEvent]:
    return db.query(TaskEvent).filter(TaskEvent.task_id == task_id).order_by(TaskEvent.created_at).all()


def task_to_dict(task: WorkspaceTask, include_events: bool = False) -> dict:
    d = {
        "id": task.id,
        "workspace_id": task.workspace_id,
        "conversation_id": task.conversation_id,
        "user_instruction": task.user_instruction,
        "status": task.status,
        "plan": task.plan or [],
        "result_summary": task.result_summary,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }
    if include_events:
        d["events"] = [
            {"id": e.id, "event_type": e.event_type, "message": e.message, "payload": e.payload, "created_at": e.created_at.isoformat()}
            for e in task.events
        ]
    return d


def add_generated_file(
    db: Session, workspace_id: str, *, filename: str, format: str, storage_path: str,
    size_bytes: int, task_id: Optional[str] = None, source_file_ids: Optional[List[str]] = None,
) -> GeneratedFile:
    gf = GeneratedFile(
        id=_uid(), workspace_id=workspace_id, task_id=task_id, filename=filename, format=format,
        storage_path=storage_path, size_bytes=size_bytes, source_file_ids=source_file_ids or [],
    )
    db.add(gf)
    db.commit()
    db.refresh(gf)
    return gf


def get_generated_file(db: Session, file_id: str, workspace_id: str) -> Optional[GeneratedFile]:
    return db.query(GeneratedFile).filter(GeneratedFile.id == file_id, GeneratedFile.workspace_id == workspace_id).first()


def list_generated_files(db: Session, workspace_id: str) -> List[GeneratedFile]:
    return db.query(GeneratedFile).filter(GeneratedFile.workspace_id == workspace_id).order_by(desc(GeneratedFile.created_at)).all()


def generated_file_to_dict(gf: GeneratedFile) -> dict:
    return {
        "id": gf.id,
        "workspace_id": gf.workspace_id,
        "task_id": gf.task_id,
        "filename": gf.filename,
        "format": gf.format,
        "size_bytes": gf.size_bytes,
        "source_file_ids": gf.source_file_ids or [],
        "created_at": gf.created_at.isoformat(),
    }


# ──────────────────────────────────────────────────────────
# Connectors
# ──────────────────────────────────────────────────────────

def list_connectors(db: Session) -> List[Connector]:
    return db.query(Connector).order_by(Connector.display_name).all()


def get_connector_by_provider(db: Session, provider: str) -> Optional[Connector]:
    return db.query(Connector).filter(Connector.provider == provider).first()


def get_connector_by_id(db: Session, connector_id: str) -> Optional[Connector]:
    return db.query(Connector).filter(Connector.id == connector_id).first()


def get_user_connector_account(
    db: Session, user_id: str, connector_id: str
) -> Optional[UserConnectorAccount]:
    """Scoped to user_id — this is the enforcement point that stops one user
    from ever reading or acting on another user's connector account."""
    return (
        db.query(UserConnectorAccount)
        .filter(
            UserConnectorAccount.user_id == user_id,
            UserConnectorAccount.connector_id == connector_id,
        )
        .first()
    )


def upsert_user_connector_account(
    db: Session,
    user_id: str,
    connector_id: str,
    **fields,
) -> UserConnectorAccount:
    account = get_user_connector_account(db, user_id, connector_id)
    if account:
        for key, value in fields.items():
            setattr(account, key, value)
    else:
        account = UserConnectorAccount(
            id=_uid(), user_id=user_id, connector_id=connector_id, **fields
        )
        db.add(account)
    db.commit()
    db.refresh(account)
    return account


def delete_user_connector_account(db: Session, user_id: str, connector_id: str) -> bool:
    account = get_user_connector_account(db, user_id, connector_id)
    if not account:
        return False
    db.delete(account)
    db.commit()
    return True


def create_connector_event(
    db: Session,
    user_id: Optional[str],
    connector_id: Optional[str],
    event_type: str,
    status: str,
    action: str = "",
    request_metadata: Optional[dict] = None,
    response_metadata: Optional[dict] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> ConnectorEvent:
    event = ConnectorEvent(
        id=_uid(),
        user_id=user_id,
        connector_id=connector_id,
        event_type=event_type,
        action=action,
        status=status,
        request_metadata=request_metadata,
        response_metadata=response_metadata,
        error_code=error_code,
        error_message=error_message,
    )
    db.add(event)
    db.commit()
    return event


def list_connector_events(
    db: Session, user_id: Optional[str] = None, connector_id: Optional[str] = None, limit: int = 50
) -> List[ConnectorEvent]:
    q = db.query(ConnectorEvent)
    if user_id:
        q = q.filter(ConnectorEvent.user_id == user_id)
    if connector_id:
        q = q.filter(ConnectorEvent.connector_id == connector_id)
    return q.order_by(desc(ConnectorEvent.created_at)).limit(limit).all()


# ──────────────────────────────────────────────────────────
# Design Workflows (AI-generated Canva designs)
# ──────────────────────────────────────────────────────────

def create_design_workflow(
    db: Session,
    user_id: str,
    conversation_id: str,
    design_type: str,
    mode: str,
    structured_spec: dict,
    canva_design_id: Optional[str] = None,
    canva_brand_template_id: Optional[str] = None,
    last_job_id: Optional[str] = None,
) -> DesignWorkflow:
    workflow = DesignWorkflow(
        id=_uid(), user_id=user_id, conversation_id=conversation_id,
        design_type=design_type, mode=mode, structured_spec=structured_spec,
        canva_design_id=canva_design_id, canva_brand_template_id=canva_brand_template_id,
        last_job_id=last_job_id,
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    return workflow


def get_latest_design_workflow(db: Session, conversation_id: str) -> Optional[DesignWorkflow]:
    return (
        db.query(DesignWorkflow)
        .filter(DesignWorkflow.conversation_id == conversation_id)
        .order_by(desc(DesignWorkflow.updated_at))
        .first()
    )


def update_design_workflow(db: Session, workflow_id: str, **fields) -> Optional[DesignWorkflow]:
    workflow = db.query(DesignWorkflow).filter(DesignWorkflow.id == workflow_id).first()
    if not workflow:
        return None
    for key, value in fields.items():
        setattr(workflow, key, value)
    db.commit()
    db.refresh(workflow)
    return workflow


# ── Agent Orchestrator ──────────────────────────────────────────────────────

def create_agent_run(
    db: Session, user_id: str, intent: str, plan: dict,
    conversation_id: Optional[str] = None, source_module: str = "ai_chat",
    inputs: Optional[dict] = None,
) -> AgentRun:
    run = AgentRun(
        id=_uid(), user_id=user_id, conversation_id=conversation_id,
        source_module=source_module, intent=intent, plan=plan, inputs=inputs or {},
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def update_agent_run(db: Session, run_id: str, **fields) -> Optional[AgentRun]:
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if not run:
        return None
    for key, value in fields.items():
        setattr(run, key, value)
    db.commit()
    db.refresh(run)
    return run


def get_agent_run(db: Session, run_id: str) -> Optional[AgentRun]:
    return db.query(AgentRun).filter(AgentRun.id == run_id).first()


def list_agent_runs(db: Session, conversation_id: str) -> list[AgentRun]:
    return (
        db.query(AgentRun)
        .filter(AgentRun.conversation_id == conversation_id)
        .order_by(desc(AgentRun.created_at))
        .all()
    )


def create_agent_step(
    db: Session, run_id: str, step_key: str, provider: str, action: str,
    parameters: Optional[dict] = None, depends_on: Optional[list] = None,
    confirmation_required: bool = False,
) -> AgentStep:
    step = AgentStep(
        id=_uid(), run_id=run_id, step_key=step_key, provider=provider, action=action,
        parameters=parameters or {}, depends_on=depends_on or [],
        confirmation_required=confirmation_required,
    )
    db.add(step)
    db.commit()
    db.refresh(step)
    return step


def update_agent_step(db: Session, step_id: str, **fields) -> Optional[AgentStep]:
    step = db.query(AgentStep).filter(AgentStep.id == step_id).first()
    if not step:
        return None
    for key, value in fields.items():
        setattr(step, key, value)
    db.commit()
    db.refresh(step)
    return step


def create_agent_artifact(
    db: Session, run_id: str, type: str, provider: str,
    step_key: Optional[str] = None, external_id: Optional[str] = None,
    url: Optional[str] = None, filename: Optional[str] = None,
    mime_type: Optional[str] = None, size_bytes: int = 0, meta: Optional[dict] = None,
) -> AgentArtifact:
    artifact = AgentArtifact(
        id=_uid(), run_id=run_id, step_key=step_key, type=type, provider=provider,
        external_id=external_id, url=url, filename=filename, mime_type=mime_type,
        size_bytes=size_bytes, meta=meta,
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


# ── Connector sync state ────────────────────────────────────────────────────

def get_connector_sync_state(db: Session, user_id: str, connector_id: str) -> Optional[ConnectorSyncState]:
    return (
        db.query(ConnectorSyncState)
        .filter(ConnectorSyncState.user_id == user_id, ConnectorSyncState.connector_id == connector_id)
        .first()
    )


def upsert_connector_sync_state(db: Session, user_id: str, connector_id: str, **fields) -> ConnectorSyncState:
    state = get_connector_sync_state(db, user_id, connector_id)
    if state:
        for key, value in fields.items():
            setattr(state, key, value)
    else:
        state = ConnectorSyncState(id=_uid(), user_id=user_id, connector_id=connector_id, **fields)
        db.add(state)
    db.commit()
    db.refresh(state)
    return state


def list_due_sync_states(db: Session, now: datetime) -> List[ConnectorSyncState]:
    return (
        db.query(ConnectorSyncState)
        .filter((ConnectorSyncState.next_sync_at.is_(None)) | (ConnectorSyncState.next_sync_at <= now))
        .all()
    )


def list_connected_accounts(db: Session, connector_id: Optional[str] = None) -> List[UserConnectorAccount]:
    """All currently-connected accounts — used by the health monitor sweep."""
    q = db.query(UserConnectorAccount).filter(UserConnectorAccount.connection_status == "connected")
    if connector_id:
        q = q.filter(UserConnectorAccount.connector_id == connector_id)
    return q.all()


# ──────────────────────────────────────────────────────────
# Global AI Brain: MemoryItem
# ──────────────────────────────────────────────────────────

def create_memory_item(
    db: Session,
    user_id: str,
    module: str,
    kind: str,
    content: str,
    title: str = "",
    embedding: Optional[List[float]] = None,
    pinned: bool = False,
    source_type: str = "explicit",
    source_ref: Optional[str] = None,
) -> MemoryItem:
    item = MemoryItem(
        id=_uid(), user_id=user_id, module=module, kind=kind, title=title,
        content=content, embedding=embedding, pinned=pinned,
        source_type=source_type, source_ref=source_ref,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    # Cognitive Layer (Phase 2): Knowledge Graph — every decision/preference/
    # pinned-note/solution/project_event belongs_to its module, so "what
    # decisions were made in module X" is graph-traversable. Richer links
    # (e.g. to a specific conversation or task) are added by the calling
    # service layer, which has that context — this choke point only knows
    # the generic module relationship.
    from api.services import graph_service
    from api.services.identity import MemoryScope
    scope = MemoryScope(user_id=user_id, anon_session_id=None, is_persistent=True)
    graph_service.link_sync(
        db, scope, ("decision", item.id), ("module", module), relationship="belongs_to",
        from_label=title or content[:80], to_label=module,
    )

    return item


def get_memory_item(db: Session, memory_id: str, user_id: str) -> Optional[MemoryItem]:
    return db.query(MemoryItem).filter(MemoryItem.id == memory_id, MemoryItem.user_id == user_id).first()


def list_memory_items(
    db: Session, user_id: str, module: Optional[str] = None, kind: Optional[str] = None,
) -> List[MemoryItem]:
    q = db.query(MemoryItem).filter(MemoryItem.user_id == user_id)
    if module:
        q = q.filter(MemoryItem.module == module)
    if kind:
        q = q.filter(MemoryItem.kind == kind)
    return q.order_by(desc(MemoryItem.created_at)).all()


def list_memory_items_by_kinds(
    db: Session,
    user_id: str,
    kinds: List[str],
    module: Optional[str] = None,
    since=None,
    limit: int = 50,
) -> List[MemoryItem]:
    q = db.query(MemoryItem).filter(MemoryItem.user_id == user_id, MemoryItem.kind.in_(kinds))
    if module:
        q = q.filter(MemoryItem.module == module)
    if since:
        q = q.filter(MemoryItem.created_at >= since)
    return q.order_by(desc(MemoryItem.created_at)).limit(limit).all()


def delete_memory_item(db: Session, memory_id: str, user_id: str) -> bool:
    item = get_memory_item(db, memory_id, user_id)
    if not item:
        return False
    db.delete(item)
    db.commit()
    return True


def memory_item_to_dict(item: MemoryItem) -> dict:
    return {
        "id": item.id,
        "module": item.module,
        "kind": item.kind,
        "title": item.title,
        "content": item.content,
        "pinned": item.pinned,
        "source_type": item.source_type,
        "source_ref": item.source_ref,
        "created_at": item.created_at.isoformat(),
    }


# ──────────────────────────────────────────────────────────
# Global AI Brain: ConversationSummary
# ──────────────────────────────────────────────────────────

def create_conversation_summary(
    db: Session,
    conversation_id: str,
    summary_text: str,
    embedding: Optional[List[float]],
    covers_from_message_id: Optional[str],
    covers_to_message_id: Optional[str],
    message_count_covered: int,
) -> ConversationSummary:
    summary = ConversationSummary(
        id=_uid(), conversation_id=conversation_id, summary_text=summary_text,
        embedding=embedding, covers_from_message_id=covers_from_message_id,
        covers_to_message_id=covers_to_message_id, message_count_covered=message_count_covered,
    )
    db.add(summary)
    db.commit()
    db.refresh(summary)
    return summary


def list_conversation_summaries(db: Session, conversation_id: str) -> List[ConversationSummary]:
    return (
        db.query(ConversationSummary)
        .filter(ConversationSummary.conversation_id == conversation_id)
        .order_by(ConversationSummary.created_at)
        .all()
    )


def get_latest_conversation_summary(db: Session, conversation_id: str) -> Optional[ConversationSummary]:
    return (
        db.query(ConversationSummary)
        .filter(ConversationSummary.conversation_id == conversation_id)
        .order_by(desc(ConversationSummary.created_at))
        .first()
    )


def list_summaries_for_conversations(db: Session, conversation_ids: List[str]) -> List[ConversationSummary]:
    if not conversation_ids:
        return []
    return (
        db.query(ConversationSummary)
        .filter(ConversationSummary.conversation_id.in_(conversation_ids))
        .order_by(desc(ConversationSummary.created_at))
        .all()
    )


# ──────────────────────────────────────────────────────────
# Hybrid Workspace Awareness: IndexedResource
# ──────────────────────────────────────────────────────────

def get_indexed_resource(db: Session, resource_type: str, resource_id: str) -> Optional[IndexedResource]:
    return (
        db.query(IndexedResource)
        .filter(IndexedResource.resource_type == resource_type, IndexedResource.resource_id == resource_id)
        .first()
    )


def upsert_indexed_resource_dirty(
    db: Session,
    resource_type: str,
    resource_id: str,
    workspace_id: Optional[str] = None,
    reason: str = "",
) -> IndexedResource:
    row = get_indexed_resource(db, resource_type, resource_id)
    if row:
        row.status = "dirty"
        row.dirty_reason = reason
        if workspace_id:
            row.workspace_id = workspace_id
    else:
        row = IndexedResource(
            id=_uid(), resource_type=resource_type, resource_id=resource_id,
            workspace_id=workspace_id, status="dirty", dirty_reason=reason,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def mark_indexed_resource_clean(
    db: Session,
    row: IndexedResource,
    content_hash: Optional[str],
    embedding_model_version: str,
    title: Optional[str] = None,
    content_preview: Optional[str] = None,
    embedding: Optional[List[float]] = None,
) -> IndexedResource:
    row.status = "clean"
    row.dirty_reason = None
    row.content_hash = content_hash
    row.embedding_model_version = embedding_model_version
    row.last_indexed_at = _now()
    if title is not None:
        row.title = title
    if content_preview is not None:
        row.content_preview = content_preview
    if embedding is not None:
        row.embedding = embedding
    db.commit()
    db.refresh(row)
    return row


def mark_indexed_resource_error(db: Session, row: IndexedResource, reason: str) -> IndexedResource:
    row.status = "error"
    row.dirty_reason = reason
    db.commit()
    db.refresh(row)
    return row


def delete_indexed_resource(db: Session, resource_type: str, resource_id: str) -> bool:
    row = get_indexed_resource(db, resource_type, resource_id)
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


def list_dirty_resources(
    db: Session,
    workspace_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    limit: int = 50,
) -> List[IndexedResource]:
    q = db.query(IndexedResource).filter(IndexedResource.status == "dirty")
    if workspace_id:
        q = q.filter(IndexedResource.workspace_id == workspace_id)
    if resource_type:
        q = q.filter(IndexedResource.resource_type == resource_type)
    return q.order_by(IndexedResource.updated_at).limit(limit).all()


def count_dirty_resources(db: Session, workspace_id: str) -> int:
    return (
        db.query(IndexedResource)
        .filter(IndexedResource.workspace_id == workspace_id, IndexedResource.status == "dirty")
        .count()
    )


def list_indexed_resources_for_workspace(db: Session, workspace_id: str) -> List[IndexedResource]:
    return db.query(IndexedResource).filter(IndexedResource.workspace_id == workspace_id).all()


# ──────────────────────────────────────────────────────────
# Cognitive Layer (Phase 2): Task Memory — ProjectTask
# ──────────────────────────────────────────────────────────

def create_project_task(
    db: Session,
    user_id: str,
    module: str,
    title: str,
    description: str = "",
    conversation_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    linked_file_ids: Optional[List[str]] = None,
    linked_commit_refs: Optional[List[str]] = None,
) -> ProjectTask:
    task = ProjectTask(
        id=_uid(), user_id=user_id, module=module, title=title, description=description,
        conversation_id=conversation_id, workspace_id=workspace_id,
        linked_file_ids=linked_file_ids or [], linked_commit_refs=linked_commit_refs or [],
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_project_task(db: Session, task_id: str, user_id: str) -> Optional[ProjectTask]:
    return db.query(ProjectTask).filter(ProjectTask.id == task_id, ProjectTask.user_id == user_id).first()


def list_project_tasks(
    db: Session, user_id: str, status: Optional[str] = None, module: Optional[str] = None,
) -> List[ProjectTask]:
    q = db.query(ProjectTask).filter(ProjectTask.user_id == user_id)
    if status:
        q = q.filter(ProjectTask.status == status)
    if module:
        q = q.filter(ProjectTask.module == module)
    return q.order_by(desc(ProjectTask.updated_at)).all()


def update_project_task(
    db: Session,
    task_id: str,
    user_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    linked_file_ids: Optional[List[str]] = None,
    linked_commit_refs: Optional[List[str]] = None,
) -> Optional[ProjectTask]:
    task = get_project_task(db, task_id, user_id)
    if not task:
        return None
    if title is not None:
        task.title = title
    if description is not None:
        task.description = description
    if linked_file_ids is not None:
        task.linked_file_ids = linked_file_ids
    if linked_commit_refs is not None:
        task.linked_commit_refs = linked_commit_refs
    db.commit()
    db.refresh(task)
    return task


def update_project_task_status(
    db: Session, task_id: str, user_id: str, status: str, blocked_reason: Optional[str] = None,
) -> Optional[ProjectTask]:
    task = get_project_task(db, task_id, user_id)
    if not task:
        return None
    task.status = status
    task.blocked_reason = blocked_reason if status == "blocked" else None
    if status == "completed":
        task.completed_at = _now()
    else:
        task.completed_at = None
    db.commit()
    db.refresh(task)
    return task


def project_task_to_dict(task: ProjectTask) -> dict:
    return {
        "id": task.id,
        "module": task.module,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "blocked_reason": task.blocked_reason,
        "conversation_id": task.conversation_id,
        "workspace_id": task.workspace_id,
        "linked_file_ids": task.linked_file_ids or [],
        "linked_commit_refs": task.linked_commit_refs or [],
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


# ──────────────────────────────────────────────────────────
# Cognitive Layer (Phase 2): Knowledge Graph — CognitiveNode/CognitiveEdge
# ──────────────────────────────────────────────────────────

def get_cognitive_node(db: Session, entity_type: str, entity_ref: str) -> Optional[CognitiveNode]:
    return (
        db.query(CognitiveNode)
        .filter(CognitiveNode.entity_type == entity_type, CognitiveNode.entity_ref == entity_ref)
        .first()
    )


def upsert_cognitive_node(
    db: Session,
    user_id: str,
    entity_type: str,
    entity_ref: str,
    label: str = "",
    module: str = "general",
    embedding: Optional[List[float]] = None,
) -> CognitiveNode:
    node = get_cognitive_node(db, entity_type, entity_ref)
    if node:
        if label:
            node.label = label
        if embedding is not None:
            node.embedding = embedding
    else:
        node = CognitiveNode(
            id=_uid(), user_id=user_id, entity_type=entity_type, entity_ref=entity_ref,
            label=label, module=module, embedding=embedding,
        )
        db.add(node)
    db.commit()
    db.refresh(node)
    return node


def create_cognitive_edge(
    db: Session, from_node_id: str, to_node_id: str, relationship: str, weight: float = 1.0,
) -> CognitiveEdge:
    existing = (
        db.query(CognitiveEdge)
        .filter(
            CognitiveEdge.from_node_id == from_node_id,
            CognitiveEdge.to_node_id == to_node_id,
            CognitiveEdge.relationship == relationship,
        )
        .first()
    )
    if existing:
        return existing
    edge = CognitiveEdge(
        id=_uid(), from_node_id=from_node_id, to_node_id=to_node_id,
        relationship=relationship, weight=weight,
    )
    db.add(edge)
    db.commit()
    db.refresh(edge)
    return edge


def list_edges_for_node(db: Session, node_id: str) -> List[CognitiveEdge]:
    """Both directions — traversal doesn't care which side the node was linked from."""
    return (
        db.query(CognitiveEdge)
        .filter((CognitiveEdge.from_node_id == node_id) | (CognitiveEdge.to_node_id == node_id))
        .all()
    )


def get_cognitive_node_by_id(db: Session, node_id: str) -> Optional[CognitiveNode]:
    return db.query(CognitiveNode).filter(CognitiveNode.id == node_id).first()


def cognitive_node_to_dict(node: CognitiveNode) -> dict:
    return {
        "id": node.id,
        "entity_type": node.entity_type,
        "entity_ref": node.entity_ref,
        "label": node.label,
        "module": node.module,
        "created_at": node.created_at.isoformat(),
    }


def cognitive_edge_to_dict(edge: CognitiveEdge) -> dict:
    return {
        "id": edge.id,
        "from_node_id": edge.from_node_id,
        "to_node_id": edge.to_node_id,
        "relationship": edge.relationship,
        "weight": edge.weight,
        "created_at": edge.created_at.isoformat(),
    }


# ──────────────────────────────────────────────────────────
# Autonomous Research Agent (Learning Hub → Autonomous Research mode)
# ──────────────────────────────────────────────────────────

def create_research_mission(
    db: Session,
    *,
    user_id: Optional[str],
    mission_text: str,
    mode: str = "quick_scan",
    languages: Optional[list] = None,
    content_types: Optional[list] = None,
    free_mode: bool = True,
    limits: Optional[dict] = None,
    schedule: Optional[dict] = None,
    priority: int = 100,
    origin: str = "user",
    coverage_target: float = 70.0,
    max_coverage_rounds: int = 3,
) -> ResearchMission:
    mission = ResearchMission(
        id=_uid(),
        user_id=user_id,
        mission_text=mission_text,
        mode=mode,
        languages=languages or ["en"],
        content_types=content_types or ["web_pages"],
        free_mode=free_mode,
        limits=limits or {},
        schedule=schedule,
        status="queued",
        current_phase="queued",
        priority=priority,
        origin=origin,
        coverage_target=coverage_target,
        max_coverage_rounds=max_coverage_rounds,
        queued_at=datetime.now(timezone.utc),
    )
    db.add(mission)
    db.commit()
    db.refresh(mission)
    return mission


def get_research_mission(db: Session, mission_id: str) -> Optional[ResearchMission]:
    return db.query(ResearchMission).filter(ResearchMission.id == mission_id).first()


def list_research_missions(db: Session, user_id: Optional[str] = None) -> List[ResearchMission]:
    q = db.query(ResearchMission)
    if user_id:
        q = q.filter(ResearchMission.user_id == user_id)
    return q.order_by(desc(ResearchMission.created_at)).all()


def list_resumable_research_missions(db: Session, limit: int = 200) -> List[ResearchMission]:
    """Preview-only, read-only listing of missions eligible for auto-resume
    consideration (does NOT claim anything — safe to call from a preview
    endpoint). Excludes origin="test" so test-generated missions never even
    appear as candidates. Ordered priority DESC, then oldest-queued first —
    same ordering claim_next_mission() uses, so this is an accurate preview
    of claim order. Phase 2B.2.1: callers that actually want to run missions
    must go through claim_next_mission()/claim_batch(), not this function."""
    return (
        db.query(ResearchMission)
        .filter(ResearchMission.status.in_(["queued", "retry_waiting"]))
        .filter(ResearchMission.origin != "test")
        .order_by(desc(ResearchMission.priority), asc(func.coalesce(ResearchMission.queued_at, ResearchMission.created_at)))
        .limit(limit)
        .all()
    )


def claim_next_mission(db: Session, worker_id: str, lease_seconds: int, exclude_ids: Optional[set] = None) -> Optional[ResearchMission]:
    """Atomically claim exactly one eligible mission for this worker.

    Select-then-conditional-UPDATE (not SELECT...FOR UPDATE SKIP LOCKED,
    which SQLite doesn't support and this codebase runs on both SQLite and
    Postgres): the UPDATE's WHERE re-checks the exact status the SELECT saw,
    so if another worker claimed the same row first, this UPDATE's rowcount
    is 0 and the next candidate in the lookahead window is tried instead —
    a genuine atomicity guarantee per row on both backends, since a single
    UPDATE statement is atomic regardless of dialect.

    Excludes origin="test" (never auto-resumed) and any next_retry_at still
    in the future (backoff not yet elapsed). Returns None if nothing is
    currently claimable.
    """
    now = datetime.now(timezone.utc)
    exclude_ids = exclude_ids or set()
    candidates = (
        db.query(ResearchMission)
        .filter(ResearchMission.status.in_(["queued", "retry_waiting"]))
        .filter(ResearchMission.origin != "test")
        .filter(or_(ResearchMission.next_retry_at.is_(None), ResearchMission.next_retry_at <= now))
        .order_by(desc(ResearchMission.priority), asc(func.coalesce(ResearchMission.queued_at, ResearchMission.created_at)))
        .limit(25)
        .all()
    )
    for mission in candidates:
        if mission.id in exclude_ids:
            continue
        result = db.execute(
            update(ResearchMission)
            .where(ResearchMission.id == mission.id, ResearchMission.status == mission.status)
            .values(
                status="claimed",
                claim_owner=worker_id,
                claim_expires_at=now + timedelta(seconds=lease_seconds),
                heartbeat_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        db.commit()
        if result.rowcount == 1:
            db.refresh(mission)
            return mission
    return None


def heartbeat_mission_claim(db: Session, mission_id: str, worker_id: str, lease_seconds: int) -> bool:
    """Extend a held claim's lease. Returns False (no-op) if this worker no
    longer owns the claim (e.g. its lease already expired and was recovered
    by release_expired_leases() — the mission may already be claimed by a
    different worker by then)."""
    now = datetime.now(timezone.utc)
    result = db.execute(
        update(ResearchMission)
        .where(
            ResearchMission.id == mission_id,
            ResearchMission.claim_owner == worker_id,
            ResearchMission.status.in_(["claimed", "running"]),
        )
        .values(claim_expires_at=now + timedelta(seconds=lease_seconds), heartbeat_at=now)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return result.rowcount == 1


def release_expired_leases(db: Session) -> int:
    """Requeue any claimed/running mission whose lease has expired (worker
    crashed or was killed) — status -> "queued", resume_count incremented,
    claim fields cleared, queued_at reset so it re-enters the priority
    ordering fresh. Idempotent by construction: once a row's status flips to
    "queued" it no longer matches this UPDATE's WHERE clause, so calling
    this repeatedly never double-processes the same expired lease.

    A NULL claim_expires_at on a claimed/running row is treated the same as
    an expired one — this is what catches missions left "running" by the
    pre-2B.2.1 code path (which never set a lease at all) after an upgrade,
    satisfying "running missions with an expired lease become interrupted,
    then queued" for rows that predate leasing entirely."""
    now = datetime.now(timezone.utc)
    result = db.execute(
        update(ResearchMission)
        .where(
            ResearchMission.status.in_(["claimed", "running"]),
            or_(ResearchMission.claim_expires_at.is_(None), ResearchMission.claim_expires_at < now),
        )
        .values(
            status="queued",
            queued_at=now,
            resume_count=ResearchMission.resume_count + 1,
            claim_owner=None,
            claim_expires_at=None,
            heartbeat_at=None,
        )
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return result.rowcount


def archive_research_missions(db: Session, mission_ids: list[str]) -> int:
    """Bulk-archive missions already previewed by the caller (admin
    endpoint) — only archives rows currently in a terminal, non-resumable
    status (completed/stopped/cancelled/failed), never an active one."""
    if not mission_ids:
        return 0
    result = db.execute(
        update(ResearchMission)
        .where(
            ResearchMission.id.in_(mission_ids),
            ResearchMission.status.in_(["completed", "stopped", "cancelled", "failed"]),
        )
        .values(status="archived")
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return result.rowcount


def count_active_research_missions(db: Session) -> int:
    return (
        db.query(ResearchMission)
        .filter(ResearchMission.status.in_(["claimed", "running"]))
        .count()
    )


def count_research_missions_by_status(db: Session) -> dict:
    rows = db.query(ResearchMission.status, func.count(ResearchMission.id)).group_by(ResearchMission.status).all()
    return {status: count for status, count in rows}


def list_due_scheduled_missions(db: Session, now_iso: str) -> List[ResearchMission]:
    """continuous_learning missions whose schedule.next_run_at has passed — polled by the mission scheduler loop."""
    candidates = (
        db.query(ResearchMission)
        .filter(ResearchMission.mode == "continuous_learning")
        .filter(ResearchMission.status.in_(["completed", "stopped"]))
        .all()
    )
    due = []
    for m in candidates:
        next_run_at = (m.schedule or {}).get("next_run_at")
        if next_run_at and next_run_at <= now_iso:
            due.append(m)
    return due


def update_research_mission(db: Session, mission_id: str, **fields) -> Optional[ResearchMission]:
    """Generic field-setter — only columns present on ResearchMission are applied."""
    mission = get_research_mission(db, mission_id)
    if not mission:
        return None
    for key, value in fields.items():
        if hasattr(mission, key):
            setattr(mission, key, value)
    db.commit()
    db.refresh(mission)
    return mission


def enqueue_research_urls(
    db: Session, mission_id: str, items: list[dict],
) -> List[ResearchQueueItem]:
    """Bulk-insert queue items, skipping URLs already queued for this mission."""
    existing = {
        row[0] for row in db.query(ResearchQueueItem.url).filter(ResearchQueueItem.mission_id == mission_id).all()
    }
    created: List[ResearchQueueItem] = []
    for item in items:
        url = (item.get("url") or "").strip()
        if not url or url in existing:
            continue
        existing.add(url)
        row = ResearchQueueItem(
            id=_uid(),
            mission_id=mission_id,
            url=url,
            source_domain=item.get("source_domain", ""),
            discovered_via=item.get("discovered_via", ""),
            depth=item.get("depth", 0),
            topic_id=item.get("topic_id"),
            academic_metadata=item.get("academic_metadata"),
        )
        db.add(row)
        created.append(row)
    if created:
        db.commit()
        for row in created:
            db.refresh(row)
    return created


def get_next_pending_queue_item(db: Session, mission_id: str) -> Optional[ResearchQueueItem]:
    return (
        db.query(ResearchQueueItem)
        .filter(ResearchQueueItem.mission_id == mission_id, ResearchQueueItem.status == "pending")
        .order_by(ResearchQueueItem.created_at)
        .first()
    )


def list_research_queue_items(db: Session, mission_id: str, status: Optional[str] = None, limit: int = 200) -> List[ResearchQueueItem]:
    q = db.query(ResearchQueueItem).filter(ResearchQueueItem.mission_id == mission_id)
    if status:
        q = q.filter(ResearchQueueItem.status == status)
    return q.order_by(desc(ResearchQueueItem.created_at)).limit(limit).all()


def update_research_queue_item(db: Session, item_id: str, **fields) -> Optional[ResearchQueueItem]:
    row = db.query(ResearchQueueItem).filter(ResearchQueueItem.id == item_id).first()
    if not row:
        return None
    for key, value in fields.items():
        if hasattr(row, key):
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def get_research_source_by_url(db: Session, mission_id: str, url: str) -> Optional[ResearchSource]:
    return (
        db.query(ResearchSource)
        .filter(ResearchSource.mission_id == mission_id, ResearchSource.url == url)
        .first()
    )


def get_research_source_by_hash(db: Session, mission_id: str, content_hash: str) -> Optional[ResearchSource]:
    return (
        db.query(ResearchSource)
        .filter(ResearchSource.mission_id == mission_id, ResearchSource.content_hash == content_hash)
        .first()
    )


def create_research_source(db: Session, **fields) -> ResearchSource:
    source = ResearchSource(id=_uid(), **fields)
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def list_research_sources(db: Session, mission_id: str, quality_label: Optional[str] = None, limit: int = 200) -> List[ResearchSource]:
    q = db.query(ResearchSource).filter(ResearchSource.mission_id == mission_id)
    if quality_label:
        q = q.filter(ResearchSource.quality_label == quality_label)
    return q.order_by(desc(ResearchSource.quality_score)).limit(limit).all()


def update_research_source(db: Session, source_id: str, **fields) -> Optional[ResearchSource]:
    row = db.query(ResearchSource).filter(ResearchSource.id == source_id).first()
    if not row:
        return None
    for key, value in fields.items():
        if hasattr(row, key):
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def get_research_source(db: Session, source_id: str) -> Optional[ResearchSource]:
    return db.query(ResearchSource).filter(ResearchSource.id == source_id).first()


def list_research_sources_by_family(db: Session, source_family_id: str) -> List[ResearchSource]:
    """Every source sharing an independence-grouping key — used to count
    DISTINCT families (not raw source rows) as independent evidence."""
    return db.query(ResearchSource).filter(ResearchSource.source_family_id == source_family_id).all()


def list_research_sources_by_trust(
    db: Session, *, status: Optional[str] = None, order: str = "desc", limit: int = 200,
) -> List[ResearchSource]:
    """Sources ranked by effective_trust_score — feeds 'strongest sources
    about X' / low-trust / unproven queries. Cross-mission (trust is a
    property of the source, not scoped to one mission's view of it)."""
    q = db.query(ResearchSource)
    if status:
        q = q.filter(ResearchSource.trust_status == status)
    q = q.order_by(desc(ResearchSource.effective_trust_score) if order == "desc" else asc(ResearchSource.effective_trust_score))
    return q.limit(limit).all()


def list_stale_research_sources(db: Session, older_than: datetime, limit: int = 50) -> List[ResearchSource]:
    """Sources due for the trust worker's periodic staleness sweep — never
    recalculated, or not recalculated since `older_than`."""
    return (
        db.query(ResearchSource)
        .filter(or_(ResearchSource.last_trust_calculated_at.is_(None), ResearchSource.last_trust_calculated_at < older_than))
        .order_by(asc(func.coalesce(ResearchSource.last_trust_calculated_at, ResearchSource.fetched_at)))
        .limit(limit)
        .all()
    )


def list_knowledge_evidence_by_source(db: Session, research_source_id: str) -> List[KnowledgeEvidence]:
    """Reverse lookup — which nodes/edges does this source have evidence
    on. Used by SourceTrustService.recalculate() to know which
    KnowledgeNodes to cascade a confidence recompute to."""
    return db.query(KnowledgeEvidence).filter(KnowledgeEvidence.research_source_id == research_source_id).all()


# ── Dynamic Source Trust (Phase 2B.3) ───────────────────────────────────────

def create_source_trust_history(db: Session, **fields) -> SourceTrustHistory:
    """Append-only — no update/delete counterpart exists for this table
    anywhere in the codebase, by design."""
    entry = SourceTrustHistory(id=_uid(), **fields)
    db.add(entry)
    db.commit()
    return entry


def list_source_trust_history(db: Session, source_id: str, limit: int = 100) -> List[SourceTrustHistory]:
    return (
        db.query(SourceTrustHistory)
        .filter(SourceTrustHistory.source_id == source_id)
        .order_by(desc(SourceTrustHistory.created_at))
        .limit(limit)
        .all()
    )


def source_trust_history_to_dict(entry: SourceTrustHistory) -> dict:
    return {
        "id": entry.id,
        "source_id": entry.source_id,
        "old_static_score": entry.old_static_score,
        "new_static_score": entry.new_static_score,
        "old_dynamic_score": entry.old_dynamic_score,
        "new_dynamic_score": entry.new_dynamic_score,
        "old_effective_score": entry.old_effective_score,
        "new_effective_score": entry.new_effective_score,
        "delta": entry.delta,
        "reason_code": entry.reason_code,
        "reason_description": entry.reason_description,
        "related_mission_id": entry.related_mission_id,
        "related_evidence_id": entry.related_evidence_id,
        "related_conflict_id": entry.related_conflict_id,
        "related_user_id": entry.related_user_id,
        "service_name": entry.service_name,
        "calculation_version": entry.calculation_version,
        "created_at": entry.created_at.isoformat(),
    }


def get_source_user_review(db: Session, source_id: str, user_id: str) -> Optional[SourceUserReview]:
    return (
        db.query(SourceUserReview)
        .filter(SourceUserReview.source_id == source_id, SourceUserReview.user_id == user_id)
        .first()
    )


def upsert_source_user_review(db: Session, source_id: str, user_id: str, **fields) -> SourceUserReview:
    row = get_source_user_review(db, source_id, user_id)
    if row:
        for key, value in fields.items():
            if hasattr(row, key):
                setattr(row, key, value)
    else:
        row = SourceUserReview(id=_uid(), source_id=source_id, user_id=user_id, **fields)
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_source_user_reviews(db: Session, source_id: Optional[str] = None, review_status: Optional[str] = None) -> List[SourceUserReview]:
    q = db.query(SourceUserReview)
    if source_id:
        q = q.filter(SourceUserReview.source_id == source_id)
    if review_status:
        q = q.filter(SourceUserReview.review_status == review_status)
    return q.order_by(desc(SourceUserReview.updated_at)).all()


def source_user_review_to_dict(row: SourceUserReview) -> dict:
    return {
        "id": row.id,
        "source_id": row.source_id,
        "user_id": row.user_id,
        "review_status": row.review_status,
        "reason": row.reason,
        "note": row.note,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def create_trust_recalculation_job(db: Session, **fields) -> TrustRecalculationJob:
    job = TrustRecalculationJob(id=_uid(), **fields)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def claim_next_trust_job(db: Session, worker_id: str, lease_seconds: int) -> Optional[TrustRecalculationJob]:
    """Same atomic conditional-UPDATE claim pattern as
    crud.claim_next_mission() (Phase 2B.2.1) — a single-row UPDATE whose
    WHERE re-checks the exact status just read, so a losing concurrent
    claim attempt's rowcount is 0 rather than double-claiming."""
    now = datetime.now(timezone.utc)
    candidates = (
        db.query(TrustRecalculationJob)
        .filter(TrustRecalculationJob.status == "pending")
        .order_by(asc(TrustRecalculationJob.created_at))
        .limit(25)
        .all()
    )
    for job in candidates:
        result = db.execute(
            update(TrustRecalculationJob)
            .where(TrustRecalculationJob.id == job.id, TrustRecalculationJob.status == "pending")
            .values(
                status="claimed", claim_owner=worker_id,
                claim_expires_at=now + timedelta(seconds=lease_seconds),
            )
            .execution_options(synchronize_session=False)
        )
        db.commit()
        if result.rowcount == 1:
            db.refresh(job)
            return job
    return None


def release_expired_trust_jobs(db: Session) -> int:
    """Idempotent — same expired-lease recovery pattern as
    release_expired_leases() (Phase 2B.2.1). A crashed worker's claimed/
    running job becomes pending again exactly once."""
    now = datetime.now(timezone.utc)
    result = db.execute(
        update(TrustRecalculationJob)
        .where(
            TrustRecalculationJob.status.in_(["claimed", "running"]),
            or_(TrustRecalculationJob.claim_expires_at.is_(None), TrustRecalculationJob.claim_expires_at < now),
        )
        .values(status="pending", claim_owner=None, claim_expires_at=None)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return result.rowcount


def update_trust_recalculation_job(db: Session, job_id: str, **fields) -> Optional[TrustRecalculationJob]:
    job = db.query(TrustRecalculationJob).filter(TrustRecalculationJob.id == job_id).first()
    if not job:
        return None
    for key, value in fields.items():
        if hasattr(job, key):
            setattr(job, key, value)
    db.commit()
    db.refresh(job)
    return job


def get_trust_recalculation_job(db: Session, job_id: str) -> Optional[TrustRecalculationJob]:
    return db.query(TrustRecalculationJob).filter(TrustRecalculationJob.id == job_id).first()


def list_trust_recalculation_jobs(db: Session, status: Optional[str] = None, limit: int = 200) -> List[TrustRecalculationJob]:
    q = db.query(TrustRecalculationJob)
    if status:
        q = q.filter(TrustRecalculationJob.status == status)
    return q.order_by(desc(TrustRecalculationJob.created_at)).limit(limit).all()


def trust_recalculation_job_to_dict(job: TrustRecalculationJob) -> dict:
    return {
        "id": job.id,
        "research_source_id": job.research_source_id,
        "status": job.status,
        "reason": job.reason,
        "attempts": job.attempts,
        "claim_owner": job.claim_owner,
        "claim_expires_at": job.claim_expires_at.isoformat() if job.claim_expires_at else None,
        "created_at": job.created_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error": job.error,
    }


def create_research_file(db: Session, **fields) -> ResearchFile:
    file_row = ResearchFile(id=_uid(), **fields)
    db.add(file_row)
    db.commit()
    db.refresh(file_row)
    return file_row


def list_research_files(db: Session, mission_id: str, status: Optional[str] = None, limit: int = 300) -> List[ResearchFile]:
    q = db.query(ResearchFile).filter(ResearchFile.mission_id == mission_id)
    if status:
        q = q.filter(ResearchFile.status == status)
    return q.order_by(desc(ResearchFile.created_at)).limit(limit).all()


def update_research_file(db: Session, file_id: str, **fields) -> Optional[ResearchFile]:
    row = db.query(ResearchFile).filter(ResearchFile.id == file_id).first()
    if not row:
        return None
    for key, value in fields.items():
        if hasattr(row, key):
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def add_research_activity(db: Session, mission_id: str, level: str, message: str) -> ResearchActivityLog:
    entry = ResearchActivityLog(id=_uid(), mission_id=mission_id, level=level, message=message)
    db.add(entry)
    db.commit()
    return entry


def list_research_activity(db: Session, mission_id: str, level: Optional[str] = None, limit: int = 200) -> List[ResearchActivityLog]:
    q = db.query(ResearchActivityLog).filter(ResearchActivityLog.mission_id == mission_id)
    if level:
        q = q.filter(ResearchActivityLog.level == level)
    return q.order_by(desc(ResearchActivityLog.created_at)).limit(limit).all()


def research_mission_to_dict(mission: ResearchMission) -> dict:
    return {
        "id": mission.id,
        "mission_text": mission.mission_text,
        "normalized_topic": mission.normalized_topic,
        "mode": mission.mode,
        "languages": mission.languages,
        "content_types": mission.content_types,
        "free_mode": mission.free_mode,
        "status": mission.status,
        "current_phase": mission.current_phase,
        "limits": mission.limits,
        "schedule": mission.schedule,
        "pages_discovered": mission.pages_discovered,
        "pages_processed": mission.pages_processed,
        "files_discovered": mission.files_discovered,
        "files_ingested": mission.files_ingested,
        "files_rejected": mission.files_rejected,
        "duplicates_skipped": mission.duplicates_skipped,
        "storage_used_bytes": mission.storage_used_bytes,
        "estimated_cost_usd": mission.estimated_cost_usd,
        "last_error": mission.last_error,
        "last_run_at": mission.last_run_at.isoformat() if mission.last_run_at else None,
        "created_at": mission.created_at.isoformat(),
        "updated_at": mission.updated_at.isoformat(),
        "priority": mission.priority,
        "origin": mission.origin,
        "queued_at": mission.queued_at.isoformat() if mission.queued_at else None,
        "claim_owner": mission.claim_owner,
        "claim_expires_at": mission.claim_expires_at.isoformat() if mission.claim_expires_at else None,
        "heartbeat_at": mission.heartbeat_at.isoformat() if mission.heartbeat_at else None,
        "resume_count": mission.resume_count,
        "next_retry_at": mission.next_retry_at.isoformat() if mission.next_retry_at else None,
        "last_attempt_error_type": mission.last_attempt_error_type,
        "coverage_target": mission.coverage_target,
        "max_coverage_rounds": mission.max_coverage_rounds,
        "coverage_rounds_completed": mission.coverage_rounds_completed,
        "detected_manufacturer": mission.detected_manufacturer,
    }


def research_source_to_dict(source: ResearchSource) -> dict:
    return {
        "id": source.id,
        "mission_id": source.mission_id,
        "url": source.url,
        "domain": source.domain,
        "title": source.title,
        "publisher": source.publisher,
        "quality_score": source.quality_score,
        "quality_label": source.quality_label,
        "quality_reasons": source.quality_reasons,
        "license_note": source.license_note,
        "accepted_into_kb": source.accepted_into_kb,
        "fetched_at": source.fetched_at.isoformat(),
        "dynamic_trust_score": source.dynamic_trust_score,
        "effective_trust_score": source.effective_trust_score,
        "trust_status": source.trust_status,
        "trust_algorithm_version": source.trust_algorithm_version,
        "last_trust_calculated_at": source.last_trust_calculated_at.isoformat() if source.last_trust_calculated_at else None,
        "trust_signal_summary": source.trust_signal_summary,
        "source_family_id": source.source_family_id,
        "source_doi": source.source_doi,
    }


def research_file_to_dict(file_row: ResearchFile) -> dict:
    return {
        "id": file_row.id,
        "mission_id": file_row.mission_id,
        "source_id": file_row.source_id,
        "filename": file_row.filename,
        "file_type": file_row.file_type,
        "size_bytes": file_row.size_bytes,
        "publication_date": file_row.publication_date,
        "detected_language": file_row.detected_language,
        "relevance_score": file_row.relevance_score,
        "quality_score": file_row.quality_score,
        "status": file_row.status,
        "downloaded": file_row.downloaded,
        "rag_document_id": file_row.rag_document_id,
        "created_at": file_row.created_at.isoformat(),
    }


def research_activity_to_dict(entry: ResearchActivityLog) -> dict:
    return {
        "id": entry.id,
        "mission_id": entry.mission_id,
        "level": entry.level,
        "message": entry.message,
        "created_at": entry.created_at.isoformat(),
    }


# ──────────────────────────────────────────────────────────
# Knowledge Evolution Engine (Phase 2A) — Research Plan / Topics
# ──────────────────────────────────────────────────────────

def create_research_plan(db: Session, *, mission_id: str, normalized_understanding: dict) -> ResearchPlan:
    plan = ResearchPlan(id=_uid(), mission_id=mission_id, normalized_understanding=normalized_understanding)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def get_research_plan_by_mission(db: Session, mission_id: str) -> Optional[ResearchPlan]:
    return (
        db.query(ResearchPlan)
        .filter(ResearchPlan.mission_id == mission_id)
        .order_by(desc(ResearchPlan.created_at))
        .first()
    )


def create_research_topic(db: Session, **fields) -> ResearchTopic:
    topic = ResearchTopic(id=_uid(), **fields)
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return topic


def list_research_topics(db: Session, mission_id: str) -> List[ResearchTopic]:
    return (
        db.query(ResearchTopic)
        .filter(ResearchTopic.mission_id == mission_id)
        .order_by(desc(ResearchTopic.rank))
        .all()
    )


def get_research_topic(db: Session, topic_id: str) -> Optional[ResearchTopic]:
    return db.query(ResearchTopic).filter(ResearchTopic.id == topic_id).first()


def update_research_topic(db: Session, topic_id: str, **fields) -> Optional[ResearchTopic]:
    topic = get_research_topic(db, topic_id)
    if not topic:
        return None
    for key, value in fields.items():
        if hasattr(topic, key):
            setattr(topic, key, value)
    db.commit()
    db.refresh(topic)
    return topic


def research_plan_to_dict(plan: ResearchPlan) -> dict:
    return {
        "id": plan.id,
        "mission_id": plan.mission_id,
        "normalized_understanding": plan.normalized_understanding,
        "created_at": plan.created_at.isoformat(),
    }


def research_topic_to_dict(topic: ResearchTopic) -> dict:
    return {
        "id": topic.id,
        "plan_id": topic.plan_id,
        "mission_id": topic.mission_id,
        "label": topic.label,
        "parent_topic_id": topic.parent_topic_id,
        "rank": topic.rank,
        "dependencies": topic.dependencies,
        "status": topic.status,
        "estimates": topic.estimates,
        "research_questions": topic.research_questions,
        "search_strategy": topic.search_strategy,
        "coverage_pct": topic.coverage_pct,
        "created_at": topic.created_at.isoformat(),
        "updated_at": topic.updated_at.isoformat(),
        "topic_memory_id": topic.topic_memory_id,
    }


# ──────────────────────────────────────────────────────────
# Research Memory & Knowledge Freshness (Phase 2B.4)
# ──────────────────────────────────────────────────────────

def create_topic_research_memory(db: Session, **fields) -> TopicResearchMemory:
    row = TopicResearchMemory(id=_uid(), **fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_topic_research_memory(db: Session, memory_id: str) -> Optional[TopicResearchMemory]:
    return db.query(TopicResearchMemory).filter(TopicResearchMemory.id == memory_id).first()


def get_topic_research_memory_by_key(db: Session, topic_key: str) -> Optional[TopicResearchMemory]:
    return db.query(TopicResearchMemory).filter(TopicResearchMemory.topic_key == topic_key).first()


def list_topic_research_memories(db: Session, limit: int = 500) -> List[TopicResearchMemory]:
    """Phase 2B.9 — the Knowledge Health audit's iteration source. Oldest-
    updated first so a bounded per-tick batch naturally rotates through
    every topic over successive ticks instead of starving later ones."""
    return db.query(TopicResearchMemory).order_by(asc(TopicResearchMemory.updated_at)).limit(limit).all()


def update_topic_research_memory(db: Session, memory_id: str, **fields) -> Optional[TopicResearchMemory]:
    row = get_topic_research_memory(db, memory_id)
    if not row:
        return None
    for key, value in fields.items():
        if hasattr(row, key):
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def list_outdated_topic_memories(db: Session, limit: int = 200) -> List[TopicResearchMemory]:
    return (
        db.query(TopicResearchMemory)
        .filter(TopicResearchMemory.freshness_status.in_(["Aging", "Outdated"]))
        .order_by(asc(TopicResearchMemory.next_refresh))
        .limit(limit)
        .all()
    )


def list_due_topic_memories(db: Session, now: datetime, limit: int) -> List[TopicResearchMemory]:
    """Bounded batch of topics due for a Knowledge Refresh sweep — same
    bounded-batch-per-tick discipline as MissionScheduler.tick()'s existing
    resume sweep (Phase 2B.2.1), so this can never fan out unbounded either.
    `now` is a real datetime (matches the release_expired_leases()/
    release_expired_trust_jobs() convention above), not an ISO string —
    next_refresh is a genuine DateTime column, not JSON."""
    return (
        db.query(TopicResearchMemory)
        .filter(
            TopicResearchMemory.next_refresh.isnot(None),
            TopicResearchMemory.next_refresh <= now,
            TopicResearchMemory.freshness_status.in_(["Aging", "Outdated"]),
        )
        .order_by(asc(TopicResearchMemory.next_refresh))
        .limit(limit)
        .all()
    )


def topic_research_memory_to_dict(row: TopicResearchMemory) -> dict:
    return {
        "id": row.id,
        "topic_key": row.topic_key,
        "content_category": row.content_category,
        "last_research": row.last_research.isoformat() if row.last_research else None,
        "last_update": row.last_update.isoformat() if row.last_update else None,
        "search_queries": row.search_queries,
        "providers_used": row.providers_used,
        "visited_sources": row.visited_sources,
        "downloaded_files_count": row.downloaded_files_count,
        "processed_hashes_count": row.processed_hashes_count,
        "extracted_graph_count": row.extracted_graph_count,
        "generated_embeddings_count": row.generated_embeddings_count,
        "new_facts_count": row.new_facts_count,
        "updated_facts_count": row.updated_facts_count,
        "conflicts_found_count": row.conflicts_found_count,
        "knowledge_gain": row.knowledge_gain,
        "next_refresh": row.next_refresh.isoformat() if row.next_refresh else None,
        "freshness_status": row.freshness_status,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


# ──────────────────────────────────────────────────────────
# Autonomous Internet Learning + Manufacturer/Scientific Intelligence (Phase 2B.5)
# ──────────────────────────────────────────────────────────

def create_academic_paper_metadata(db: Session, **fields) -> AcademicPaperMetadata:
    row = AcademicPaperMetadata(id=_uid(), **fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_academic_paper_metadata_by_source(db: Session, research_source_id: str) -> Optional[AcademicPaperMetadata]:
    return (
        db.query(AcademicPaperMetadata)
        .filter(AcademicPaperMetadata.research_source_id == research_source_id)
        .first()
    )


def academic_paper_metadata_to_dict(row: AcademicPaperMetadata) -> dict:
    return {
        "id": row.id,
        "research_source_id": row.research_source_id,
        "title": row.title,
        "authors": row.authors,
        "institution_or_journal": row.institution_or_journal,
        "degree_type": row.degree_type,
        "publication_year": row.publication_year,
        "doi_or_repo_id": row.doi_or_repo_id,
        "abstract": row.abstract,
        "research_problem": row.research_problem,
        "methodology": row.methodology,
        "equipment_components": row.equipment_components,
        "results": row.results,
        "limitations": row.limitations,
        "future_work": row.future_work,
        "citations": row.citations,
        "is_open_access": row.is_open_access,
        "file_hash": row.file_hash,
        "created_at": row.created_at.isoformat(),
    }


# ──────────────────────────────────────────────────────────
# Knowledge Evolution Engine (Phase 2A) — versioned Knowledge Graph
# ──────────────────────────────────────────────────────────

def label_exists_in_graph(db: Session, label: str) -> bool:
    """Case-insensitive check across all current KnowledgeNode types — used by
    the Curiosity Engine's unexplained-term scan, which doesn't know in
    advance what type a mentioned term would be classified as."""
    return (
        db.query(KnowledgeNode)
        .filter(func.lower(KnowledgeNode.label) == label.lower(), KnowledgeNode.status == "current")
        .first()
        is not None
    )


def get_knowledge_node_by_label(db: Session, label: str, node_type: str) -> Optional[KnowledgeNode]:
    """Dedupe key used by knowledge_versioning.py — same (label, node_type) match study_service.py already uses."""
    return (
        db.query(KnowledgeNode)
        .filter(
            KnowledgeNode.label == label,
            KnowledgeNode.node_type == node_type,
            KnowledgeNode.status == "current",
        )
        .first()
    )


def create_knowledge_node(db: Session, **fields) -> KnowledgeNode:
    node = KnowledgeNode(id=_uid(), **fields)
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def get_knowledge_node(db: Session, node_id: str) -> Optional[KnowledgeNode]:
    return db.query(KnowledgeNode).filter(KnowledgeNode.id == node_id).first()


def update_knowledge_node(db: Session, node_id: str, **fields) -> Optional[KnowledgeNode]:
    node = get_knowledge_node(db, node_id)
    if not node:
        return None
    for key, value in fields.items():
        if hasattr(node, key):
            setattr(node, key, value)
    db.commit()
    db.refresh(node)
    return node


def get_knowledge_edge_by_relationship(db: Session, from_node_id: str, to_node_id: str, relationship: str) -> Optional[KnowledgeEdge]:
    return (
        db.query(KnowledgeEdge)
        .filter(
            KnowledgeEdge.from_node_id == from_node_id,
            KnowledgeEdge.to_node_id == to_node_id,
            KnowledgeEdge.relationship == relationship,
            KnowledgeEdge.status == "current",
        )
        .first()
    )


def list_knowledge_edges_for_node(db: Session, node_id: str, direction: str = "both") -> List[KnowledgeEdge]:
    """Phase 2B.7 — every current edge touching a node, for the Expert
    Reasoning Engine's graph traversal (Cause->Effect, Component->Function,
    Manufacturer->Product, etc.). direction: "out" (node is from_node),
    "in" (node is to_node), or "both" (default)."""
    q = db.query(KnowledgeEdge).filter(KnowledgeEdge.status == "current")
    if direction == "out":
        q = q.filter(KnowledgeEdge.from_node_id == node_id)
    elif direction == "in":
        q = q.filter(KnowledgeEdge.to_node_id == node_id)
    else:
        q = q.filter(or_(KnowledgeEdge.from_node_id == node_id, KnowledgeEdge.to_node_id == node_id))
    return q.all()


def create_knowledge_edge(db: Session, **fields) -> KnowledgeEdge:
    edge = KnowledgeEdge(id=_uid(), **fields)
    db.add(edge)
    db.commit()
    db.refresh(edge)
    return edge


def get_knowledge_edge(db: Session, edge_id: str) -> Optional[KnowledgeEdge]:
    return db.query(KnowledgeEdge).filter(KnowledgeEdge.id == edge_id).first()


def update_knowledge_edge(db: Session, edge_id: str, **fields) -> Optional[KnowledgeEdge]:
    edge = get_knowledge_edge(db, edge_id)
    if not edge:
        return None
    for key, value in fields.items():
        if hasattr(edge, key):
            setattr(edge, key, value)
    db.commit()
    db.refresh(edge)
    return edge


def create_knowledge_evidence(db: Session, **fields) -> KnowledgeEvidence:
    evidence = KnowledgeEvidence(id=_uid(), **fields)
    db.add(evidence)
    db.commit()
    return evidence


def list_knowledge_evidence(db: Session, node_id: Optional[str] = None, edge_id: Optional[str] = None) -> List[KnowledgeEvidence]:
    q = db.query(KnowledgeEvidence)
    if node_id:
        q = q.filter(KnowledgeEvidence.node_id == node_id)
    if edge_id:
        q = q.filter(KnowledgeEvidence.edge_id == edge_id)
    return q.order_by(desc(KnowledgeEvidence.created_at)).all()


def sum_evidence_count_for_topic(db: Session, topic_id: str) -> int:
    """Total evidence_count across every current KnowledgeNode linked to this topic — feeds gap_detector's coverage math."""
    total = (
        db.query(func.coalesce(func.sum(KnowledgeNode.evidence_count), 0))
        .filter(KnowledgeNode.research_topic_id == topic_id, KnowledgeNode.status == "current")
        .scalar()
    )
    return int(total or 0)


def list_knowledge_nodes_by_topic(db: Session, topic_id: str, status: Optional[str] = "current") -> List[KnowledgeNode]:
    q = db.query(KnowledgeNode).filter(KnowledgeNode.research_topic_id == topic_id)
    if status:
        q = q.filter(KnowledgeNode.status == status)
    return q.order_by(desc(KnowledgeNode.confidence)).all()


def get_knowledge_node_version_chain(db: Session, node_id: str) -> List[KnowledgeNode]:
    """Walk supersedes_id backward and replaced_by_id forward — the full version history of one fact, oldest first."""
    node = get_knowledge_node(db, node_id)
    if not node:
        return []

    chain: List[KnowledgeNode] = [node]

    cursor = node
    while cursor.supersedes_id:
        prev = get_knowledge_node(db, cursor.supersedes_id)
        if not prev:
            break
        chain.insert(0, prev)
        cursor = prev

    cursor = node
    while cursor.replaced_by_id:
        nxt = get_knowledge_node(db, cursor.replaced_by_id)
        if not nxt:
            break
        chain.append(nxt)
        cursor = nxt

    return chain


def knowledge_node_to_dict(node: KnowledgeNode) -> dict:
    return {
        "id": node.id,
        "node_type": node.node_type,
        "label": node.label,
        "description": node.description,
        "approved": node.approved,
        "weight": node.weight,
        "version": node.version,
        "confidence": node.confidence,
        "evidence_count": node.evidence_count,
        "status": node.status,
        "supersedes_id": node.supersedes_id,
        "replaced_by_id": node.replaced_by_id,
        "research_topic_id": node.research_topic_id,
        "created_at": node.created_at.isoformat(),
    }


def knowledge_evidence_to_dict(evidence: KnowledgeEvidence) -> dict:
    return {
        "id": evidence.id,
        "node_id": evidence.node_id,
        "edge_id": evidence.edge_id,
        "research_source_id": evidence.research_source_id,
        "supports": evidence.supports,
        "created_at": evidence.created_at.isoformat(),
    }


# ──────────────────────────────────────────────────────────
# Knowledge Evolution Engine (Phase 2B.1) — Curiosity Engine
# ──────────────────────────────────────────────────────────

def create_curiosity_question(db: Session, **fields) -> CuriosityQuestion:
    question = CuriosityQuestion(id=_uid(), **fields)
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


def get_curiosity_question(db: Session, question_id: str) -> Optional[CuriosityQuestion]:
    return db.query(CuriosityQuestion).filter(CuriosityQuestion.id == question_id).first()


def list_curiosity_questions(db: Session, mission_id: Optional[str] = None, status: Optional[str] = None) -> List[CuriosityQuestion]:
    q = db.query(CuriosityQuestion)
    if mission_id:
        q = q.filter(CuriosityQuestion.mission_id == mission_id)
    if status:
        q = q.filter(CuriosityQuestion.status == status)
    return q.order_by(desc(CuriosityQuestion.priority_score)).all()


def update_curiosity_question(db: Session, question_id: str, **fields) -> Optional[CuriosityQuestion]:
    question = get_curiosity_question(db, question_id)
    if not question:
        return None
    for key, value in fields.items():
        if hasattr(question, key):
            setattr(question, key, value)
    db.commit()
    db.refresh(question)
    return question


def count_curiosity_spawned_missions_since(db: Session, since: datetime) -> int:
    """Platform-wide count of curiosity-spawned missions since `since` — used
    for the daily_curiosity_limit setting, backed by real rows (not an
    in-memory counter) so it survives restarts."""
    return (
        db.query(func.count(CuriosityQuestion.id))
        .filter(CuriosityQuestion.spawned_mission_id.isnot(None), CuriosityQuestion.created_at >= since)
        .scalar()
        or 0
    )


def curiosity_question_to_dict(question: CuriosityQuestion) -> dict:
    return {
        "id": question.id,
        "mission_id": question.mission_id,
        "related_topic_id": question.related_topic_id,
        "question_text": question.question_text,
        "reason": question.reason,
        "source_reference": question.source_reference,
        "category": question.category,
        "priority_score": question.priority_score,
        "expected_knowledge_gain": question.expected_knowledge_gain,
        "estimated_research_cost": question.estimated_research_cost,
        "estimated_storage_mb": question.estimated_storage_mb,
        "status": question.status,
        "spawned_mission_id": question.spawned_mission_id,
        "created_at": question.created_at.isoformat(),
        "updated_at": question.updated_at.isoformat(),
    }


# ──────────────────────────────────────────────────────────
# Knowledge Governance Layer (Phase 2B.2)
# ──────────────────────────────────────────────────────────

def create_knowledge_provenance(db: Session, **fields) -> KnowledgeProvenance:
    row = KnowledgeProvenance(id=_uid(), **fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_knowledge_provenance(db: Session, provenance_id: str) -> bool:
    """Used only by governance_service's compensating-rollback path to undo
    a provenance row it just inserted earlier in the SAME failed operation —
    never called to retroactively edit history."""
    row = db.query(KnowledgeProvenance).filter(KnowledgeProvenance.id == provenance_id).first()
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


def list_knowledge_provenance(db: Session, node_id: Optional[str] = None, edge_id: Optional[str] = None) -> List[KnowledgeProvenance]:
    q = db.query(KnowledgeProvenance)
    if node_id:
        q = q.filter(KnowledgeProvenance.node_id == node_id)
    if edge_id:
        q = q.filter(KnowledgeProvenance.edge_id == edge_id)
    return q.order_by(desc(KnowledgeProvenance.created_at)).all()


def knowledge_provenance_to_dict(row: KnowledgeProvenance) -> dict:
    return {
        "id": row.id,
        "node_id": row.node_id,
        "edge_id": row.edge_id,
        "mission_id": row.mission_id,
        "source_id": row.source_id,
        "provider_used": row.provider_used,
        "extractor_used": row.extractor_used,
        "parser_version": row.parser_version,
        "knowledge_version": row.knowledge_version,
        "original_filename": row.original_filename,
        "original_url": row.original_url,
        "document_hash": row.document_hash,
        "page_number": row.page_number,
        "section": row.section,
        "paragraph": row.paragraph,
        "sentence_offset": row.sentence_offset,
        "created_by_service": row.created_by_service,
        "confidence_at_write": row.confidence_at_write,
        "created_at": row.created_at.isoformat(),
    }


def create_knowledge_conflict(db: Session, **fields) -> KnowledgeConflict:
    conflict = KnowledgeConflict(id=_uid(), **fields)
    db.add(conflict)
    db.commit()
    db.refresh(conflict)
    return conflict


def get_knowledge_conflict(db: Session, conflict_id: str) -> Optional[KnowledgeConflict]:
    return db.query(KnowledgeConflict).filter(KnowledgeConflict.id == conflict_id).first()


def list_knowledge_conflicts(
    db: Session,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    human_review_required: Optional[bool] = None,
    subject_node_id: Optional[str] = None,
) -> List[KnowledgeConflict]:
    q = db.query(KnowledgeConflict)
    if status:
        q = q.filter(KnowledgeConflict.resolution_status == status)
    if severity:
        q = q.filter(KnowledgeConflict.severity == severity)
    if human_review_required is not None:
        q = q.filter(KnowledgeConflict.human_review_required == human_review_required)
    if subject_node_id:
        q = q.filter(KnowledgeConflict.subject_node_id == subject_node_id)
    return q.order_by(desc(KnowledgeConflict.created_at)).all()


def update_knowledge_conflict(db: Session, conflict_id: str, **fields) -> Optional[KnowledgeConflict]:
    conflict = get_knowledge_conflict(db, conflict_id)
    if not conflict:
        return None
    for key, value in fields.items():
        if hasattr(conflict, key):
            setattr(conflict, key, value)
    db.commit()
    db.refresh(conflict)
    return conflict


def knowledge_conflict_to_dict(conflict: KnowledgeConflict) -> dict:
    return {
        "id": conflict.id,
        "subject_node_id": conflict.subject_node_id,
        "predicate": conflict.predicate,
        "claim_a": conflict.claim_a,
        "claim_b": conflict.claim_b,
        "source_a_id": conflict.source_a_id,
        "source_b_id": conflict.source_b_id,
        "conflict_type": conflict.conflict_type,
        "severity": conflict.severity,
        "resolution_status": conflict.resolution_status,
        "recommended_interpretation": conflict.recommended_interpretation,
        "confidence": conflict.confidence,
        "human_review_required": conflict.human_review_required,
        "created_at": conflict.created_at.isoformat(),
        "updated_at": conflict.updated_at.isoformat(),
    }


def create_knowledge_audit_log(db: Session, **fields) -> KnowledgeAuditLog:
    """Append-only by design — there is deliberately no update/delete
    counterpart for this table anywhere in the codebase."""
    entry = KnowledgeAuditLog(id=_uid(), **fields)
    db.add(entry)
    db.commit()
    return entry


def list_knowledge_audit_log(db: Session, node_id: Optional[str] = None, edge_id: Optional[str] = None) -> List[KnowledgeAuditLog]:
    q = db.query(KnowledgeAuditLog)
    if node_id:
        q = q.filter(KnowledgeAuditLog.node_id == node_id)
    if edge_id:
        q = q.filter(KnowledgeAuditLog.edge_id == edge_id)
    return q.order_by(desc(KnowledgeAuditLog.created_at)).all()


def knowledge_audit_log_to_dict(entry: KnowledgeAuditLog) -> dict:
    return {
        "id": entry.id,
        "node_id": entry.node_id,
        "edge_id": entry.edge_id,
        "service": entry.service,
        "operation": entry.operation,
        "reason": entry.reason,
        "old_value": entry.old_value,
        "new_value": entry.new_value,
        "mission_id": entry.mission_id,
        "created_at": entry.created_at.isoformat(),
    }


# ── Proactive AI Scientist (Phase 2B.8) ─────────────────────────────────────

def create_scientific_alert(db: Session, **fields) -> ScientificAlert:
    alert = ScientificAlert(id=_uid(), **fields)
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def list_scientific_alerts(
    db: Session, alert_type: Optional[str] = None, since: Optional[datetime] = None, limit: int = 50,
) -> List[ScientificAlert]:
    q = db.query(ScientificAlert)
    if alert_type:
        q = q.filter(ScientificAlert.alert_type == alert_type)
    if since:
        q = q.filter(ScientificAlert.created_at >= since)
    return q.order_by(desc(ScientificAlert.created_at)).limit(limit).all()


def count_scientific_alerts_since(db: Session, since: datetime) -> int:
    return db.query(ScientificAlert).filter(ScientificAlert.created_at >= since).count()


def get_recent_scientific_alert_by_key(
    db: Session, topic_key: str, alert_type: str, within_days: int,
) -> Optional[ScientificAlert]:
    """The duplicate-discovery guard — an alert for the same topic_key +
    alert_type created within the dedup window blocks a new one."""
    cutoff = _now() - timedelta(days=within_days)
    return (
        db.query(ScientificAlert)
        .filter(
            ScientificAlert.topic_key == topic_key,
            ScientificAlert.alert_type == alert_type,
            ScientificAlert.created_at >= cutoff,
        )
        .order_by(desc(ScientificAlert.created_at))
        .first()
    )


def scientific_alert_to_dict(alert: ScientificAlert) -> dict:
    return {
        "id": alert.id,
        "alert_type": alert.alert_type,
        "title": alert.title,
        "summary": alert.summary,
        "topic_key": alert.topic_key,
        "mission_id": alert.mission_id,
        "related_node_ids": alert.related_node_ids,
        "related_source_ids": alert.related_source_ids,
        "min_trust_score": alert.min_trust_score,
        "status": alert.status,
        "created_at": alert.created_at.isoformat(),
    }


# ── Knowledge Health (Phase 2B.9) ───────────────────────────────────────────

def upsert_knowledge_health_snapshot(db: Session, *, scope_type: str, scope_key: str, **fields) -> KnowledgeHealthSnapshot:
    """One row per scope_type+scope_key — this table holds the latest view
    only, never a history, matching the "cached, periodically-refreshed
    score" design (not a new time-series/history table)."""
    existing = (
        db.query(KnowledgeHealthSnapshot)
        .filter(KnowledgeHealthSnapshot.scope_type == scope_type, KnowledgeHealthSnapshot.scope_key == scope_key)
        .first()
    )
    if existing:
        for key, value in fields.items():
            if hasattr(existing, key):
                setattr(existing, key, value)
        existing.computed_at = _now()
        db.commit()
        db.refresh(existing)
        return existing
    row = KnowledgeHealthSnapshot(id=_uid(), scope_type=scope_type, scope_key=scope_key, **fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_knowledge_health_snapshot(db: Session, scope_type: str, scope_key: str) -> Optional[KnowledgeHealthSnapshot]:
    return (
        db.query(KnowledgeHealthSnapshot)
        .filter(KnowledgeHealthSnapshot.scope_type == scope_type, KnowledgeHealthSnapshot.scope_key == scope_key)
        .first()
    )


def list_knowledge_health_snapshots(
    db: Session, scope_type: Optional[str] = None, classification: Optional[str] = None, limit: int = 200,
) -> List[KnowledgeHealthSnapshot]:
    q = db.query(KnowledgeHealthSnapshot)
    if scope_type:
        q = q.filter(KnowledgeHealthSnapshot.scope_type == scope_type)
    if classification:
        q = q.filter(KnowledgeHealthSnapshot.classification == classification)
    return q.order_by(asc(KnowledgeHealthSnapshot.score)).limit(limit).all()


def knowledge_health_snapshot_to_dict(row: KnowledgeHealthSnapshot) -> dict:
    return {
        "id": row.id,
        "scope_type": row.scope_type,
        "scope_key": row.scope_key,
        "scope_label": row.scope_label,
        "score": row.score,
        "classification": row.classification,
        "signals": row.signals,
        "recommended_actions": row.recommended_actions,
        "computed_at": row.computed_at.isoformat(),
    }
