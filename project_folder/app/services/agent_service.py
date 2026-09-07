"""Sandbox lifecycle. Lock order: task -> execution -> parse item -> attempt.

Every mutation rechecks fencing under these locks. Broker delivery/ACK is outside
this service. JSONB maps are replaced (not mutated in place) for ORM tracking.
"""
import hashlib
import json
import uuid
from datetime import timedelta

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.agent_auth import AgentIdentity, issue_token
from app.core.exceptions import ConflictError, NotFoundError, UnauthorizedError, ValidationAppError
from app.models.analysis_task import AnalysisTask
from app.models.asset import Asset
from app.models.execution import Execution
from app.models.execution_attempt import ExecutionAttempt
from app.models.parse_item import ParseItem
from app.models.result import Result
from app.schemas.agent import FailureSubmission, ResultSubmission
from app.schemas.workbench import WorkbenchData
from app.services.generated_result_service import record_generated_result
from app.services.workbench_service import content_digest
from app.utils import storage
from app.utils.datetime import utcnow

TERMINAL = {"SUCCEEDED", "FAILED", "TIMEOUT", "CANCELLED"}


def conflict(code, message):
    raise ConflictError(message, error_code=code)


async def scope(db: AsyncSession, execution_id: uuid.UUID):
    ids = (await db.execute(select(ParseItem.task_id, ParseItem.id).join(
        Execution, Execution.parse_id == ParseItem.id).where(Execution.id == execution_id))).one_or_none()
    if ids is None:
        raise NotFoundError("Execution not found")
    task = (await db.execute(select(AnalysisTask).where(
        AnalysisTask.id == ids.task_id).with_for_update())).scalar_one()
    execution = (await db.execute(select(Execution).where(
        Execution.id == execution_id).with_for_update())).scalar_one()
    item = (await db.execute(select(ParseItem).where(
        ParseItem.id == ids.id).with_for_update())).scalar_one()
    attempt = (await db.execute(select(ExecutionAttempt).where(
        ExecutionAttempt.execution_id == execution_id).order_by(
        ExecutionAttempt.attempt_no.desc()).limit(1).with_for_update())).scalar_one_or_none()
    return task, execution, item, attempt


def stopped_reason(task, execution, item):
    if task.deleted_at is not None or item.deleted_at is not None:
        return "TASK_OR_ITEM_DELETED"
    if task.status == "CANCELLED" or execution.status == "CANCELLED":
        return "EXECUTION_CANCELLED"
    return None


def expired(attempt):
    return min(attempt.lease_expires_at, attempt.token_expires_at) <= utcnow()


def retry_allowed(execution, attempt):
    return bool(attempt and execution.status in {"FAILED", "TIMEOUT"} and attempt.retryable
                and execution.retry_count < execution.max_retry_count)


def state(task, execution, item, attempt):
    reason = stopped_reason(task, execution, item)
    if reason is None and attempt:
        if attempt.status == "EXPIRED" or (attempt.status == "RUNNING" and expired(attempt)):
            reason = "ATTEMPT_EXPIRED"
        elif attempt.status != "RUNNING" or execution.status != "RUNNING":
            reason = "EXECUTION_TERMINAL"
    return {
        "execution_id": execution.id, "attempt_id": attempt.id if attempt else None,
        "attempt_no": attempt.attempt_no if attempt else None,
        "execution_status": execution.status, "attempt_status": attempt.status if attempt else None,
        "lease_expires_at": attempt.lease_expires_at if attempt else None,
        "token_expires_at": attempt.token_expires_at if attempt else None,
        "retry_allowed": not stopped_reason(task, execution, item) and retry_allowed(execution, attempt),
        "stop": reason is not None or execution.status in TERMINAL, "reason": reason,
    }


