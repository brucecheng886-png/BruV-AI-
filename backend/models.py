"""
SQLAlchemy ORM Models（對應 init_db.sql）
"""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Float, ForeignKey,
    Integer, LargeBinary, Numeric, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def _uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, default="user")
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    fido_credentials: Mapped[list["FIDOCredential"]] = relationship(
        "FIDOCredential", back_populates="user", cascade="all, delete-orphan"
    )


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(String(20), default="#2563eb")
    icon: Mapped[str | None] = mapped_column(String(50), default="📚")
    embedding_model: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    embedding_provider: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    chunk_size: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    chunk_overlap: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    language: Mapped[str | None] = mapped_column(String, nullable=True, default="auto")
    rerank_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    default_top_k: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    agent_prompt: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    documents: Mapped[list["Document"]] = relationship(
        "Document", back_populates="knowledge_base",
        foreign_keys="Document.knowledge_base_id",
    )
    doc_assoc: Mapped[list["DocumentKnowledgeBase"]] = relationship(
        "DocumentKnowledgeBase", back_populates="knowledge_base"
    )


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    color: Mapped[str] = mapped_column(String(20), default="#409eff")
    description: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("tags.id", ondelete="SET NULL"))
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    children: Mapped[list["Tag"]] = relationship("Tag", back_populates="parent", foreign_keys="Tag.parent_id")
    parent: Mapped["Tag | None"] = relationship("Tag", back_populates="children", remote_side="Tag.id", foreign_keys="Tag.parent_id")
    doc_assoc: Mapped[list["DocumentTag"]] = relationship("DocumentTag", back_populates="tag", cascade="all, delete")


class DocumentKnowledgeBase(Base):
    __tablename__ = "document_knowledge_bases"

    doc_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    kb_id: Mapped[str] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), primary_key=True)
    score: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(20), default="auto")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped["Document"] = relationship("Document", back_populates="kb_assoc")
    knowledge_base: Mapped["KnowledgeBase"] = relationship("KnowledgeBase", back_populates="doc_assoc")


class DocumentTag(Base):
    __tablename__ = "document_tags"

    doc_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[str] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    confidence: Mapped[float | None] = mapped_column(Float)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tag: Mapped["Tag"] = relationship("Tag", back_populates="doc_assoc")
    document: Mapped["Document"] = relationship("Document", back_populates="tags_assoc")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str | None] = mapped_column(String)
    file_path: Mapped[str | None] = mapped_column(String)
    file_type: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict)
    knowledge_base_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="SET NULL"))
    suggested_kb_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="SET NULL"), nullable=True)
    suggested_kb_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_tags: Mapped[list] = mapped_column(JSONB, default=list)
    cover_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingestion_warnings: Mapped[list] = mapped_column(JSONB, default=list)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    chunks: Mapped[list["Chunk"]] = relationship("Chunk", back_populates="document", cascade="all, delete")
    knowledge_base: Mapped["KnowledgeBase | None"] = relationship(
        "KnowledgeBase", back_populates="documents",
        foreign_keys="Document.knowledge_base_id",
    )
    tags_assoc: Mapped[list["DocumentTag"]] = relationship("DocumentTag", back_populates="document", cascade="all, delete")
    kb_assoc: Mapped[list["DocumentKnowledgeBase"]] = relationship(
        "DocumentKnowledgeBase", back_populates="document", cascade="all, delete"
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    doc_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_id: Mapped[str | None] = mapped_column(String)
    window_context: Mapped[str | None] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped["Document"] = relationship("Document", back_populates="chunks")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String, default="新對話")
    kb_scope_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="SET NULL"))
    doc_scope_ids: Mapped[list] = mapped_column(JSONB, default=list)
    tag_scope_ids: Mapped[list] = mapped_column(JSONB, default=list)
    agent_type: Mapped[str] = mapped_column(String(20), default="chat", server_default="chat")
    agent_meta: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summarized_up_to: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    summary_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    messages: Mapped[list["Message"]] = relationship("Message", back_populates="conversation", cascade="all, delete", foreign_keys="Message.conv_id")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    conv_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[list] = mapped_column(JSONB, default=list)
    regenerated_from: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages", foreign_keys="Message.conv_id")


