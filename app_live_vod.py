import json
import os
import re
import socket
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any
from urllib import parse, request
from urllib.error import HTTPError, URLError

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    webdriver = None
    Options = None
    Service = None
    By = None
    EC = None
    WebDriverWait = None
    ChromeDriverManager = None

BASE_DIR = Path(__file__).resolve().parent
WEBAPP_DIR = BASE_DIR / "webapp"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "soop_live_vod.db"
UI_PATH = WEBAPP_DIR / "live_vod.html"
SOOP_CLIENT_ID = os.getenv("SOOP_CLIENT_ID", "").strip()
LIVE_PAGE_LIMIT = int(os.getenv("SOOP_LIVE_PAGE_LIMIT", "5"))
LIVE_REFRESH_SECONDS = int(os.getenv("SOOP_LIVE_REFRESH_SECONDS", "120"))
VOD_REFRESH_SECONDS = int(os.getenv("SOOP_VOD_REFRESH_SECONDS", "900"))
SCHEDULER_TICK_SECONDS = float(os.getenv("SOOP_SCHEDULER_TICK_SECONDS", "1"))
SCHEDULER_STARTUP_LIVE_DELAY_SECONDS = float(os.getenv("SOOP_SCHEDULER_STARTUP_LIVE_DELAY_SECONDS", "3"))
SCHEDULER_STARTUP_VOD_DELAY_SECONDS = float(os.getenv("SOOP_SCHEDULER_STARTUP_VOD_DELAY_SECONDS", "10"))
SCHEDULER_STOP_JOIN_SECONDS = float(os.getenv("SOOP_SCHEDULER_STOP_JOIN_SECONDS", "2"))
HTTP_TIMEOUT = int(os.getenv("SOOP_HTTP_TIMEOUT", "15"))
COLLECTOR_BACKOFF_SECONDS = int(os.getenv("SOOP_COLLECTOR_BACKOFF_SECONDS", "30"))
COLLECTOR_BACKOFF_MAX_SECONDS = int(os.getenv("SOOP_COLLECTOR_BACKOFF_MAX_SECONDS", "900"))
USE_BROWSER_FALLBACK = os.getenv("SOOP_USE_BROWSER_FALLBACK", "1").strip().lower() not in {"0", "false", "no"}
COOKIE_PATH = BASE_DIR / "cookies_soop.pkl"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
)

app = FastAPI(title="SOOP Live VOD WebApp")
db_lock = threading.Lock()
run_locks = {
    "live": threading.Lock(),
    "vod_all": threading.Lock(),
}
streamer_vod_locks: dict[int, threading.Lock] = {}
scheduler_state = {
    "started": False,
    "stop": False,
    "thread": None,
    "next_live": 0.0,
    "next_vod": 0.0,
    "thread_name": "",
    "started_at": None,
    "last_tick_started_at": None,
    "last_tick_finished_at": None,
    "last_stop_requested_at": None,
    "stopped_at": None,
    "last_loop_error": None,
    "tick_count": 0,
}
scheduler_state_lock = threading.Lock()
scheduler_stop_event = threading.Event()
collector_backoff_lock = threading.Lock()
collector_backoff_state: dict[str, dict[str, Any]] = {}


class StreamerCreate(BaseModel):
    soop_user_id: str = Field(min_length=2)
    nickname: str = ""
    channel_url: str = ""
    replay_url: str = ""
    category_no: str = ""
    active: bool = True


class StreamerUpdate(BaseModel):
    nickname: str | None = None
    channel_url: str | None = None
    replay_url: str | None = None
    category_no: str | None = None
    active: bool | None = None


class CollectorError(RuntimeError):
    pass


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS streamers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    soop_user_id TEXT NOT NULL UNIQUE,
    nickname TEXT NOT NULL DEFAULT '',
    channel_url TEXT NOT NULL DEFAULT '',
    replay_url TEXT NOT NULL DEFAULT '',
    category_no TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS streamer_live_state (
    streamer_id INTEGER PRIMARY KEY,
    is_live INTEGER NOT NULL DEFAULT 0,
    broad_no TEXT,
    live_title TEXT,
    viewer_count INTEGER,
    started_at TEXT,
    last_checked_at TEXT NOT NULL,
    last_live_seen_at TEXT,
    raw_json TEXT,
    FOREIGN KEY (streamer_id) REFERENCES streamers(id)
);

CREATE TABLE IF NOT EXISTS live_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    streamer_id INTEGER NOT NULL,
    is_live INTEGER NOT NULL,
    broad_no TEXT,
    live_title TEXT,
    viewer_count INTEGER,
    checked_at TEXT NOT NULL,
    FOREIGN KEY (streamer_id) REFERENCES streamers(id)
);

CREATE TABLE IF NOT EXISTS vods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    streamer_id INTEGER NOT NULL,
    vod_id TEXT,
    title TEXT NOT NULL DEFAULT '',
    vod_url TEXT NOT NULL UNIQUE,
    thumbnail_url TEXT NOT NULL DEFAULT '',
    published_at TEXT,
    duration_seconds INTEGER,
    duration_text TEXT,
    collected_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    raw_json TEXT,
    FOREIGN KEY (streamer_id) REFERENCES streamers(id)
);

CREATE TABLE IF NOT EXISTS collector_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collector_type TEXT NOT NULL,
    streamer_id INTEGER,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    message TEXT
);

