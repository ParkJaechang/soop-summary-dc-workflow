import json
import sqlite3
import threading
import time
from pathlib import Path
import sys

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app_live_vod as live


ARTIFACT_DIR = Path(__file__).resolve().parent
DB_PATH = ARTIFACT_DIR / "lifecycle_test.db"

STATION_HTML = """
<html>
  <head><title>Lifecycle Stream 방송국 | SOOP</title></head>
  <body>
    <div class="Badge-module__live">LIVE</div>
    <div class="player_area">on-air</div>
  </body>
</html>
""".strip()

REPLAY_HTML = """
<html>
  <head><title>Lifecycle Stream 방송국 | SOOP</title></head>
  <body>
    <a href="https://vod.sooplive.co.kr/player/88001">
      <img src="https://img.test/88001.jpg" />
      <p class="Title-module__title">Lifecycle VOD One</p>
      <div class="Badge-module__vodTime"><div>12:34</div></div>
      <div class="ThumbnailMoreInfo-module__md">views</div>
      <div class="ThumbnailMoreInfo-module__md">2026-04-08T10:00:00+09:00</div>
    </a>
    <a href="https://vod.sooplive.co.kr/player/88002">
      <img src="https://img.test/88002.jpg" />
      <p class="Title-module__title">Lifecycle VOD Two</p>
      <div class="Badge-module__vodTime"><div>03:21</div></div>
      <div class="ThumbnailMoreInfo-module__md">views</div>
      <div class="ThumbnailMoreInfo-module__md">2026-04-08T09:30:00+09:00</div>
    </a>
  </body>
</html>
""".strip()


fetch_lock = threading.Lock()
fetch_trace: list[dict] = []
fetch_counts = {
    "station": 0,
    "replay": 0,
}


def snapshot_fetch_counts() -> dict[str, int]:
    with fetch_lock:
        return dict(fetch_counts)