class Plugin(Base):
    __tablename__ = "plugins"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # webhook | builtin
    plugin_type: Mapped[str] = mapped_column(String, default="webhook")
    # notion | chart | calculator | email | rss | weather | github | ...（builtin 時使用）
    builtin_key: Mapped[str | None] = mapped_column(String)
    input_schema: Mapped[dict] = mapped_column(JSONB, default=dict)
    # 插件設定（非敏感：host/port/sender...）
    plugin_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    endpoint: Mapped[str] = mapped_column(String, default="")    # webhook 用
    auth_header: Mapped[str | None] = mapped_column(String)       # Fernet 加密（webhook bearer / builtin token）
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LLMModel(Base):
    __tablename__ = "llm_models"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    family: Mapped[str | None] = mapped_column(String)
    developer: Mapped[str | None] = mapped_column(String)
    params_b: Mapped[float | None] = mapped_column(Float)
    context_length: Mapped[int | None] = mapped_column(Integer)
    license: Mapped[str | None] = mapped_column(String)
    tags: Mapped[list] = mapped_column(ARRAY(String), default=list)
    benchmarks: Mapped[dict] = mapped_column(JSONB, default=dict)
    quantizations: Mapped[dict] = mapped_column(JSONB, default=dict)
    ollama_id: Mapped[str | None] = mapped_column(String)
    hf_id: Mapped[str | None] = mapped_column(String)
    # RAGFlow-aligned fields
    model_type: Mapped[str] = mapped_column(String(20), default="chat")
    max_tokens: Mapped[int | None] = mapped_column(Integer)
    vision_support: Mapped[bool] = mapped_column(Boolean, default=False)
    provider: Mapped[str | None] = mapped_column(String(30))
    base_url: Mapped[str | None] = mapped_column(String(256))
    api_key:  Mapped[str | None] = mapped_column(Text)            # Fernet 加密後的 API Key
    # 治理欄位（Phase A2）
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    monthly_quota_usd: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LLMUsageLog(Base):
    """Phase B1: LLM 呼叫使用量日誌"""
    __tablename__ = "llm_usage_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conv_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    agent_task_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    call_type: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OntologyReviewQueue(Base):
    __tablename__ = "ontology_review_queue"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    entity_name: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    source_doc_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OntologyBlocklist(Base):
    __tablename__ = "ontology_blocklist"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    blocked_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)   # SHA-256 hex
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    template_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    required_vars: Mapped[list] = mapped_column(JSONB, default=list)
    optional_vars: Mapped[list] = mapped_column(JSONB, default=list)
    example_triggers: Mapped[list] = mapped_column(JSONB, default=list)
    pit_warnings: Mapped[list] = mapped_column(JSONB, default=list)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FIDOCredential(Base):
    __tablename__ = "fido_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, unique=True, nullable=False)
    public_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sign_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False, default="我的安全金鑰")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="fido_credentials")


class AuditLog(Base):
    """稽核日誌：記錄每一次重要操作"""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    user_email: Mapped[str | None] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # e.g. "DELETE_DOCUMENT"
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)  # e.g. "document"
    resource_id: Mapped[str | None] = mapped_column(String, nullable=True)
    method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class DocumentAccessLog(Base):
    """文件存取日誌：記錄每一次文件瀏覽或下載動作"""
    __tablename__ = "document_access_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(10), nullable=False)  # "view" | "download"
    accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)


class KBPermission(Base):
    """知識庫存取權限：控制非管理員使用者可以讀取哪些知識庫"""
    __tablename__ = "kb_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kb_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    permission: Mapped[str] = mapped_column(String(20), nullable=False, default="read")  # "read" | "write"
    granted_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InviteToken(Base):
    """邀請 Token：管理員產生邀請連結，讓新使用者自助註冊"""
    __tablename__ = "invite_tokens"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)   # 預填 email，可空
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── 共享硬碟模組 ────────────────────────────────────────────────

class Folder(Base):
    """共享硬碟資料夾（獨立於知識庫，支援階層與白名單）"""
    __tablename__ = "folders"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("folders.id", ondelete="CASCADE"), nullable=True
    )
    icon: Mapped[str | None] = mapped_column(String(50), default="📁")
    color: Mapped[str | None] = mapped_column(String(20), default="#2563eb")
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    children: Mapped[list["Folder"]] = relationship(
        "Folder", back_populates="parent", foreign_keys="Folder.parent_id"
    )
    parent: Mapped["Folder | None"] = relationship(
        "Folder", back_populates="children",
        remote_side="Folder.id", foreign_keys="Folder.parent_id"
    )
    doc_assoc: Mapped[list["FolderDocument"]] = relationship(
        "FolderDocument", back_populates="folder", cascade="all, delete"
    )
    permissions: Mapped[list["FolderPermission"]] = relationship(
        "FolderPermission", back_populates="folder", cascade="all, delete"
    )


class FolderDocument(Base):
    """資料夾與文件的多對多關聯"""
    __tablename__ = "folder_documents"

    folder_id: Mapped[str] = mapped_column(
        ForeignKey("folders.id", ondelete="CASCADE"), primary_key=True
    )
    doc_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    added_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    folder: Mapped["Folder"] = relationship("Folder", back_populates="doc_assoc")
    document: Mapped["Document"] = relationship("Document")


class FolderPermission(Base):
    """資料夾白名單（授父層自動繼承至子層）"""
    __tablename__ = "folder_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    folder_id: Mapped[str] = mapped_column(
        ForeignKey("folders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    permission: Mapped[str] = mapped_column(
        String(20), nullable=False, default="read"
    )  # "read" | "write" | "manage"
    granted_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    folder: Mapped["Folder"] = relationship("Folder", back_populates="permissions")