async def summarize(db, task):
    if task.status == "CANCELLED" or task.deleted_at is not None:
        return
    await db.flush()
    items = list((await db.scalars(select(ParseItem.id).where(
        ParseItem.task_id == task.id, ParseItem.deleted_at.is_(None),
        ParseItem.status.in_(["DRAFT", "READY"])))).all())
    if not items:
        return
    latest = list((await db.scalars(select(Execution).where(Execution.parse_id.in_(items))
        .distinct(Execution.parse_id).order_by(Execution.parse_id, Execution.created_at.desc(),
                                             Execution.id.desc()))).all())
    statuses = [e.status for e in latest]
    if len(latest) == len(items) and all(s in TERMINAL for s in statuses):
        task.status = ("FAILED" if any(s in {"FAILED", "TIMEOUT"} for s in statuses)
                       else "CANCELLED" if "CANCELLED" in statuses else "COMPLETED")
        task.completed_at = utcnow()
    else:
        task.status = "RUNNING" if any(s == "RUNNING" or s in TERMINAL for s in statuses) else "DISPATCHED"
        task.completed_at = None


async def reconcile(db, task, execution, item, attempt):
    reason = stopped_reason(task, execution, item)
    if reason and attempt and attempt.status == "RUNNING":
        attempt.status, attempt.finished_at = "CANCELLED", utcnow()
        if execution.status not in TERMINAL:
            execution.status, execution.finished_at = "CANCELLED", utcnow()
    elif attempt and attempt.status == "RUNNING" and expired(attempt):
        attempt.status, attempt.finished_at, attempt.retryable = "EXPIRED", utcnow(), True
        if execution.status == "RUNNING":
            execution.status, execution.finished_at = "TIMEOUT", utcnow()
            execution.error_code, execution.error_message = "ATTEMPT_EXPIRED", "Sandbox lease or token expired"
            await summarize(db, task)