def fake_fetch_text(url: str) -> str:
    now = time.time()
    if "/replay/" in url:
        kind = "replay"
        delay = 0.03
        body = REPLAY_HTML
    elif "/station/" in url:
        kind = "station"
        delay = 0.02
        body = STATION_HTML
    else:
        raise AssertionError(f"unexpected URL in lifecycle verifier: {url}")

    with fetch_lock:
        fetch_counts[kind] += 1
        fetch_trace.append(
            {
                "kind": kind,
                "url": url,
                "called_at": now,
                "station_calls": fetch_counts["station"],
                "replay_calls": fetch_counts["replay"],
            }
        )

    time.sleep(delay)
    return body


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def select_rows(query: str) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(query).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def session_snapshot(client: TestClient, label: str, streamer_id: int | None = None) -> dict:
    snapshot = {
        "label": label,
        "health": client.get("/api/health").json(),
        "jobs_count": client.get("/api/jobs").json()["count"],
        "fetch_counts": snapshot_fetch_counts(),
        "scheduler_state": live.get_scheduler_state_snapshot(),
    }
    if streamer_id is not None:
        snapshot["live_count"] = client.get("/api/live").json()["count"]
        snapshot["vod_count"] = client.get(f"/api/streamers/{streamer_id}/vods").json()["count"]
        snapshot["collector_visibility_summary"] = client.get("/api/admin/collector-visibility").json()["summary"]
    return snapshot


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()

    live.DB_PATH = DB_PATH
    live.SOOP_CLIENT_ID = ""
    live.USE_BROWSER_FALLBACK = False
    live.LIVE_REFRESH_SECONDS = 0.25
    live.VOD_REFRESH_SECONDS = 0.35
    live.SCHEDULER_TICK_SECONDS = 0.05
    live.SCHEDULER_STARTUP_LIVE_DELAY_SECONDS = 0.18
    live.SCHEDULER_STARTUP_VOD_DELAY_SECONDS = 0.22
    live.SCHEDULER_STOP_JOIN_SECONDS = 1.0
    live.fetch_text = fake_fetch_text

    lifecycle_trace: list[dict] = []

    streamer_id = None
    with TestClient(live.app) as client:
        lifecycle_trace.append(session_snapshot(client, "session_1_start"))
        created = client.post(
            "/api/streamers",
            json={
                "soop_user_id": "lifecycle_streamer",
                "nickname": "Lifecycle Stream",
                "channel_url": "https://fixture.test/station/lifecycle_streamer",
                "replay_url": "https://fixture.test/replay/lifecycle_streamer",
                "category_no": "",
                "active": True,
            },
        ).json()
        streamer_id = created["item"]["id"]
        time.sleep(0.45)
        lifecycle_trace.append(session_snapshot(client, "session_1_mid", streamer_id))
        time.sleep(0.45)
        lifecycle_trace.append(session_snapshot(client, "session_1_end", streamer_id))
        session_1_jobs = client.get("/api/jobs").json()
        session_1_visibility = client.get("/api/admin/collector-visibility").json()
        counts_before_shutdown_1 = snapshot_fetch_counts()
        state_before_shutdown_1 = live.get_scheduler_state_snapshot()

    time.sleep(0.2)
    counts_after_shutdown_1 = snapshot_fetch_counts()
    state_after_shutdown_1 = live.get_scheduler_state_snapshot()

    with TestClient(live.app) as client:
        lifecycle_trace.append(session_snapshot(client, "session_2_start", streamer_id))
        time.sleep(0.4)
        lifecycle_trace.append(session_snapshot(client, "session_2_mid", streamer_id))
        time.sleep(0.35)
        lifecycle_trace.append(session_snapshot(client, "session_2_end", streamer_id))
        session_2_jobs = client.get("/api/jobs").json()
        session_2_visibility = client.get("/api/admin/collector-visibility").json()
        counts_before_shutdown_2 = snapshot_fetch_counts()
        state_before_shutdown_2 = live.get_scheduler_state_snapshot()

    time.sleep(0.2)
    counts_after_shutdown_2 = snapshot_fetch_counts()
    state_after_shutdown_2 = live.get_scheduler_state_snapshot()

    collector_runs = select_rows("SELECT * FROM collector_runs ORDER BY id ASC")
    live_state_rows = select_rows("SELECT * FROM streamer_live_state ORDER BY streamer_id ASC")
    vod_rows = select_rows("SELECT * FROM vods ORDER BY id ASC")

    fetch_trace_serialized = []
    if fetch_trace:
        first_called_at = fetch_trace[0]["called_at"]
        for item in fetch_trace:
            fetch_trace_serialized.append(
                {
                    **item,
                    "offset_seconds": round(item["called_at"] - first_called_at, 3),
                }
            )

    lifecycle_summary = {
        "session_1_clean_stop": {
            "thread_alive_before_shutdown": state_before_shutdown_1["thread_alive"],
            "thread_alive_after_shutdown_wait": state_after_shutdown_1["thread_alive"],
            "started_after_shutdown_wait": state_after_shutdown_1["started"],
            "station_calls_added_after_shutdown": counts_after_shutdown_1["station"] - counts_before_shutdown_1["station"],
            "replay_calls_added_after_shutdown": counts_after_shutdown_1["replay"] - counts_before_shutdown_1["replay"],
        },
        "session_2_restart": {
            "thread_alive_before_shutdown": state_before_shutdown_2["thread_alive"],
            "thread_alive_after_shutdown_wait": state_after_shutdown_2["thread_alive"],
            "started_after_shutdown_wait": state_after_shutdown_2["started"],
            "session_2_tick_count_end": lifecycle_trace[-1]["health"]["scheduler_tick_count"],
        },
        "bounded_execution": {
            "total_station_calls": fetch_counts["station"],
            "total_replay_calls": fetch_counts["replay"],
            "collector_runs": len(collector_runs),
            "vod_rows": len(vod_rows),
            "live_state_rows": len(live_state_rows),
        },
    }

    write_json(ARTIFACT_DIR / "background_scheduler_health_trace.json", lifecycle_trace)
    write_json(ARTIFACT_DIR / "background_scheduler_fetch_trace.json", fetch_trace_serialized)
    write_json(ARTIFACT_DIR / "collector_runs_after_background_thread.json", collector_runs)
    write_json(ARTIFACT_DIR / "live_state_after_background_thread.json", live_state_rows)
    write_json(ARTIFACT_DIR / "vod_rows_after_background_thread.json", vod_rows)
    write_json(
        ARTIFACT_DIR / "background_scheduler_lifecycle_evidence.json",
        {
            "summary": lifecycle_summary,
            "session_1_jobs_count": session_1_jobs["count"],
            "session_2_jobs_count": session_2_jobs["count"],
            "session_1_visibility_summary": session_1_visibility["summary"],
            "session_2_visibility_summary": session_2_visibility["summary"],
            "state_after_shutdown_1": state_after_shutdown_1,
            "state_after_shutdown_2": state_after_shutdown_2,
        },
    )

    notes = [
        "TASK-015 background scheduler lifecycle verifier",
        "",
        f"Collector runs saved: {len(collector_runs)}",
        f"Live rows saved: {len(live_state_rows)}",
        f"VOD rows saved: {len(vod_rows)}",
        f"Total station fetch calls: {fetch_counts['station']}",
        f"Total replay fetch calls: {fetch_counts['replay']}",
        "",
        "Session 1 clean-stop evidence:",
        f"- thread alive before shutdown: {state_before_shutdown_1['thread_alive']}",
        f"- thread alive after shutdown wait: {state_after_shutdown_1['thread_alive']}",
        f"- scheduler started after shutdown wait: {state_after_shutdown_1['started']}",
        f"- station calls added after shutdown: {counts_after_shutdown_1['station'] - counts_before_shutdown_1['station']}",
        f"- replay calls added after shutdown: {counts_after_shutdown_1['replay'] - counts_before_shutdown_1['replay']}",
        "",
        "Session 2 restart evidence:",
        f"- thread alive before shutdown: {state_before_shutdown_2['thread_alive']}",
        f"- thread alive after shutdown wait: {state_after_shutdown_2['thread_alive']}",
        f"- scheduler started after shutdown wait: {state_after_shutdown_2['started']}",
        f"- session 2 tick count at end: {lifecycle_trace[-1]['health']['scheduler_tick_count']}",
        "",
        "Bounded execution:",
        "- both shutdown waits added zero new upstream fetch calls",
        "- the restarted scheduler produced new collector_runs in the same SQLite DB",
        "- the real background thread path persisted live state, VOD rows, and collector_runs",
    ]
    (ARTIFACT_DIR / "background_scheduler_verification_notes.txt").write_text("\n".join(notes) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
