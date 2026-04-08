import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, r"C:\python")

import app_live_vod as mod


ARTIFACT_DIR = Path(r"C:\python\agents\artifacts\TASK-014-scheduler-mixed-latency-and-repeated-failure-hardening")
DB_PATH = ARTIFACT_DIR / "task014_scheduler_hardening.db"


def capture_db_state(db_path: Path) -> tuple[list[dict], list[dict]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        run_rows = [
            dict(row)
            for row in conn.execute(
                "SELECT id, collector_type, streamer_id, status, started_at, finished_at, message "
                "FROM collector_runs ORDER BY id"
            ).fetchall()
        ]
        backoff_rows = [
            dict(row)
            for row in conn.execute(
                "SELECT scope_key, collector_type, streamer_id, reason, failures, backoff_seconds, retry_after "
                "FROM collector_backoffs ORDER BY scope_key"
            ).fetchall()
        ]
    return run_rows, backoff_rows


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    mod.DB_PATH = DB_PATH
    mod.USE_BROWSER_FALLBACK = False
    mod.SOOP_CLIENT_ID = "fixture-client"
    mod.LIVE_REFRESH_SECONDS = 3
    mod.VOD_REFRESH_SECONDS = 1
    mod.SCHEDULER_TICK_SECONDS = 0.1
    mod.COLLECTOR_BACKOFF_SECONDS = 2
    mod.COLLECTOR_BACKOFF_MAX_SECONDS = 4
    mod.collector_backoff_state.clear()
    mod.streamer_vod_locks.clear()
    mod.scheduler_state["started"] = True
    mod.scheduler_state["stop"] = True
    mod.init_db()
    mod.create_streamer(
        mod.StreamerCreate(
            soop_user_id="alpha_user",
            nickname="Alpha Scheduler",
            replay_url="https://fixture.local/vod-alpha",
            active=True,
        )
    )

    original_fetch_text = mod.fetch_text
    live_calls: list[dict] = []
    vod_calls: list[dict] = []
    state = {
        "vod_outcomes": ["timeout", "timeout", "success"],
        "current_vod_outcome": None,
    }
    replay_url = "https://fixture.local/vod-alpha"
    last_vod_url = "https://ch.sooplive.co.kr/alpha_user/vods/review"
    all_vod_urls = {
        replay_url,
        "https://www.sooplive.co.kr/station/alpha_user",
        "https://ch.sooplive.co.kr/alpha_user",
        last_vod_url,
    }
    live_success_payload = (
        'callback({"broad": [{"user_id": "alpha_user", "broad_no": "881122", '
        '"broad_title": "Scheduler Live", "total_view_cnt": 44}]});'
    )
    vod_success_html = """
<html><head><title>Alpha Scheduler 방송국 | SOOP</title></head><body>
  <a href="https://vod.sooplive.co.kr/player/611001">
    <img src="https://img.local/alpha-scheduler.jpg" />
    <p class="Title-module__title">Scheduler Recovery VOD</p>
    <div class="Badge-module__vodTime"><div>00:18:00</div></div>
    <div class="ThumbnailMoreInfo-module__md">조회수 11</div>
    <div class="ThumbnailMoreInfo-module__md">2026-04-08 03:10</div>
  </a>
</body></html>
"""

    def fake_fetch_text(url: str) -> str:
        if "openapi.sooplive.co.kr/broad/list" in url:
            live_calls.append({"url": url, "ts": time.time()})
            time.sleep(1.2)
            return live_success_payload
        if url in all_vod_urls:
            vod_calls.append({"url": url, "ts": time.time()})
            if url == replay_url:
                if state["vod_outcomes"]:
                    state["current_vod_outcome"] = state["vod_outcomes"].pop(0)
                else:
                    state["current_vod_outcome"] = "success"
            outcome = state["current_vod_outcome"] or "success"
            if outcome == "timeout":
                if url == last_vod_url:
                    state["current_vod_outcome"] = None
                raise TimeoutError("scheduler vod timeout")
            state["current_vod_outcome"] = None
            return vod_success_html
        raise ValueError(f"unexpected fixture url: {url}")

    mod.fetch_text = fake_fetch_text
    mod.scheduler_state["next_live"] = 0.0
    mod.scheduler_state["next_vod"] = 0.0

    trace = []
    try:
        for label, sleep_before in [
            ("tick_1_initial", 0.0),
            ("tick_2_immediate", 0.0),
            ("tick_3_due_backoff_skip", 1.05),
            ("tick_4_due_repeated_failure", 1.05),
            ("tick_5_due_backoff_skip", 1.05),
            ("tick_6_due_recovery", 1.05),
        ]:
            if sleep_before:
                time.sleep(sleep_before)
            live_before = len(live_calls)
            vod_before = len(vod_calls)
            start = time.time()
            result = mod.run_scheduler_tick()
            duration = time.time() - start
            run_rows, backoff_rows = capture_db_state(DB_PATH)
            trace.append(
                {
                    "label": label,
                    "duration_seconds": round(duration, 3),
                    "result": result,
                    "live_fetches_added": len(live_calls) - live_before,
                    "vod_fetches_added": len(vod_calls) - vod_before,
                    "collector_runs_count": len(run_rows),
                    "collector_backoffs_count": len(backoff_rows),
                    "latest_run_statuses": [
                        f"{row['collector_type']}:{row['status']}" for row in run_rows[-4:]
                    ],
                }
            )

        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            collector_runs = [
                dict(row)
                for row in conn.execute(
                    "SELECT id, collector_type, streamer_id, status, started_at, finished_at, message "
                    "FROM collector_runs ORDER BY id"
                ).fetchall()
            ]
            collector_backoffs = [
                dict(row)
                for row in conn.execute(
                    "SELECT scope_key, collector_type, streamer_id, reason, failures, backoff_seconds, retry_after "
                    "FROM collector_backoffs ORDER BY scope_key"
                ).fetchall()
            ]
            live_state_rows = [
                dict(row)
                for row in conn.execute(
                    "SELECT streamer_id, is_live, broad_no, live_title, viewer_count, last_checked_at, last_live_seen_at "
                    "FROM streamer_live_state ORDER BY streamer_id"
                ).fetchall()
            ]
            vod_rows = [
                dict(row)
                for row in conn.execute(
                    "SELECT streamer_id, vod_id, title, vod_url, published_at, duration_text, collected_at, last_seen_at "
                    "FROM vods ORDER BY id"
                ).fetchall()
            ]

        visibility = mod.get_collector_visibility_snapshot(20)

        (ARTIFACT_DIR / "scheduler_tick_trace.json").write_text(
            json.dumps(trace, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (ARTIFACT_DIR / "scheduler_fetch_pressure_trace.json").write_text(
            json.dumps(
                {
                    "live_calls": live_calls,
                    "vod_calls": vod_calls,
                    "tick_trace": trace,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (ARTIFACT_DIR / "collector_runs_after_scheduler_hardening.json").write_text(
            json.dumps({"items": collector_runs, "count": len(collector_runs)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (ARTIFACT_DIR / "collector_backoffs_after_scheduler_hardening.json").write_text(
            json.dumps({"items": collector_backoffs, "count": len(collector_backoffs)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (ARTIFACT_DIR / "recent_state_after_scheduler_hardening.json").write_text(
            json.dumps(
                {
                    "visibility": visibility,
                    "live_state_rows": live_state_rows,
                    "vod_rows": vod_rows,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        notes = [
            "TASK-014 scheduler mixed-latency and repeated-failure verification",
            f"Tick count: {len(trace)}",
            f"Final collector_runs: {len(collector_runs)}",
            f"Final collector_backoffs: {len(collector_backoffs)}",
            f"Live fetch count: {len(live_calls)}",
            f"VOD fetch count: {len(vod_calls)}",
            f"Immediate tick live/vod added fetches: {trace[1]['live_fetches_added']} / {trace[1]['vod_fetches_added']}",
            f"First backoff skip tick live/vod added fetches: {trace[2]['live_fetches_added']} / {trace[2]['vod_fetches_added']}",
            f"Late recovery tick live/vod added fetches: {trace[4]['live_fetches_added']} / {trace[4]['vod_fetches_added']}",
            "Expected pattern: slow live execution does not trigger immediate catch-up on the next tick, VOD fails twice across scheduled ticks, the first backoff-active tick skips VOD without extra upstream fetch, and later ticks recover cleanly.",
        ]
        (ARTIFACT_DIR / "scheduler_hardening_verification_notes.txt").write_text(
            "\n".join(notes) + "\n",
            encoding="utf-8",
        )
    finally:
        mod.fetch_text = original_fetch_text


if __name__ == "__main__":
    main()
