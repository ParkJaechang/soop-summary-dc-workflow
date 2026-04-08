import hashlib
import json
import re
import sqlite3
import threading
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, model_validator


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "dc_publisher.db"

app = FastAPI(title="DC Publisher MVP")
db_lock = threading.Lock()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS publish_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'dcinside_gallery',
    gallery_id TEXT NOT NULL DEFAULT '',
    board_url TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS post_jobs (
    id TEXT PRIMARY KEY,
    target_id INTEGER NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'manual',
    source_ref TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    attachments_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    dedupe_key TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    approved_at TEXT,
    queued_at TEXT,
    posted_at TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (target_id) REFERENCES publish_targets(id)
);

CREATE TABLE IF NOT EXISTS publish_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    adapter TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    message TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (job_id) REFERENCES post_jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_post_jobs_target_status
ON post_jobs(target_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_post_jobs_dedupe
ON post_jobs(dedupe_key);

CREATE INDEX IF NOT EXISTS idx_publish_attempts_job
ON publish_attempts(job_id, started_at DESC);
"""


VALID_JOB_STATUS = {"draft", "approved", "queued", "prepared", "posted", "failed", "cancelled"}
SUMMARY_BRIDGE_CONTRACT_VERSION = "summary-publisher-bridge/v1"
SUMMARY_POST_SOURCE_TYPE = "summary_payload"
SOOP_VOD_URL_RE = re.compile(r"^https?://(?:[^/]+\.)?sooplive\.co\.kr/player/(?P<vod_id>\d+)(?:[/?#].*)?$", re.IGNORECASE)
SOOP_VOD_ID_RE = re.compile(r"^(?:vod[-:_])?(?P<vod_id>\d+)$", re.IGNORECASE)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db_lock, closing(get_conn()) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


class PublishTargetCreate(BaseModel):
    name: str = Field(min_length=1)
    platform: str = "dcinside_gallery"
    gallery_id: str = ""
    board_url: str = ""
    active: bool = True


class PublishTargetUpdate(BaseModel):
    name: str | None = None
    platform: str | None = None
    gallery_id: str | None = None
    board_url: str | None = None
    active: bool | None = None


class PostJobCreate(BaseModel):
    target_id: int
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    source_type: str = "manual"
    source_ref: str = ""
    attachments: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    dedupe_key: str = ""


class PostJobUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    attachments: list[str] | None = None
    metadata: dict[str, Any] | None = None
    dedupe_key: str | None = None
    status: str | None = None
    error: str | None = None


class SummaryDraftBridgePayload(BaseModel):
    target_id: int
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    producer: str = Field(min_length=1)
    source_ref: str = ""
    source_id: str = ""
    source_url: str = ""
    attachments: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    contract_version: str = SUMMARY_BRIDGE_CONTRACT_VERSION

    @model_validator(mode="after")
    def validate_source_identity(self) -> "SummaryDraftBridgePayload":
        if not any(
            (
                self.source_ref.strip(),
                self.source_id.strip(),
                self.source_url.strip(),
            )
        ):
            raise ValueError("At least one of source_ref, source_id, or source_url is required")
        return self


class CanonicalSummaryPayload(BaseModel):
    contract_version: str = Field(min_length=1)
    producer: dict[str, Any] = Field(default_factory=dict)
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    dedupe_basis: dict[str, Any] = Field(default_factory=dict)


class PublishResult(BaseModel):
    job_id: str
    status: str
    adapter: str
    message: str


@dataclass
class PublishPayload:
    job_id: str
    title: str
    body: str
    attachments: list[str]
    metadata: dict[str, Any]
    target: dict[str, Any]


class PublisherAdapter(Protocol):
    adapter_name: str

    def publish(self, payload: PublishPayload) -> PublishResult:
        ...


class ManualPublisherAdapter:
    adapter_name = "manual"

    def publish(self, payload: PublishPayload) -> PublishResult:
        message = (
            "Payload prepared for review. "
            "No site submission was attempted in manual mode."
        )
        return PublishResult(
            job_id=payload.job_id,
            status="prepared",
            adapter=self.adapter_name,
            message=message,
        )


class DcInsidePublisherAdapter:
    adapter_name = "dcinside_browser"

    def publish(self, payload: PublishPayload) -> PublishResult:
        raise NotImplementedError(
            "The browser publisher is intentionally not implemented in this MVP. "
            "Add it only after confirming the allowed posting flow and required selectors."
        )


def get_target_or_404(conn: sqlite3.Connection, target_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM publish_targets WHERE id = ?", (target_id,)).fetchone()
    target = row_to_dict(row)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    return target


def get_job_or_404(conn: sqlite3.Connection, job_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM post_jobs WHERE id = ?", (job_id,)).fetchone()
    job = row_to_dict(row)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return hydrate_job(job)


def hydrate_job(job: dict[str, Any]) -> dict[str, Any]:
    job["attachments"] = json.loads(job.pop("attachments_json", "[]"))
    job["metadata"] = json.loads(job.pop("metadata_json", "{}"))
    return job


def insert_attempt(conn: sqlite3.Connection, job_id: str, adapter: str, status: str, message: str) -> int:
    started_at = now_iso()
    cursor = conn.execute(
        """
        INSERT INTO publish_attempts (job_id, adapter, status, started_at, finished_at, message)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (job_id, adapter, status, started_at, started_at, message),
    )
    return int(cursor.lastrowid)