async def claim(db, execution_id, attempt_id):
    task, execution, item, previous = await scope(db, execution_id)
    await reconcile(db, task, execution, item, previous)
    reason = stopped_reason(task, execution, item)
    if reason:
        await db.commit()
        conflict(reason, "Cancelled or deleted work cannot be claimed")
    if previous and previous.id == attempt_id:
        if previous.status != "RUNNING" or expired(previous):
            await db.commit()
            conflict("ATTEMPT_FINISHED", "This attempt has ended; inspect worker execution status")
        return {**state(task, execution, item, previous), "access_token": issue_token(previous),
                "token_type": "bearer", "heartbeat_interval_seconds": max(1, settings.AGENT_LEASE_SECONDS // 4)}
    # The parent execution lock serializes attempts for this execution. UUIDs are
    # globally unique; a transaction-scoped advisory lock serializes reuse across executions.
    from sqlalchemy import text
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"),
                     {"key": int.from_bytes(attempt_id.bytes[:8], "big", signed=True)})
    if await db.get(ExecutionAttempt, attempt_id) is not None:
        conflict("ATTEMPT_ID_EXISTS", "Attempt ID belongs to another claim")
    if previous:
        if not retry_allowed(execution, previous):
            await db.commit()
            conflict("EXECUTION_NOT_CLAIMABLE", "Attempt is active, terminal, or retry budget is exhausted")
        execution.retry_count += 1
    elif execution.status not in {"CREATED", "QUEUED"}:
        conflict("EXECUTION_NOT_CLAIMABLE", "Only an unclaimed CREATED or QUEUED execution may start")
    now = utcnow()
    end = (now + timedelta(seconds=settings.AGENT_TOKEN_TTL_SECONDS)).replace(microsecond=0)
    attempt = ExecutionAttempt(id=attempt_id, execution_id=execution.id,
        attempt_no=previous.attempt_no + 1 if previous else 1, status="RUNNING",
        token_id=uuid.uuid4(), token_expires_at=end,
        lease_expires_at=min(now + timedelta(seconds=settings.AGENT_LEASE_SECONDS), end),
        started_at=now, retryable=False, artifacts={}, receipts={})
    db.add(attempt)
    execution.status = "RUNNING"
    execution.started_at = execution.started_at or now
    execution.finished_at = None
    execution.error_code = execution.error_message = None
    task.status, task.completed_at = "RUNNING", None
    await db.commit()
    return {**state(task, execution, item, attempt), "access_token": issue_token(attempt),
            "token_type": "bearer", "heartbeat_interval_seconds": max(1, settings.AGENT_LEASE_SECONDS // 4)}


async def worker_state(db, execution_id):
    values = await scope(db, execution_id)
    await reconcile(db, *values)
    result_id = (await db.scalars(select(Result.id).where(Result.execution_id == execution_id)
                                 .order_by(Result.round_no.desc()).limit(1))).first()
    output = {**state(*values), "latest_result_id": result_id}
    await db.commit()
    return output


async def agent_scope(db, identity: AgentIdentity):
    values = await scope(db, identity.execution_id)
    attempt = values[3]
    if not attempt or attempt.id != identity.attempt_id:
        conflict("ATTEMPT_REPLACED", "This sandbox no longer owns the execution")
    if attempt.token_id != identity.token_id or attempt.token_expires_at <= utcnow():
        raise UnauthorizedError("Agent credential has been revoked or expired")
    return values


def ensure_current(values, *, allow_terminal=False):
    task, execution, item, attempt = values
    reason = stopped_reason(task, execution, item)
    if reason:
        conflict(reason, "Cancelled or deleted work cannot be accessed")
    if allow_terminal:
        return
    if expired(attempt):
        conflict("ATTEMPT_EXPIRED", "Attempt lease expired")
    if attempt.status != "RUNNING" or execution.status != "RUNNING":
        conflict("EXECUTION_NOT_RUNNING", "Attempt has ended")


async def heartbeat(db, identity):
    values = await agent_scope(db, identity)
    await reconcile(db, *values)
    output = state(*values)
    if not output["stop"]:
        attempt = values[3]
        attempt.lease_expires_at = min(utcnow() + timedelta(seconds=settings.AGENT_LEASE_SECONDS),
                                       attempt.token_expires_at)
        output = state(*values)
    await db.commit()
    return output


async def source_asset(db, values):
    _, execution, item, _ = values
    # Asset selection comes from the dispatch snapshot, never a caller URL/path.
    try:
        asset_id = uuid.UUID(str(execution.input_data.get("asset_id", item.asset_id)))
    except (ValueError, TypeError):
        raise ValidationAppError("Invalid execution source snapshot") from None
    asset = await db.get(Asset, asset_id)
    if asset is None or asset.deleted_at is not None or asset.user_id != values[0].user_id:
        raise NotFoundError("Execution source not found")
    return asset


async def context(db, identity):
    values = await agent_scope(db, identity)
    ensure_current(values)
    task, execution, item, attempt = values
    asset = await source_asset(db, values)
    return {"task_id": task.id, "parse_id": item.id, "execution_id": execution.id,
        "attempt_id": attempt.id, "name": item.name,
        "source": {"asset_id": asset.id, "file_name": asset.file_name,
            "content_url": "/internal/agent/source",
            "page_no": execution.input_data.get("page_no", item.page_no),
            "roi": execution.input_data.get("roi", {"x": item.x, "y": item.y,
                                                    "width": item.width, "height": item.height})},
        "flow": {"id": execution.flow_id, "version": execution.flow_version},
        "model": {"id": execution.model_id, "version": execution.model_version},
        "lease_expires_at": attempt.lease_expires_at, "token_expires_at": attempt.token_expires_at}


def fingerprint(operation, payload):
    raw = json.dumps({"operation": operation, "payload": payload.model_dump(mode="json")},
                     sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def replay(values, payload, operation):
    ensure_current(values, allow_terminal=True)
    receipt = values[3].receipts.get(str(payload.request_id))
    digest = fingerprint(operation, payload)
    if receipt:
        if receipt["fingerprint"] != digest:
            conflict("REQUEST_ID_CONFLICT", "Request ID was used with different content or operation")
        return receipt["response"], digest
    ensure_current(values)
    if len(values[3].receipts) >= 1000:
        conflict("ATTEMPT_REQUEST_LIMIT", "Attempt receipt limit reached")
    return None, digest


def remember(attempt, request_id, digest, response):
    attempt.receipts = {**attempt.receipts, str(request_id): {"fingerprint": digest, "response": response}}


async def submit_result(db, identity, payload: ResultSubmission, *, complete=False):
    values = await agent_scope(db, identity)
    prior, digest = replay(values, payload, "complete" if complete else "results")
    if prior is not None:
        return prior
    task, execution, _, attempt = values
    artifacts = []
    for artifact_id in payload.workbench.artifact_ids:
        entry = attempt.artifacts.get(str(artifact_id))
        if not entry or entry["result_id"] != str(payload.result_id):
            raise ValidationAppError("Artifact is not uploaded for this attempt and result", error_code="INVALID_ARTIFACT")
        artifacts.append({"id": artifact_id, "storage_key": entry["storage_key"], "media_type": entry["media_type"]})
    try:
        workbench = WorkbenchData(content_sha256=content_digest(payload.content), artifacts=artifacts,
            **payload.workbench.model_dump(exclude={"artifact_ids"}))
    except ValidationError:
        raise ValidationAppError("Invalid workbench artifact references", error_code="INVALID_WORKBENCH") from None
    # Serialize result UUID collisions across executions before the existing writer.
    from sqlalchemy import text
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"),
                     {"key": int.from_bytes(payload.result_id.bytes[:8], "big", signed=True)})
    result = await record_generated_result(db, execution_id=execution.id, result_id=payload.result_id,
        content=payload.content, parse_type=payload.type, content_type=payload.content_type,
        workbench=workbench, note=payload.note)
    ensure_current(values)
    if complete:
        execution.status = attempt.status = "SUCCEEDED"
        execution.finished_at = attempt.finished_at = utcnow()
        await summarize(db, task)
    response = {"request_id": str(payload.request_id), "result_id": str(result.id),
        "round_no": result.round_no, "execution_status": execution.status, "attempt_status": attempt.status}
    remember(attempt, payload.request_id, digest, response)
    await db.commit()
    return response


async def fail(db, identity, payload: FailureSubmission):
    values = await agent_scope(db, identity)
    prior, digest = replay(values, payload, "fail")
    if prior is not None:
        return prior
    task, execution, _, attempt = values
    execution.status = attempt.status = payload.status
    execution.finished_at = attempt.finished_at = utcnow()
    execution.error_code, execution.error_message = payload.error_code, payload.message
    attempt.retryable = payload.retryable
    await summarize(db, task)
    response = {"request_id": str(payload.request_id), "execution_status": execution.status,
                "attempt_status": attempt.status, "retry_allowed": retry_allowed(execution, attempt)}
    remember(attempt, payload.request_id, digest, response)
    await db.commit()
    return response


def image_type(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    raise ValidationAppError("Only PNG, JPEG and WebP signatures are accepted", error_code="INVALID_ARTIFACT")


async def upload_artifact(db, identity, result_id, artifact_id, file):
    # Read with a fixed cap before taking DB locks; reauthorize after upload.
    cap = settings.AGENT_MAX_ARTIFACT_MB * 1024 * 1024
    data = bytearray()
    try:
        while chunk := await file.read(min(1024 * 1024, cap + 1 - len(data))):
            data.extend(chunk)
            if len(data) > cap:
                raise ValidationAppError("Artifact exceeds size limit", error_code="ARTIFACT_TOO_LARGE")
    finally:
        await file.close()
    media_type, extension = image_type(data)
    digest = hashlib.sha256(data).hexdigest()
    values = await agent_scope(db, identity)
    ensure_current(values)
    attempt = values[3]
    response = {"artifact_id": str(artifact_id), "result_id": str(result_id),
                "media_type": media_type, "size": len(data), "sha256": digest}
    existing = attempt.artifacts.get(str(artifact_id))
    if existing:
        if {k: existing[k] for k in response} != response:
            conflict("ARTIFACT_ID_CONFLICT", "Artifact ID was used with different content")
        return response
    if await db.get(Result, result_id) is not None:
        conflict("RESULT_EXISTS", "Cannot add files to a saved result")
    if len(attempt.artifacts) >= settings.AGENT_MAX_ARTIFACTS:
        conflict("ARTIFACT_LIMIT", "Attempt artifact limit reached")
    # Unique immutable filenames also tolerate an orphan left by a failed DB commit.
    key = f"results/{identity.execution_id}/{result_id}/{attempt.id}/{artifact_id}-{uuid.uuid4()}.{extension}"
    path = storage.resolve(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as output:
            output.write(data)
        ensure_current(values)
        attempt.artifacts = {**attempt.artifacts, str(artifact_id): {**response, "storage_key": key}}
        await db.commit()
    except BaseException:
        # Commit outcome may be uncertain. Never unlink a possibly committed artifact;
        # a later orphan collector must check database references before removing it.
        await db.rollback()
        raise
    return response