CREATE TABLE IF NOT EXISTS collector_backoffs (
    scope_key TEXT PRIMARY KEY,
    collector_type TEXT NOT NULL,
    streamer_id INTEGER,
    reason TEXT NOT NULL,
    failures INTEGER NOT NULL,
    backoff_seconds INTEGER NOT NULL,
    retry_after TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_live_snapshots_streamer_checked
ON live_snapshots(streamer_id, checked_at DESC);

CREATE INDEX IF NOT EXISTS idx_vods_streamer_published
ON vods(streamer_id, published_at DESC, collected_at DESC);

CREATE INDEX IF NOT EXISTS idx_collector_runs_started
ON collector_runs(started_at DESC);

CREATE INDEX IF NOT EXISTS idx_collector_backoffs_retry_after
ON collector_backoffs(retry_after ASC);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def collector_scope_key(collector_type: str, streamer_id: int | None = None) -> str:
    if streamer_id is None:
        return f"{collector_type}:global"
    return f"{collector_type}:streamer:{streamer_id}"


def classify_collector_exception(exc: Exception) -> tuple[str, str, bool]:
    if isinstance(exc, HTTPError):
        if exc.code == 429:
            return ("rate_limited", f"rate_limited: HTTP {exc.code}", True)
        return ("http_error", f"http_error: HTTP {exc.code}", exc.code >= 500)
    if isinstance(exc, URLError):
        reason = exc.reason
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return ("timeout", f"timeout: {reason}", True)
        return ("network_error", f"network_error: {reason}", True)
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return ("timeout", f"timeout: {exc}", True)
    if isinstance(exc, json.JSONDecodeError):
        return ("parse_error", f"parse_error: {exc.msg}", False)
    if isinstance(exc, CollectorError):
        message = str(exc) or "collector_error"
        lowered = message.lower()
        if lowered.startswith("timeout:"):
            return ("timeout", message, True)
        if lowered.startswith("rate_limited:"):
            return ("rate_limited", message, True)
        if lowered.startswith("network_error:"):
            return ("network_error", message, True)
        if lowered.startswith("http_error:"):
            return ("http_error", message, True)
        if lowered.startswith("parse_error:"):
            return ("parse_error", message, False)
        if lowered.startswith("collector_error:"):
            return ("collector_error", message, False)
        return ("collector_error", f"collector_error: {message}", False)
    return ("unexpected_error", f"unexpected_error: {exc}", False)


def compute_backoff_seconds(failures: int) -> int:
    base = max(1, COLLECTOR_BACKOFF_SECONDS)
    max_delay = max(base, COLLECTOR_BACKOFF_MAX_SECONDS)
    delay = base * (2 ** max(0, failures - 1))
    return min(delay, max_delay)


def iso_to_timestamp(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return 0.0


def serialize_backoff_entry(entry: dict[str, Any]) -> dict[str, Any]:
    retry_after_ts = float(entry.get("retry_after", 0))
    return {
        "reason": str(entry.get("reason") or ""),
        "failures": int(entry.get("failures", 0)),
        "backoff_seconds": int(entry.get("backoff_seconds", 0)),
        "retry_after": retry_after_ts,
        "retry_after_iso": datetime.fromtimestamp(retry_after_ts, timezone.utc).astimezone().isoformat(timespec="seconds"),
    }


def upsert_persisted_backoff(scope_key: str, collector_type: str, streamer_id: int | None, entry: dict[str, Any]) -> None:
    stored = serialize_backoff_entry(entry)
    with db_lock, closing(get_conn()) as conn:
        conn.execute(
            """
            INSERT INTO collector_backoffs
            (scope_key, collector_type, streamer_id, reason, failures, backoff_seconds, retry_after, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(scope_key) DO UPDATE SET
                collector_type = excluded.collector_type,
                streamer_id = excluded.streamer_id,
                reason = excluded.reason,
                failures = excluded.failures,
                backoff_seconds = excluded.backoff_seconds,
                retry_after = excluded.retry_after,
                updated_at = excluded.updated_at
            """,
            (
                scope_key,
                collector_type,
                streamer_id,
                stored["reason"],
                stored["failures"],
                stored["backoff_seconds"],
                stored["retry_after_iso"],
                now_iso(),
            ),
        )
        conn.commit()


def delete_persisted_backoff(scope_key: str) -> None:
    with db_lock, closing(get_conn()) as conn:
        conn.execute("DELETE FROM collector_backoffs WHERE scope_key = ?", (scope_key,))
        conn.commit()


def get_persisted_backoff(scope_key: str) -> dict[str, Any] | None:
    with closing(get_conn()) as conn:
        row = conn.execute(
            """
            SELECT scope_key, reason, failures, backoff_seconds, retry_after
            FROM collector_backoffs
            WHERE scope_key = ?
            """,
            (scope_key,),
        ).fetchone()
    if not row:
        return None
    retry_after = iso_to_timestamp(row["retry_after"])
    if retry_after <= time.time():
        delete_persisted_backoff(scope_key)
        return None
    return {
        "reason": row["reason"],
        "failures": int(row["failures"]),
        "backoff_seconds": int(row["backoff_seconds"]),
        "retry_after": retry_after,
    }


def load_persisted_backoffs() -> None:
    now = time.time()
    with closing(get_conn()) as conn:
        rows = conn.execute(
            """
            SELECT scope_key, reason, failures, backoff_seconds, retry_after
            FROM collector_backoffs
            """
        ).fetchall()
    loaded: dict[str, dict[str, Any]] = {}
    expired: list[str] = []
    for row in rows:
        retry_after = iso_to_timestamp(row["retry_after"])
        if retry_after <= now:
            expired.append(row["scope_key"])
            continue
        loaded[row["scope_key"]] = {
            "reason": row["reason"],
            "failures": int(row["failures"]),
            "backoff_seconds": int(row["backoff_seconds"]),
            "retry_after": retry_after,
        }
    if expired:
        with db_lock, closing(get_conn()) as conn:
            conn.executemany("DELETE FROM collector_backoffs WHERE scope_key = ?", [(item,) for item in expired])
            conn.commit()
    with collector_backoff_lock:
        collector_backoff_state.clear()
        collector_backoff_state.update(loaded)


def clear_backoff(collector_type: str, streamer_id: int | None = None) -> None:
    key = collector_scope_key(collector_type, streamer_id)
    with collector_backoff_lock:
        collector_backoff_state.pop(key, None)
    delete_persisted_backoff(key)


def get_active_backoff_message(collector_type: str, streamer_id: int | None = None) -> str | None:
    key = collector_scope_key(collector_type, streamer_id)
    with collector_backoff_lock:
        entry = collector_backoff_state.get(key)
    if not entry:
        entry = get_persisted_backoff(key)
        if not entry:
            return None
        with collector_backoff_lock:
            collector_backoff_state[key] = dict(entry)
    with collector_backoff_lock:
        entry = collector_backoff_state.get(key)
        if not entry:
            return None
        remaining = int(round(entry["retry_after"] - time.time()))
        if remaining <= 0:
            collector_backoff_state.pop(key, None)
            delete_persisted_backoff(key)
            return None
        return (
            f"backoff_active: reason={entry['reason']}, failures={entry['failures']}, "
            f"retry_in={remaining}s"
        )


def record_backoff_failure(collector_type: str, streamer_id: int | None, failure_kind: str) -> dict[str, Any]:
    key = collector_scope_key(collector_type, streamer_id)
    with collector_backoff_lock:
        previous = collector_backoff_state.get(key, {})
    if not previous:
        previous = get_persisted_backoff(key) or {}
        if previous:
            with collector_backoff_lock:
                collector_backoff_state[key] = dict(previous)
    with collector_backoff_lock:
        previous = collector_backoff_state.get(key, previous)
        failures = int(previous.get("failures", 0)) + 1
        backoff_seconds = compute_backoff_seconds(failures)
        entry = {
            "reason": failure_kind,
            "failures": failures,
            "backoff_seconds": backoff_seconds,
            "retry_after": time.time() + backoff_seconds,
        }
        collector_backoff_state[key] = entry
    upsert_persisted_backoff(key, collector_type, streamer_id, entry)
    return dict(entry)


def finalize_failure_message(collector_type: str, streamer_id: int | None, exc: Exception) -> str:
    failure_kind, message, retryable = classify_collector_exception(exc)
    if retryable:
        entry = record_backoff_failure(collector_type, streamer_id, failure_kind)
        return (
            f"{message} | backoff_seconds={entry['backoff_seconds']} "
            f"failures={entry['failures']}"
        )
    clear_backoff(collector_type, streamer_id)
    return message


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column_exists(conn: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    existing = {row["name"] for row in columns}
    if column_name in existing:
        return
    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def init_db() -> None:
    with db_lock, closing(get_conn()) as conn:
        conn.executescript(SCHEMA_SQL)
        # Keep older local DBs compatible with the documented baseline schema.
        ensure_column_exists(conn, "vods", "duration_seconds", "INTEGER")
        conn.commit()
    load_persisted_backoffs()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def clean_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def ensure_streamer_lock(streamer_id: int) -> threading.Lock:
    lock = streamer_vod_locks.get(streamer_id)
    if lock is None:
        lock = threading.Lock()
        streamer_vod_locks[streamer_id] = lock
    return lock


def fetch_text(url: str) -> str:
    req = request.Request(url, headers={"User-Agent": USER_AGENT})
    with request.urlopen(req, timeout=HTTP_TIMEOUT) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def fetch_json(url: str) -> dict[str, Any]:
    payload = fetch_text(url).strip()
    if payload.startswith("callback(") and payload.endswith(");"):
        payload = payload[len("callback("):-2]
    return json.loads(payload)


def normalize_vod_url(url: str) -> str:
    return url.split("?")[0].strip()


def browser_fallback_ready() -> bool:
    return bool(USE_BROWSER_FALLBACK and webdriver and ChromeDriverManager and Options and Service)


def create_browser_driver():
    if not browser_fallback_ready():
        raise CollectorError("browser fallback is unavailable; install selenium and webdriver-manager first")
    options = Options()
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--headless=new")
    options.add_argument("--window-position=-10000,0")
    options.add_argument(f"user-agent={USER_AGENT}")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-blink-features=AutomationControlled")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def load_soop_cookies(driver: Any) -> None:
    if not COOKIE_PATH.exists():
        return
    try:
        import pickle

        driver.get("https://www.sooplive.co.kr")
        with COOKIE_PATH.open("rb") as handle:
            cookies = pickle.load(handle)
        for cookie in cookies:
            if "expiry" in cookie:
                del cookie["expiry"]
            try:
                driver.add_cookie(cookie)
            except Exception:
                pass
        driver.refresh()
        time.sleep(1)
    except Exception:
        return


def begin_collector_run(collector_type: str, streamer_id: int | None = None) -> int:
    started_at = now_iso()
    with db_lock, closing(get_conn()) as conn:
        cur = conn.execute(
            "INSERT INTO collector_runs (collector_type, streamer_id, status, started_at) VALUES (?, ?, ?, ?)",
            (collector_type, streamer_id, "running", started_at),
        )
        conn.commit()
        return int(cur.lastrowid)


def finish_collector_run(run_id: int, status: str, message: str) -> None:
    with db_lock, closing(get_conn()) as conn:
        conn.execute(
            "UPDATE collector_runs SET status = ?, finished_at = ?, message = ? WHERE id = ?",
            (status, now_iso(), message[:1000], run_id),
        )
        conn.commit()


def record_collector_run_event(collector_type: str, status: str, message: str, streamer_id: int | None = None) -> int:
    run_id = begin_collector_run(collector_type, streamer_id)
    finish_collector_run(run_id, status, message)
    return run_id


def parse_scope_key(scope_key: str) -> tuple[str, int | None]:
    collector_type, _, suffix = scope_key.partition(":")
    if suffix == "global":
        return collector_type, None
    if suffix.startswith("streamer:"):
        try:
            return collector_type, int(suffix.split(":", 1)[1])
        except ValueError:
            return collector_type, None
    return collector_type, None


def parse_run_message(message: str | None) -> dict[str, Any]:
    text = (message or "").strip()
    info: dict[str, Any] = {
        "kind": "info",
        "retryable": False,
        "headline": text or "-",
    }
    if not text:
        return info

    if text.startswith("backoff_active:"):
        match = re.search(r"reason=([^,\s]+), failures=(\d+), retry_in=(\d+)s", text)
        info["kind"] = "backoff_active"
        info["retryable"] = True
        if match:
            info["reason"] = match.group(1)
            info["failures"] = int(match.group(2))
            info["retry_in_seconds"] = int(match.group(3))
            info["headline"] = f"backoff {match.group(1)} ({match.group(3)}s left)"
        return info

    retry_match = re.search(r"\|\s*backoff_seconds=(\d+)\s+failures=(\d+)", text)
    prefix_match = re.match(r"([a-z_]+):", text)
    if retry_match:
        info["retryable"] = True
        info["backoff_seconds"] = int(retry_match.group(1))
        info["failures"] = int(retry_match.group(2))
    if prefix_match:
        info["kind"] = prefix_match.group(1)
        info["reason"] = prefix_match.group(1)
        if prefix_match.group(1) in {"timeout", "network_error", "rate_limited", "http_error"}:
            info["retryable"] = True
    if text.startswith("source="):
        info["kind"] = "completed_source"
        source_match = re.search(r"source=([^,]+)", text)
        total_match = re.search(r"total=(\d+)", text)
        if source_match:
            info["source_url"] = source_match.group(1)
        if total_match:
            info["items"] = int(total_match.group(1))
        info["headline"] = f"VOD sync {total_match.group(1) if total_match else '?'} items"
        return info
    if text.startswith("tracked="):
        info["kind"] = "completed_live"
        live_match = re.search(r"live=(\d+)", text)
        pages_match = re.search(r"pages=(\d+)", text)
        if live_match:
            info["live_count"] = int(live_match.group(1))
        if pages_match:
            info["pages"] = int(pages_match.group(1))
        info["headline"] = f"live refresh {live_match.group(1) if live_match else '?'} live"
        return info
    if text.startswith("streamers="):
        info["kind"] = "completed_vod_sweep"
        counts = {
            "streamers": re.search(r"streamers=(\d+)", text),
            "completed": re.search(r"completed=(\d+)", text),
            "failed": re.search(r"failed=(\d+)", text),
            "skipped": re.search(r"skipped=(\d+)", text),
        }
        for key, match in counts.items():
            if match:
                info[key] = int(match.group(1))
        info["headline"] = (
            f"vod sweep {info.get('completed', 0)} ok / "
            f"{info.get('failed', 0)} failed / {info.get('skipped', 0)} skipped"
        )
        return info
    if info["kind"] != "info":
        info["headline"] = text.split("|", 1)[0].strip()
    return info


def list_active_backoffs() -> list[dict[str, Any]]:
    load_persisted_backoffs()
    streamers = {item["id"]: item for item in get_streamers(active_only=False)}
    now = time.time()
    active: list[dict[str, Any]] = []
    with collector_backoff_lock:
        for scope_key, entry in collector_backoff_state.items():
            retry_after = float(entry.get("retry_after", 0))
            remaining = int(round(retry_after - now))
            if remaining <= 0:
                continue
            collector_type, streamer_id = parse_scope_key(scope_key)
            streamer = streamers.get(streamer_id) if streamer_id is not None else None
            active.append(
                {
                    "scope_key": scope_key,
                    "collector_type": collector_type,
                    "streamer_id": streamer_id,
                    "streamer_name": (streamer or {}).get("nickname") or (streamer or {}).get("soop_user_id") or "global",
                    "soop_user_id": (streamer or {}).get("soop_user_id"),
                    "reason": entry.get("reason"),
                    "failures": int(entry.get("failures", 0)),
                    "backoff_seconds": int(entry.get("backoff_seconds", 0)),
                    "retry_in_seconds": remaining,
                    "retry_after": datetime.fromtimestamp(retry_after, timezone.utc).astimezone().isoformat(timespec="seconds"),
                }
            )
    active.sort(key=lambda item: (item["collector_type"], item["streamer_id"] or 0))
    return active


def get_recent_collector_runs(limit: int = 20) -> list[dict[str, Any]]:
    streamers = {item["id"]: item for item in get_streamers(active_only=False)}
    with closing(get_conn()) as conn:
        rows = conn.execute(
            "SELECT * FROM collector_runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    result = []
    for row in rows:
        item = row_to_dict(row) or {}
        streamer = streamers.get(item.get("streamer_id"))
        item["streamer_name"] = (streamer or {}).get("nickname") or (streamer or {}).get("soop_user_id") or "global"
        item["soop_user_id"] = (streamer or {}).get("soop_user_id")
        item["message_info"] = parse_run_message(item.get("message"))
        result.append(item)
    return result


def get_collector_visibility_snapshot(run_limit: int = 20) -> dict[str, Any]:
    streamers = get_streamers_with_state()
    recent_runs = get_recent_collector_runs(run_limit)
    active_backoffs = list_active_backoffs()
    failed_runs = [item for item in recent_runs if item.get("status") == "failed"]
    skipped_runs = [item for item in recent_runs if item.get("status") == "skipped"]
    completed_runs = [item for item in recent_runs if item.get("status") == "completed"]
    recent_state = []
    for streamer in streamers:
        live_state = streamer.get("live_state") or {}
        latest_vod = streamer.get("latest_vod") or {}
        recent_state.append(
            {
                "streamer_id": streamer["id"],
                "soop_user_id": streamer["soop_user_id"],
                "streamer_name": streamer.get("nickname") or streamer["soop_user_id"],
                "active": bool(streamer.get("active")),
                "is_live": bool(live_state.get("is_live")),
                "live_title": live_state.get("live_title"),
                "last_live_checked_at": live_state.get("last_checked_at"),
                "latest_vod_title": latest_vod.get("title"),
                "latest_vod_at": latest_vod.get("published_at") or latest_vod.get("collected_at"),
            }
        )
    recent_state.sort(key=lambda item: (not item["active"], item["streamer_name"].lower()))
    return {
        "summary": {
            "recent_run_count": len(recent_runs),
            "failed_count": len(failed_runs),
            "skipped_count": len(skipped_runs),
            "completed_count": len(completed_runs),
            "active_backoff_count": len(active_backoffs),
            "last_failed_at": failed_runs[0]["finished_at"] if failed_runs else None,
            "last_completed_at": completed_runs[0]["finished_at"] if completed_runs else None,
        },
        "active_backoffs": active_backoffs,
        "recent_runs": recent_runs,
        "recent_state": recent_state,
    }


def scheduler_thread_alive() -> bool:
    thread = scheduler_state.get("thread")
    return bool(thread and thread.is_alive())


def get_scheduler_state_snapshot() -> dict[str, Any]:
    with scheduler_state_lock:
        return {
            "started": bool(scheduler_state["started"]),
            "stop": bool(scheduler_state["stop"]),
            "thread_alive": scheduler_thread_alive(),
            "thread_name": scheduler_state.get("thread_name") or None,
            "next_live": float(scheduler_state["next_live"]),
            "next_vod": float(scheduler_state["next_vod"]),
            "started_at": scheduler_state.get("started_at"),
            "last_tick_started_at": scheduler_state.get("last_tick_started_at"),
            "last_tick_finished_at": scheduler_state.get("last_tick_finished_at"),
            "last_stop_requested_at": scheduler_state.get("last_stop_requested_at"),
            "stopped_at": scheduler_state.get("stopped_at"),
            "last_loop_error": scheduler_state.get("last_loop_error"),
            "tick_count": int(scheduler_state.get("tick_count", 0)),
            "tick_seconds": SCHEDULER_TICK_SECONDS,
        }


def start_scheduler_thread() -> bool:
    with scheduler_state_lock:
        existing = scheduler_state.get("thread")
        if existing and existing.is_alive():
            scheduler_state["started"] = True
            scheduler_state["stop"] = False
            return False

        scheduler_stop_event.clear()
        scheduler_state["started"] = True
        scheduler_state["stop"] = False
        scheduler_state["next_live"] = time.time() + SCHEDULER_STARTUP_LIVE_DELAY_SECONDS
        scheduler_state["next_vod"] = time.time() + SCHEDULER_STARTUP_VOD_DELAY_SECONDS
        scheduler_state["started_at"] = now_iso()
        scheduler_state["last_tick_started_at"] = None
        scheduler_state["last_tick_finished_at"] = None
        scheduler_state["last_stop_requested_at"] = None
        scheduler_state["stopped_at"] = None
        scheduler_state["last_loop_error"] = None
        scheduler_state["tick_count"] = 0
        thread = threading.Thread(target=scheduler_loop, daemon=True, name="soop-live-vod-scheduler")
        scheduler_state["thread"] = thread
        scheduler_state["thread_name"] = thread.name
        thread.start()
        return True


def stop_scheduler_thread(join_timeout: float | None = None) -> bool:
    with scheduler_state_lock:
        thread = scheduler_state.get("thread")
        if not thread:
            scheduler_state["started"] = False
            scheduler_state["stop"] = True
            scheduler_state["thread_name"] = ""
            scheduler_state["stopped_at"] = now_iso()
            return True
        scheduler_state["stop"] = True
        scheduler_state["last_stop_requested_at"] = now_iso()
        scheduler_stop_event.set()

    timeout = SCHEDULER_STOP_JOIN_SECONDS if join_timeout is None else join_timeout
    thread.join(timeout=max(0.1, timeout))
    stopped_cleanly = not thread.is_alive()

    with scheduler_state_lock:
        scheduler_state["started"] = not stopped_cleanly
        if stopped_cleanly:
            scheduler_state["thread"] = None
            scheduler_state["thread_name"] = ""
            scheduler_state["stopped_at"] = now_iso()
        else:
            scheduler_state["thread"] = thread
            scheduler_state["thread_name"] = thread.name
    return stopped_cleanly


def get_streamers(active_only: bool = False) -> list[dict[str, Any]]:
    query = "SELECT * FROM streamers"
    params: list[Any] = []
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY active DESC, updated_at DESC, id DESC"
    with closing(get_conn()) as conn:
        rows = conn.execute(query, params).fetchall()
        return [row_to_dict(row) for row in rows]


def get_streamer(streamer_id: int) -> dict[str, Any] | None:
    with closing(get_conn()) as conn:
        return row_to_dict(conn.execute("SELECT * FROM streamers WHERE id = ?", (streamer_id,)).fetchone())


def get_streamer_live_state(streamer_id: int) -> dict[str, Any] | None:
    with closing(get_conn()) as conn:
        return row_to_dict(
            conn.execute("SELECT * FROM streamer_live_state WHERE streamer_id = ?", (streamer_id,)).fetchone()
        )


def get_latest_vod(streamer_id: int) -> dict[str, Any] | None:
    with closing(get_conn()) as conn:
        row = conn.execute(
            """
            SELECT * FROM vods
            WHERE streamer_id = ?
            ORDER BY COALESCE(published_at, collected_at) DESC, id DESC
            LIMIT 1
            """,
            (streamer_id,),
        ).fetchone()
        return row_to_dict(row)


def get_streamers_with_state() -> list[dict[str, Any]]:
    result = []
    for streamer in get_streamers(active_only=False):
        streamer["live_state"] = get_streamer_live_state(streamer["id"])
        streamer["latest_vod"] = get_latest_vod(streamer["id"])
        result.append(streamer)
    return result


def create_streamer(payload: StreamerCreate) -> dict[str, Any]:
    now = now_iso()
    soop_user_id = payload.soop_user_id.strip()
    if not soop_user_id:
        raise HTTPException(status_code=400, detail="soop_user_id is required")
    channel_url = payload.channel_url.strip() or f"https://www.sooplive.co.kr/station/{soop_user_id}"
    replay_url = payload.replay_url.strip()
    with db_lock, closing(get_conn()) as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO streamers (soop_user_id, nickname, channel_url, replay_url, category_no, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    soop_user_id,
                    payload.nickname.strip(),
                    channel_url,
                    replay_url,
                    payload.category_no.strip(),
                    1 if payload.active else 0,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="streamer already exists") from exc
        conn.execute(
            """
            INSERT OR REPLACE INTO streamer_live_state
            (streamer_id, is_live, broad_no, live_title, viewer_count, started_at, last_checked_at, last_live_seen_at, raw_json)
            VALUES (?, 0, NULL, NULL, NULL, NULL, ?, NULL, NULL)
            """,
            (cur.lastrowid, now),
        )
        conn.commit()
        return get_streamer(int(cur.lastrowid)) or {}


def update_streamer(streamer_id: int, payload: StreamerUpdate) -> dict[str, Any]:
    existing = get_streamer(streamer_id)
    if not existing:
        raise HTTPException(status_code=404, detail="streamer not found")
    updated = dict(existing)
    for field in ("nickname", "channel_url", "replay_url", "category_no", "active"):
        value = getattr(payload, field)
        if value is not None:
            updated[field] = value.strip() if isinstance(value, str) else (1 if value else 0)
    updated["updated_at"] = now_iso()
    with db_lock, closing(get_conn()) as conn:
        conn.execute(
            """
            UPDATE streamers
            SET nickname = ?, channel_url = ?, replay_url = ?, category_no = ?, active = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                updated["nickname"],
                updated["channel_url"],
                updated["replay_url"],
                updated["category_no"],
                updated["active"],
                updated["updated_at"],
                streamer_id,
            ),
        )
        conn.commit()
    return get_streamer(streamer_id) or {}


def deactivate_streamer(streamer_id: int) -> None:
    existing = get_streamer(streamer_id)
    if not existing:
        raise HTTPException(status_code=404, detail="streamer not found")
    with db_lock, closing(get_conn()) as conn:
        conn.execute("UPDATE streamers SET active = 0, updated_at = ? WHERE id = ?", (now_iso(), streamer_id))
        conn.commit()


def save_live_state(streamer: dict[str, Any], live_payload: dict[str, Any] | None) -> None:
    checked_at = now_iso()
    is_live = 1 if live_payload else 0
    broad_no = live_payload.get("broad_no") if live_payload else None
    live_title = live_payload.get("broad_title") if live_payload else None
    viewer_count = int(live_payload.get("total_view_cnt") or 0) if live_payload else None
    started_at = live_payload.get("broad_start") if live_payload else None
    raw_json = json.dumps(live_payload, ensure_ascii=False) if live_payload else None
    last_live_seen_at = checked_at if live_payload else None

    with db_lock, closing(get_conn()) as conn:
        previous = conn.execute(
            "SELECT last_live_seen_at FROM streamer_live_state WHERE streamer_id = ?",
            (streamer["id"],),
        ).fetchone()
        if not last_live_seen_at and previous and previous["last_live_seen_at"]:
            last_live_seen_at = previous["last_live_seen_at"]
        conn.execute(
            """
            INSERT OR REPLACE INTO streamer_live_state
            (streamer_id, is_live, broad_no, live_title, viewer_count, started_at, last_checked_at, last_live_seen_at, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                streamer["id"],
                is_live,
                broad_no,
                live_title,
                viewer_count,
                started_at,
                checked_at,
                last_live_seen_at,
                raw_json,
            ),
        )
        conn.execute(
            """
            INSERT INTO live_snapshots (streamer_id, is_live, broad_no, live_title, viewer_count, checked_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (streamer["id"], is_live, broad_no, live_title, viewer_count, checked_at),
        )
        conn.commit()


def enrich_streamer_nickname_from_html(streamer_id: int, html: str) -> None:
    title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if not title_match:
        return
    title = clean_text(title_match.group(1))
    if not title:
        return
    nickname = title.replace("| SOOP", "").strip()
    nickname = re.sub(r"\s*방송국.*$", "", nickname).strip()
    nickname = re.sub(r"\s*Station.*$", "", nickname).strip()
    if not nickname:
        return
    with db_lock, closing(get_conn()) as conn:
        row = conn.execute("SELECT nickname FROM streamers WHERE id = ?", (streamer_id,)).fetchone()
        if row and not row["nickname"]:
            conn.execute("UPDATE streamers SET nickname = ?, updated_at = ? WHERE id = ?", (nickname, now_iso(), streamer_id))
            conn.commit()


def parse_vod_items(html: str) -> list[dict[str, Any]]:
    url_pattern = re.compile(r'href="(https://vod\.sooplive\.co\.kr/player/(\d+)(?:/catch)?)"', re.IGNORECASE)
    found: dict[str, dict[str, Any]] = {}
    for match in url_pattern.finditer(html):
        vod_url = normalize_vod_url(match.group(1))
        vod_id = match.group(2)
        if vod_url in found:
            continue
        anchor_end = html.find("</a>", match.end())
        if anchor_end != -1:
            chunk = html[match.start(): anchor_end + 4]
        else:
            end = min(len(html), match.end() + 4500)
            chunk = html[match.start(): end]
        title_match = re.search(r'<p[^>]*Title-module__title[^>]*>(.*?)</p>', chunk, re.IGNORECASE | re.DOTALL)
        if not title_match:
            title_match = re.search(r'<p[^>]*>(.*?)</p>', chunk, re.IGNORECASE | re.DOTALL)
        thumb_match = re.search(r'<img[^>]+src="([^"]+)"', chunk, re.IGNORECASE)
        duration_match = re.search(r'Badge-module__vodTime[^>]*>\s*<div[^>]*>([^<]+)</div>', chunk, re.IGNORECASE | re.DOTALL)
        meta_matches = re.findall(r'ThumbnailMoreInfo-module__md[^>]*>([^<]+)</div>', chunk, re.IGNORECASE)
        relative_time = meta_matches[1] if len(meta_matches) > 1 else None
        found[vod_url] = {
            "vod_id": vod_id,
            "vod_url": vod_url,
            "title": clean_text(title_match.group(1)) if title_match else "",
            "thumbnail_url": thumb_match.group(1).strip() if thumb_match else "",
            "published_at": relative_time,
            "duration_text": clean_text(duration_match.group(1)) if duration_match else "",
        }
    return list(found.values())


def candidate_station_urls(streamer: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for candidate in (
        streamer.get("replay_url") or "",
        streamer.get("channel_url") or "",
        f"https://www.sooplive.co.kr/station/{streamer['soop_user_id']}",
        f"https://ch.sooplive.co.kr/{streamer['soop_user_id']}",
        f"https://ch.sooplive.co.kr/{streamer['soop_user_id']}/vods/review",
    ):
        candidate = candidate.strip()
        if candidate and candidate not in urls:
            urls.append(candidate)
    return urls


def collect_vods_for_streamer(streamer: dict[str, Any]) -> dict[str, Any]:
    lock = ensure_streamer_lock(streamer["id"])
    if not lock.acquire(blocking=False):
        record_collector_run_event("vod", "skipped", "collector already running", streamer["id"])
        return {"status": "skipped", "message": "collector already running"}

    backoff_message = get_active_backoff_message("vod", streamer["id"])
    if backoff_message:
        record_collector_run_event("vod", "skipped", backoff_message, streamer["id"])
        lock.release()
        return {"status": "skipped", "message": backoff_message}

    run_id = begin_collector_run("vod", streamer["id"])
    try:
        html = ""
        source_url = ""
        last_error = ""
        for url in candidate_station_urls(streamer):
            try:
                html = fetch_text(url)
                source_url = url
                if "vod.sooplive.co.kr/player/" in html:
                    break
            except (HTTPError, URLError, TimeoutError, ValueError, socket.timeout) as exc:
                last_error = classify_collector_exception(exc)[1]
                continue
        if not html:
            raise CollectorError(last_error or "could not load any SOOP channel page")

        enrich_streamer_nickname_from_html(streamer["id"], html)
        items = parse_vod_items(html)
        if not items and browser_fallback_ready():
            driver = None
            try:
                driver = create_browser_driver()
                load_soop_cookies(driver)
                driver.get(source_url)
                time.sleep(3)
                html = driver.page_source
                items = parse_vod_items(html)
            finally:
                if driver is not None:
                    try:
                        driver.quit()
                    except Exception:
                        pass

        if not items:
            raise CollectorError(f"no VOD items found from {source_url}")

        inserted = 0
        updated = 0
        now = now_iso()
        with db_lock, closing(get_conn()) as conn:
            for item in items:
                existing = conn.execute("SELECT id FROM vods WHERE vod_url = ?", (item["vod_url"],)).fetchone()
                payload_json = json.dumps({"source_url": source_url, **item}, ensure_ascii=False)
                if existing:
                    conn.execute(
                        """
                        UPDATE vods
                        SET title = ?, thumbnail_url = ?, published_at = ?, duration_text = ?, last_seen_at = ?, raw_json = ?
                        WHERE id = ?
                        """,
                        (
                            item["title"],
                            item["thumbnail_url"],
                            item["published_at"],
                            item["duration_text"],
                            now,
                            payload_json,
                            existing["id"],
                        ),
                    )
                    updated += 1
                else:
                    conn.execute(
                        """
                        INSERT INTO vods
                        (streamer_id, vod_id, title, vod_url, thumbnail_url, published_at, duration_text, collected_at, last_seen_at, raw_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            streamer["id"],
                            item["vod_id"],
                            item["title"],
                            item["vod_url"],
                            item["thumbnail_url"],
                            item["published_at"],
                            item["duration_text"],
                            now,
                            now,
                            payload_json,
                        ),
                    )
                    inserted += 1
            conn.commit()
        clear_backoff("vod", streamer["id"])
        message = f"source={source_url}, inserted={inserted}, updated={updated}, total={len(items)}"
        finish_collector_run(run_id, "completed", message)
        return {"status": "completed", "message": message, "source_url": source_url, "items": len(items)}
    except Exception as exc:
        failure_message = finalize_failure_message("vod", streamer["id"], exc)
        finish_collector_run(run_id, "failed", failure_message)
        raise CollectorError(failure_message) from exc
    finally:
        if lock.locked():
            lock.release()


def collect_vods_for_all() -> dict[str, Any]:
    if not run_locks["vod_all"].acquire(blocking=False):
        record_collector_run_event("vod", "skipped", "global VOD collector already running")
        return {"status": "skipped", "message": "global VOD collector already running"}
    backoff_message = get_active_backoff_message("vod", None)
    if backoff_message:
        record_collector_run_event("vod", "skipped", backoff_message)
        run_locks["vod_all"].release()
        return {"status": "skipped", "message": backoff_message}
    run_id = begin_collector_run("vod", None)
    try:
        streamers = get_streamers(active_only=True)
        if not streamers:
            clear_backoff("vod", None)
            finish_collector_run(run_id, "completed", "no active streamers")
            return {"status": "completed", "message": "no active streamers", "results": []}
        results = []
        for streamer in streamers:
            try:
                results.append({"streamer_id": streamer["id"], **collect_vods_for_streamer(streamer)})
            except Exception as exc:
                results.append({"streamer_id": streamer["id"], "status": "failed", "message": str(exc)})
        completed = sum(1 for item in results if item.get("status") == "completed")
        failed = sum(1 for item in results if item.get("status") == "failed")
        skipped = sum(1 for item in results if item.get("status") == "skipped")
        message = (
            f"streamers={len(streamers)}, completed={completed}, "
            f"failed={failed}, skipped={skipped}"
        )
        clear_backoff("vod", None)
        finish_collector_run(run_id, "completed", message)
        return {"status": "completed", "message": message, "results": results}
    except Exception as exc:
        failure_message = finalize_failure_message("vod", None, exc)
        finish_collector_run(run_id, "failed", failure_message)
        raise CollectorError(failure_message) from exc
    finally:
        if run_locks["vod_all"].locked():
            run_locks["vod_all"].release()


def collect_live_status_via_api(streamers: list[dict[str, Any]]) -> dict[str, Any]:
    tracked = {streamer["soop_user_id"]: streamer for streamer in streamers}
    matches: dict[str, dict[str, Any]] = {}
    scanned_pages = 0

    for page_no in range(1, LIVE_PAGE_LIMIT + 1):
        query = parse.urlencode(
            {
                "client_id": SOOP_CLIENT_ID,
                "order_type": "broad_start",
                "page_no": page_no,
                "callback": "callback",
            }
        )
        data = fetch_json(f"https://openapi.sooplive.co.kr/broad/list?{query}")
        broad_list = data.get("broad") or []
        if not isinstance(broad_list, list) or not broad_list:
            break
        scanned_pages = page_no
        for item in broad_list:
            user_id = str(item.get("user_id") or "").strip()
            if user_id in tracked:
                matches[user_id] = item
        if len(matches) == len(tracked):
            break

    for streamer in streamers:
        save_live_state(streamer, matches.get(streamer["soop_user_id"]))

    live_count = sum(1 for item in matches.values() if item)
    return {
        "mode": "api",
        "message": f"tracked={len(streamers)}, live={live_count}, pages={scanned_pages or 1}",
        "live_count": live_count,
    }


def detect_live_from_station_html(streamer: dict[str, Any]) -> dict[str, Any] | None:
    candidates = [
        streamer.get("channel_url") or "",
        f"https://www.sooplive.co.kr/station/{streamer['soop_user_id']}",
        f"https://m.sooplive.co.kr/station/{streamer['soop_user_id']}",
        f"https://ch.sooplive.co.kr/{streamer['soop_user_id']}",
    ]
    html = ""
    source_url = ""
    for url in candidates:
        if not url:
            continue
        try:
            html = fetch_text(url)
            source_url = url
            if html:
                break
        except Exception:
            continue
    if not html:
        return None

    lower_html = html.lower()
    is_live = any(
        signal in lower_html
        for signal in (
            'badge-module__live',
            'livebadge',
            'on-air',
            'onair',
            'status on',
            'player_area',
        )
    )
    broad_match = re.search(r'/([A-Za-z0-9_]+)/(?P<broad_no>\d{4,})', html)
    title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    title = clean_text(title_match.group(1)) if title_match else ''
    title = title.replace('| SOOP', '').strip()
    payload = {
        "user_id": streamer["soop_user_id"],
        "broad_no": broad_match.group('broad_no') if broad_match else None,
        "broad_title": title,
        "broad_start": None,
        "total_view_cnt": None,
        "source_url": source_url,
        "detected_by": "html-fallback",
    }
    return payload if is_live else None


def detect_live_from_station_browser(streamer: dict[str, Any]) -> dict[str, Any] | None:
    if not browser_fallback_ready():
        return None
    driver = None
    try:
        driver = create_browser_driver()
        load_soop_cookies(driver)
        driver.get(f"https://www.sooplive.co.kr/station/{streamer['soop_user_id']}")
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
            )
        except Exception:
            pass
        page_source = driver.page_source
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[class*='Badge-module__live']"))
            )
            is_live = True
        except Exception:
            lower_html = page_source.lower()
            is_live = any(signal in lower_html for signal in ('badge-module__live', 'on-air', 'onair', 'status on'))
        if not is_live:
            return None
        title_match = re.search(r'<title>(.*?)</title>', page_source, re.IGNORECASE | re.DOTALL)
        title = clean_text(title_match.group(1)) if title_match else ''
        title = title.replace('| SOOP', '').strip()
        return {
            "user_id": streamer["soop_user_id"],
            "broad_no": None,
            "broad_title": title,
            "broad_start": None,
            "total_view_cnt": None,
            "source_url": f"https://www.sooplive.co.kr/station/{streamer['soop_user_id']}",
            "detected_by": "browser-fallback",
        }
    except Exception:
        return None
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def collect_live_status_via_html(streamers: list[dict[str, Any]]) -> dict[str, Any]:
    live_count = 0
    detection_mode = "station_html"
    for streamer in streamers:
        payload = detect_live_from_station_html(streamer)
        if payload is None and browser_fallback_ready():
            payload = detect_live_from_station_browser(streamer)
            if payload:
                detection_mode = "browser-fallback"
        if payload:
            live_count += 1
        save_live_state(streamer, payload)
    return {
        "mode": "html-fallback",
        "message": f"tracked={len(streamers)}, live={live_count}, checked_via={detection_mode}",
        "live_count": live_count,
    }


def refresh_live_status() -> dict[str, Any]:
    if not run_locks["live"].acquire(blocking=False):
        record_collector_run_event("live", "skipped", "live collector already running")
        return {"status": "skipped", "message": "live collector already running"}

    backoff_message = get_active_backoff_message("live", None)
    if backoff_message:
        record_collector_run_event("live", "skipped", backoff_message)
        run_locks["live"].release()
        return {"status": "skipped", "message": backoff_message}

    run_id = begin_collector_run("live", None)
    try:
        streamers = get_streamers(active_only=True)
        if not streamers:
            clear_backoff("live", None)
            finish_collector_run(run_id, "completed", "no active streamers")
            return {"status": "completed", "message": "no active streamers"}

        if SOOP_CLIENT_ID:
            result = collect_live_status_via_api(streamers)
        else:
            result = collect_live_status_via_html(streamers)

        clear_backoff("live", None)
        finish_collector_run(run_id, "completed", result["message"])
        return {"status": "completed", **result}
    except Exception as exc:
        failure_message = finalize_failure_message("live", None, exc)
        finish_collector_run(run_id, "failed", failure_message)
        raise CollectorError(failure_message) from exc
    finally:
        if run_locks["live"].locked():
            run_locks["live"].release()


def run_scheduler_tick() -> dict[str, Any]:
    results: dict[str, Any] = {}

    if time.time() >= scheduler_state["next_live"]:
        try:
            results["live"] = refresh_live_status()
        except Exception as exc:
            results["live"] = {"status": "failed", "message": str(exc)}
        scheduler_state["next_live"] = time.time() + LIVE_REFRESH_SECONDS

    if time.time() >= scheduler_state["next_vod"]:
        try:
            results["vod"] = collect_vods_for_all()
        except Exception as exc:
            results["vod"] = {"status": "failed", "message": str(exc)}
        scheduler_state["next_vod"] = time.time() + VOD_REFRESH_SECONDS

    results["next_live"] = scheduler_state["next_live"]
    results["next_vod"] = scheduler_state["next_vod"]
    return results


def scheduler_loop() -> None:
    try:
        while not scheduler_stop_event.is_set():
            with scheduler_state_lock:
                scheduler_state["last_tick_started_at"] = now_iso()
                scheduler_state["last_loop_error"] = None
            try:
                run_scheduler_tick()
            except Exception as exc:
                with scheduler_state_lock:
                    scheduler_state["last_loop_error"] = str(exc)
            finally:
                with scheduler_state_lock:
                    scheduler_state["tick_count"] = int(scheduler_state.get("tick_count", 0)) + 1
                    scheduler_state["last_tick_finished_at"] = now_iso()
            scheduler_stop_event.wait(max(0.05, SCHEDULER_TICK_SECONDS))
    finally:
        with scheduler_state_lock:
            scheduler_state["stop"] = True
            if scheduler_state.get("thread") is threading.current_thread():
                scheduler_state["thread"] = None
                scheduler_state["thread_name"] = ""
                scheduler_state["started"] = False
                scheduler_state["stopped_at"] = now_iso()


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    start_scheduler_thread()


@app.on_event("shutdown")
def on_shutdown() -> None:
    stop_scheduler_thread()


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    if not UI_PATH.exists():
        return HTMLResponse("<h1>Missing UI file</h1>", status_code=500)
    return HTMLResponse(UI_PATH.read_text(encoding="utf-8"))


@app.get("/api/health")
def api_health() -> dict[str, Any]:
    with closing(get_conn()) as conn:
        conn.execute("SELECT 1").fetchone()
    scheduler_snapshot = get_scheduler_state_snapshot()
    return {
        "status": "ok",
        "db_path": str(DB_PATH),
        "scheduler_started": scheduler_snapshot["started"],
        "scheduler_thread_alive": scheduler_snapshot["thread_alive"],
        "scheduler_stop_requested": scheduler_snapshot["stop"],
        "scheduler_thread_name": scheduler_snapshot["thread_name"],
        "scheduler_tick_count": scheduler_snapshot["tick_count"],
        "scheduler_tick_seconds": scheduler_snapshot["tick_seconds"],
        "scheduler_last_tick_started_at": scheduler_snapshot["last_tick_started_at"],
        "scheduler_last_tick_finished_at": scheduler_snapshot["last_tick_finished_at"],
        "scheduler_last_stop_requested_at": scheduler_snapshot["last_stop_requested_at"],
        "scheduler_stopped_at": scheduler_snapshot["stopped_at"],
        "scheduler_last_loop_error": scheduler_snapshot["last_loop_error"],
        "scheduler_next_live": scheduler_snapshot["next_live"],
        "scheduler_next_vod": scheduler_snapshot["next_vod"],
        "soop_client_id_configured": bool(SOOP_CLIENT_ID),
        "live_mode": "api" if SOOP_CLIENT_ID else "html-fallback",
        "browser_fallback_ready": browser_fallback_ready(),
        "live_refresh_seconds": LIVE_REFRESH_SECONDS,
        "vod_refresh_seconds": VOD_REFRESH_SECONDS,
    }


@app.get("/api/config")
def api_config() -> dict[str, Any]:
    return {
        "soop_client_id_configured": bool(SOOP_CLIENT_ID),
        "live_mode": "api" if SOOP_CLIENT_ID else "html-fallback",
        "browser_fallback_ready": browser_fallback_ready(),
        "live_page_limit": LIVE_PAGE_LIMIT,
        "db_path": str(DB_PATH),
    }


@app.get("/api/streamers")
def api_streamers() -> dict[str, Any]:
    items = get_streamers_with_state()
    return {"items": items, "count": len(items)}


@app.post("/api/streamers")
def api_create_streamer(payload: StreamerCreate) -> dict[str, Any]:
    streamer = create_streamer(payload)
    return {"item": streamer}


@app.patch("/api/streamers/{streamer_id}")
def api_update_streamer(streamer_id: int, payload: StreamerUpdate) -> dict[str, Any]:
    return {"item": update_streamer(streamer_id, payload)}


@app.delete("/api/streamers/{streamer_id}")
def api_delete_streamer(streamer_id: int) -> dict[str, Any]:
    deactivate_streamer(streamer_id)
    return {"ok": True}


@app.get("/api/live")
def api_live() -> dict[str, Any]:
    items = [item for item in get_streamers_with_state() if (item.get("live_state") or {}).get("is_live")]
    return {"items": items, "count": len(items)}


@app.post("/api/live/refresh")
def api_live_refresh() -> JSONResponse:
    try:
        result = refresh_live_status()
        return JSONResponse(result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/streamers/{streamer_id}/vods")
def api_streamer_vods(streamer_id: int) -> dict[str, Any]:
    streamer = get_streamer(streamer_id)
    if not streamer:
        raise HTTPException(status_code=404, detail="streamer not found")
    with closing(get_conn()) as conn:
        rows = conn.execute(
            """
            SELECT * FROM vods
            WHERE streamer_id = ?
            ORDER BY COALESCE(published_at, collected_at) DESC, id DESC
            LIMIT 100
            """,
            (streamer_id,),
        ).fetchall()
    return {"items": [row_to_dict(row) for row in rows], "count": len(rows)}


@app.post("/api/streamers/{streamer_id}/vods/refresh")
def api_refresh_streamer_vods(streamer_id: int) -> JSONResponse:
    streamer = get_streamer(streamer_id)
    if not streamer:
        raise HTTPException(status_code=404, detail="streamer not found")
    try:
        result = collect_vods_for_streamer(streamer)
        return JSONResponse(result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/vods/refresh")
def api_vods_refresh() -> JSONResponse:
    try:
        return JSONResponse(collect_vods_for_all())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/jobs")
def api_jobs() -> dict[str, Any]:
    items = get_recent_collector_runs(100)
    return {"items": items, "count": len(items)}


@app.get("/api/admin/collector-visibility")
def api_collector_visibility() -> dict[str, Any]:
    return get_collector_visibility_snapshot(20)


if __name__ == "__main__":
    uvicorn.run("app_live_vod:app", host="127.0.0.1", port=8877, reload=False)










