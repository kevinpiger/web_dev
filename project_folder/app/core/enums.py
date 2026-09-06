"""All status enums, matching freeze doc §23. Stored as VARCHAR + CHECK, not PG ENUM."""

from enum import StrEnum


class RoleCode(StrEnum):
    ADMIN = "ADMIN"
    USER = "USER"
    REVIEWER = "REVIEWER"


class AssetStatus(StrEnum):
    UPLOADING = "UPLOADING"
    READY = "READY"
    FAILED = "FAILED"


class AssetFileType(StrEnum):
    PDF = "PDF"
    IMAGE = "IMAGE"
    SVG = "SVG"
    OTHER = "OTHER"


class StorageType(StrEnum):
    LOCAL = "LOCAL"
    NAS = "NAS"
    S3 = "S3"
    MINIO = "MINIO"


class AnalysisTaskStatus(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskDisplayStatus(StrEnum):
    """Not persisted. Collapses task status + live execution counts into the four
    states the 任務總覽 screen shows, plus CANCELLED so a 中斷 task isn't mislabelled."""

    PENDING = "PENDING"  # 等待
    RUNNING = "RUNNING"  # 執行中
    FAILED = "FAILED"  # 錯誤
    COMPLETED = "COMPLETED"  # 完成
    CANCELLED = "CANCELLED"  # 已中斷


class ParseItemStatus(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    REJECTED = "REJECTED"


class ExecutionStatus(StrEnum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"


class ExecutionReviewStatus(StrEnum):
    """§3 增補：人工簽核狀態，與 execution.status（AI 該輪成敗）分開。"""

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class AgentRunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ResultStatus(StrEnum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class OutboxEventStatus(StrEnum):
    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class OutboxEventType(StrEnum):
    EXECUTION_CREATED = "EXECUTION_CREATED"