def find_existing_job_by_dedupe(
    conn: sqlite3.Connection,
    dedupe_key: str,
    exclude_job_id: str | None = None,
) -> sqlite3.Row | None:
    normalized = dedupe_key.strip()
    if not normalized:
        return None
    query = "SELECT id, status FROM post_jobs WHERE dedupe_key = ?"
    values: list[Any] = [normalized]
    if exclude_job_id:
        query += " AND id != ?"
        values.append(exclude_job_id)
    query += " ORDER BY created_at DESC LIMIT 1"
    return conn.execute(query, tuple(values)).fetchone()


def canonicalize_summary_source_identity(value: str) -> str | None:
    normalized = value.strip()
    if not normalized:
        return None
    url_match = SOOP_VOD_URL_RE.fullmatch(normalized)
    if url_match:
        return f"soop_vod:{url_match.group('vod_id')}"
    id_match = SOOP_VOD_ID_RE.fullmatch(normalized)
    if id_match:
        return f"soop_vod:{id_match.group('vod_id')}"
    return None


def resolve_summary_source_identity(payload: SummaryDraftBridgePayload) -> tuple[str, str]:
    provided_identities = [
        (field_name, value.strip())
        for field_name, value in (
            ("source_url", payload.source_url),
            ("source_id", payload.source_id),
            ("source_ref", payload.source_ref),
        )
        if value.strip()
    ]
    resolved_source_ref = provided_identities[0][1]
    canonical_identities = {
        canonicalize_summary_source_identity(value)
        for _, value in provided_identities
    }
    if None in canonical_identities:
        raise HTTPException(
            status_code=422,
            detail=(
                "Summary bridge requires a canonical SOOP VOD source identity. "
                "Use a matching source_url, source_id, or source_ref such as "
                "https://vod.sooplive.co.kr/player/123456 or vod-123456."
            ),
        )
    if len(canonical_identities) != 1:
        raise HTTPException(
            status_code=422,
            detail="Summary bridge source identities disagree; send matching source_url, source_id, or source_ref values",
        )
    canonical_source_ref = canonical_identities.pop()
    return resolved_source_ref, canonical_source_ref


def build_summary_dedupe_key(
    payload: SummaryDraftBridgePayload,
    canonical_source_ref: str,
) -> tuple[str, dict[str, Any]]:
    dedupe_basis = {
        "contract_version": payload.contract_version.strip() or SUMMARY_BRIDGE_CONTRACT_VERSION,
        "target_id": payload.target_id,
        "producer": payload.producer.strip(),
        "canonical_source_ref": canonical_source_ref,
    }
    basis_json = json.dumps(dedupe_basis, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(basis_json.encode("utf-8")).hexdigest()[:24]
    dedupe_key = f"summary-draft:v1:{payload.target_id}:{digest}"
    return dedupe_key, dedupe_basis


def build_summary_bridge_metadata(
    payload: SummaryDraftBridgePayload,
    source_ref: str,
    canonical_source_ref: str,
    dedupe_basis: dict[str, Any],
) -> dict[str, Any]:
    metadata = dict(payload.metadata)
    existing_bridge = metadata.get("publisher_bridge")
    bridge_metadata = dict(existing_bridge) if isinstance(existing_bridge, dict) else {}
    bridge_metadata.update(
        {
            "contract_version": payload.contract_version.strip() or SUMMARY_BRIDGE_CONTRACT_VERSION,
            "draft_created_via": "app_dc_publisher.summary_bridge",
            "draft_only": True,
            "producer": payload.producer.strip(),
            "source_ref": source_ref,
            "canonical_source_ref": canonical_source_ref,
            "source_id": payload.source_id.strip(),
            "source_url": payload.source_url.strip(),
            "dedupe_basis": dedupe_basis,
        }
    )
    metadata["publisher_bridge"] = bridge_metadata
    return metadata


def build_summary_bridge_payload_from_canonical_summary(
    canonical_payload: dict[str, Any],
    target_id: int,
) -> SummaryDraftBridgePayload:
    parsed = CanonicalSummaryPayload.model_validate(canonical_payload)
    producer_name = str(parsed.producer.get("name", "")).strip()
    if not producer_name:
        raise HTTPException(status_code=422, detail="Canonical summary payload is missing producer.name")

    source_metadata = parsed.metadata.get("source")
    if not isinstance(source_metadata, dict):
        raise HTTPException(status_code=422, detail="Canonical summary payload is missing metadata.source")

    canonical_source_url = str(source_metadata.get("canonical_source_url", "")).strip()
    source_url = str(source_metadata.get("source_url", "")).strip()
    source_id = str(source_metadata.get("source_id", "")).strip()
    resolved_source_url = canonical_source_url or source_url
    if not any((resolved_source_url, source_id)):
        raise HTTPException(
            status_code=422,
            detail="Canonical summary payload must include metadata.source.canonical_source_url, source_url, or source_id",
        )

    metadata = dict(parsed.metadata)
    metadata["summary_payload"] = {
        "contract_version": parsed.contract_version,
        "producer": parsed.producer,
        "dedupe_basis": parsed.dedupe_basis,
    }

    return SummaryDraftBridgePayload(
        target_id=target_id,
        title=parsed.title.strip(),
        body=parsed.body.strip(),
        producer=producer_name,
        source_url=resolved_source_url,
        source_id=source_id,
        metadata=metadata,
    )


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/api/health")
def api_health() -> dict[str, Any]:
    with db_lock, closing(get_conn()) as conn:
        target_count = conn.execute("SELECT COUNT(*) FROM publish_targets").fetchone()[0]
        job_count = conn.execute("SELECT COUNT(*) FROM post_jobs").fetchone()[0]
    return {
        "status": "ok",
        "db_path": str(DB_PATH),
        "targets": target_count,
        "jobs": job_count,
    }


@app.get("/api/targets")
def list_targets(active_only: bool = False) -> list[dict[str, Any]]:
    query = "SELECT * FROM publish_targets"
    params: tuple[Any, ...] = ()
    if active_only:
        query += " WHERE active = ?"
        params = (1,)
    query += " ORDER BY id DESC"
    with db_lock, closing(get_conn()) as conn:
        rows = conn.execute(query, params).fetchall()
    return [row_to_dict(row) for row in rows]


@app.post("/api/targets")
def create_target(payload: PublishTargetCreate) -> dict[str, Any]:
    timestamp = now_iso()
    with db_lock, closing(get_conn()) as conn:
        cursor = conn.execute(
            """
            INSERT INTO publish_targets (name, platform, gallery_id, board_url, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.name.strip(),
                payload.platform.strip(),
                payload.gallery_id.strip(),
                payload.board_url.strip(),
                1 if payload.active else 0,
                timestamp,
                timestamp,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM publish_targets WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_dict(row)


@app.patch("/api/targets/{target_id}")
def update_target(target_id: int, payload: PublishTargetUpdate) -> dict[str, Any]:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No fields to update")
    set_parts = []
    values: list[Any] = []
    for key, value in changes.items():
        set_parts.append(f"{key} = ?")
        if key == "active":
            values.append(1 if value else 0)
        else:
            values.append(value.strip() if isinstance(value, str) else value)
    set_parts.append("updated_at = ?")
    values.append(now_iso())
    values.append(target_id)
    with db_lock, closing(get_conn()) as conn:
        get_target_or_404(conn, target_id)
        conn.execute(f"UPDATE publish_targets SET {', '.join(set_parts)} WHERE id = ?", values)
        conn.commit()
        row = conn.execute("SELECT * FROM publish_targets WHERE id = ?", (target_id,)).fetchone()
    return row_to_dict(row)


@app.delete("/api/targets/{target_id}")
def delete_target(target_id: int) -> dict[str, Any]:
    with db_lock, closing(get_conn()) as conn:
        get_target_or_404(conn, target_id)
        linked_jobs = conn.execute("SELECT COUNT(*) FROM post_jobs WHERE target_id = ?", (target_id,)).fetchone()[0]
        if linked_jobs:
            raise HTTPException(status_code=400, detail="Target has linked jobs and cannot be deleted")
        conn.execute("DELETE FROM publish_targets WHERE id = ?", (target_id,))
        conn.commit()
    return {"deleted": True, "target_id": target_id}


@app.get("/api/jobs")
def list_jobs(
    status: str | None = Query(default=None),
    target_id: int | None = Query(default=None),
) -> list[dict[str, Any]]:
    clauses = []
    values: list[Any] = []
    if status:
        clauses.append("j.status = ?")
        values.append(status)
    if target_id is not None:
        clauses.append("j.target_id = ?")
        values.append(target_id)
    query = """
    SELECT
        j.*,
        t.name AS target_name,
        t.platform AS target_platform,
        t.gallery_id AS target_gallery_id
    FROM post_jobs j
    JOIN publish_targets t ON t.id = j.target_id
    """
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY j.created_at DESC"
    with db_lock, closing(get_conn()) as conn:
        rows = conn.execute(query, values).fetchall()
    jobs = []
    for row in rows:
        item = hydrate_job(row_to_dict(row))
        jobs.append(item)
    return jobs


@app.post("/api/jobs")
def create_job(payload: PostJobCreate) -> dict[str, Any]:
    timestamp = now_iso()
    job_id = uuid.uuid4().hex[:12]
    with db_lock, closing(get_conn()) as conn:
        get_target_or_404(conn, payload.target_id)
        if payload.dedupe_key:
            existing = find_existing_job_by_dedupe(conn, payload.dedupe_key)
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail=f"Duplicate dedupe_key already exists on job {existing['id']} ({existing['status']})",
                )
        conn.execute(
            """
            INSERT INTO post_jobs (
                id, target_id, source_type, source_ref, title, body,
                attachments_json, metadata_json, dedupe_key, status,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)
            """,
            (
                job_id,
                payload.target_id,
                payload.source_type.strip(),
                payload.source_ref.strip(),
                payload.title.strip(),
                payload.body,
                json.dumps(payload.attachments, ensure_ascii=False),
                json.dumps(payload.metadata, ensure_ascii=False),
                payload.dedupe_key.strip(),
                timestamp,
                timestamp,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM post_jobs WHERE id = ?", (job_id,)).fetchone()
    return hydrate_job(row_to_dict(row))


@app.patch("/api/jobs/{job_id}")
def update_job(job_id: str, payload: PostJobUpdate) -> dict[str, Any]:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "status" in changes or "error" in changes:
        raise HTTPException(
            status_code=400,
            detail="Use dedicated approval, queueing, dispatch, or attempt endpoints for workflow state changes",
        )
    set_parts = []
    values: list[Any] = []
    with db_lock, closing(get_conn()) as conn:
        get_job_or_404(conn, job_id)
        if "dedupe_key" in changes and changes["dedupe_key"]:
            existing = find_existing_job_by_dedupe(conn, changes["dedupe_key"], exclude_job_id=job_id)
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail=f"Duplicate dedupe_key already exists on job {existing['id']} ({existing['status']})",
                )
        for key, value in changes.items():
            db_key = key
            db_value = value
            if key == "attachments":
                db_key = "attachments_json"
                db_value = json.dumps(value, ensure_ascii=False)
            elif key == "metadata":
                db_key = "metadata_json"
                db_value = json.dumps(value, ensure_ascii=False)
            elif key in {"title", "body", "dedupe_key"} and isinstance(value, str):
                db_value = value.strip()
            set_parts.append(f"{db_key} = ?")
            values.append(db_value)
        set_parts.append("updated_at = ?")
        values.append(now_iso())
        values.append(job_id)
        conn.execute(f"UPDATE post_jobs SET {', '.join(set_parts)} WHERE id = ?", values)
        conn.commit()
        row = conn.execute("SELECT * FROM post_jobs WHERE id = ?", (job_id,)).fetchone()
    return hydrate_job(row_to_dict(row))


@app.post("/api/summary-bridge/draft-job")
def create_draft_job_from_summary(payload: SummaryDraftBridgePayload) -> dict[str, Any]:
    source_ref, canonical_source_ref = resolve_summary_source_identity(payload)
    dedupe_key, dedupe_basis = build_summary_dedupe_key(payload, canonical_source_ref)
    job_payload = PostJobCreate(
        target_id=payload.target_id,
        title=payload.title.strip(),
        body=payload.body.strip(),
        source_type=SUMMARY_POST_SOURCE_TYPE,
        source_ref=source_ref,
        attachments=payload.attachments,
        metadata=build_summary_bridge_metadata(payload, source_ref, canonical_source_ref, dedupe_basis),
        dedupe_key=dedupe_key,
    )
    return create_job(job_payload)


@app.post("/api/jobs/{job_id}/approve")
def approve_job(job_id: str) -> dict[str, Any]:
    timestamp = now_iso()
    with db_lock, closing(get_conn()) as conn:
        job = get_job_or_404(conn, job_id)
        if job["status"] != "draft":
            raise HTTPException(status_code=400, detail="Only draft jobs can be approved")
        conn.execute(
            "UPDATE post_jobs SET status = 'approved', approved_at = ?, updated_at = ? WHERE id = ?",
            (timestamp, timestamp, job_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM post_jobs WHERE id = ?", (job_id,)).fetchone()
    return hydrate_job(row_to_dict(row))


@app.post("/api/jobs/{job_id}/queue")
def queue_job(job_id: str) -> dict[str, Any]:
    timestamp = now_iso()
    with db_lock, closing(get_conn()) as conn:
        job = get_job_or_404(conn, job_id)
        if job["status"] not in {"approved", "failed"}:
            raise HTTPException(status_code=400, detail="Only approved or failed jobs can be queued")
        conn.execute(
            "UPDATE post_jobs SET status = 'queued', queued_at = ?, error = NULL, updated_at = ? WHERE id = ?",
            (timestamp, timestamp, job_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM post_jobs WHERE id = ?", (job_id,)).fetchone()
    return hydrate_job(row_to_dict(row))


@app.post("/api/jobs/{job_id}/dispatch")
def dispatch_job(job_id: str, adapter: str = Query(default="manual")) -> dict[str, Any]:
    adapter_map: dict[str, PublisherAdapter] = {
        "manual": ManualPublisherAdapter(),
        "dcinside_browser": DcInsidePublisherAdapter(),
    }
    chosen = adapter_map.get(adapter)
    if not chosen:
        raise HTTPException(status_code=400, detail="Unknown adapter")

    with db_lock, closing(get_conn()) as conn:
        job = get_job_or_404(conn, job_id)
        if job["status"] != "queued":
            raise HTTPException(status_code=400, detail="Only queued jobs can be dispatched")
        target = get_target_or_404(conn, int(job["target_id"]))
        payload = PublishPayload(
            job_id=job["id"],
            title=job["title"],
            body=job["body"],
            attachments=job["attachments"],
            metadata=job["metadata"],
            target=target,
        )
        try:
            result = chosen.publish(payload)
            insert_attempt(conn, job_id=job_id, adapter=result.adapter, status=result.status, message=result.message)
            conn.execute(
                "UPDATE post_jobs SET status = ?, error = NULL, updated_at = ? WHERE id = ?",
                (result.status, now_iso(), job_id),
            )
            conn.commit()
        except NotImplementedError as exc:
            message = str(exc)
            insert_attempt(conn, job_id=job_id, adapter=adapter, status="failed", message=message)
            conn.execute(
                "UPDATE post_jobs SET status = 'failed', error = ?, updated_at = ? WHERE id = ?",
                (message, now_iso(), job_id),
            )
            conn.commit()
        row = conn.execute("SELECT * FROM post_jobs WHERE id = ?", (job_id,)).fetchone()
    return hydrate_job(row_to_dict(row))


@app.post("/api/jobs/{job_id}/mark-posted")
def mark_posted(job_id: str, note: str = Query(default="Manual confirmation")) -> dict[str, Any]:
    timestamp = now_iso()
    with db_lock, closing(get_conn()) as conn:
        job = get_job_or_404(conn, job_id)
        if job["status"] not in {"prepared", "queued"}:
            raise HTTPException(status_code=400, detail="Only prepared or queued jobs can be marked as posted")
        insert_attempt(conn, job_id=job_id, adapter="manual-confirmation", status="posted", message=note)
        conn.execute(
            "UPDATE post_jobs SET status = 'posted', posted_at = ?, error = NULL, updated_at = ? WHERE id = ?",
            (timestamp, timestamp, job_id),
            )
        conn.commit()
        row = conn.execute("SELECT * FROM post_jobs WHERE id = ?", (job_id,)).fetchone()
    return hydrate_job(row_to_dict(row))


@app.get("/api/jobs/{job_id}/attempts")
def list_attempts(job_id: str) -> list[dict[str, Any]]:
    with db_lock, closing(get_conn()) as conn:
        get_job_or_404(conn, job_id)
        rows = conn.execute(
            "SELECT * FROM publish_attempts WHERE job_id = ? ORDER BY started_at DESC, id DESC",
            (job_id,),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


if __name__ == "__main__":
    uvicorn.run("app_dc_publisher:app", host="127.0.0.1", port=8091, reload=False)
