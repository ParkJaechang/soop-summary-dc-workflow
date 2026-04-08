import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib import error, request


ARTIFACT_DIR = Path(__file__).resolve().parent
ROOT_DIR = ARTIFACT_DIR.parents[2]
CHILD_SCRIPT = ARTIFACT_DIR / "external_scheduler_child.py"
DB_PATH = ARTIFACT_DIR / "task016_external_scheduler_test.db"
CHILD_FETCH_LOG_PATH = ARTIFACT_DIR / "external_scheduler_fetch_trace.json"
CHILD_RUNTIME_SUMMARY_PATH = ARTIFACT_DIR / "external_scheduler_child_runtime_summary.json"
PROCESS_EVIDENCE_PATH = ARTIFACT_DIR / "external_scheduler_process_evidence.json"
HEALTH_TRACE_PATH = ARTIFACT_DIR / "external_scheduler_health_trace.json"
COLLECTOR_RUNS_PATH = ARTIFACT_DIR / "collector_runs_after_external_process.json"
LIVE_STATE_PATH = ARTIFACT_DIR / "live_state_after_external_process.json"
VOD_ROWS_PATH = ARTIFACT_DIR / "vod_rows_after_external_process.json"
RUNBOOK_PATH = ARTIFACT_DIR / "external_scheduler_service_runbook.md"
NOTES_PATH = ARTIFACT_DIR / "external_scheduler_verification_notes.txt"
STDOUT_PATH = ARTIFACT_DIR / "external_scheduler_child_stdout.log"
STDERR_PATH = ARTIFACT_DIR / "external_scheduler_child_stderr.log"


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def select_rows(query: str) -> list[dict[str, object]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(query).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(method: str, url: str, payload: dict | None = None) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method)
    with request.urlopen(req, timeout=5) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset))


def wait_for_health(base_url: str, timeout_seconds: float) -> list[dict[str, object]]:
    deadline = time.time() + timeout_seconds
    trace: list[dict[str, object]] = []
    while time.time() < deadline:
        try:
            payload = http_json("GET", f"{base_url}/api/health")
            trace.append({"label": "healthy", "observed_at": time.time(), "health": payload})
            return trace
        except Exception as exc:  # pragma: no cover - artifact harness
            trace.append({"label": "retry", "observed_at": time.time(), "error": repr(exc)})
            time.sleep(0.15)
    raise RuntimeError("external scheduler child did not reach /api/health before timeout")


def wait_for_scheduler_work(base_url: str, streamer_id: int, timeout_seconds: float) -> list[dict[str, object]]:
    deadline = time.time() + timeout_seconds
    trace: list[dict[str, object]] = []
    while time.time() < deadline:
        health = http_json("GET", f"{base_url}/api/health")
        jobs = http_json("GET", f"{base_url}/api/jobs")
        vods = http_json("GET", f"{base_url}/api/streamers/{streamer_id}/vods")
        snapshot = {
            "observed_at": time.time(),
            "health": health,
            "jobs_count": jobs["count"],
            "vod_count": vods["count"],
        }
        trace.append(snapshot)
        if health["scheduler_tick_count"] >= 3 and jobs["count"] >= 2 and vods["count"] >= 1:
            return trace
        time.sleep(0.2)
    raise RuntimeError("external scheduler child did not produce bounded scheduler evidence before timeout")


def main() -> None:
    for path in (
        DB_PATH,
        CHILD_FETCH_LOG_PATH,
        CHILD_RUNTIME_SUMMARY_PATH,
        PROCESS_EVIDENCE_PATH,
        HEALTH_TRACE_PATH,
        COLLECTOR_RUNS_PATH,
        LIVE_STATE_PATH,
        VOD_ROWS_PATH,
        NOTES_PATH,
        STDOUT_PATH,
        STDERR_PATH,
    ):
        if path.exists():
            path.unlink()

    port = find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    env = os.environ.copy()
    env.update(
        {
            "TASK016_DB_PATH": str(DB_PATH),
            "TASK016_PORT": str(port),
            "TASK016_CHILD_FETCH_LOG": str(CHILD_FETCH_LOG_PATH),
            "TASK016_CHILD_RUNTIME_SUMMARY": str(CHILD_RUNTIME_SUMMARY_PATH),
        }
    )

    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    started_at = time.time()
    with STDOUT_PATH.open("w", encoding="utf-8") as stdout_handle, STDERR_PATH.open("w", encoding="utf-8") as stderr_handle:
        process = subprocess.Popen(
            [sys.executable, str(CHILD_SCRIPT)],
            cwd=str(ROOT_DIR),
            env=env,
            stdout=stdout_handle,
            stderr=stderr_handle,
            creationflags=creationflags,
        )

        health_trace = wait_for_health(base_url, timeout_seconds=15)
        created = http_json(
            "POST",
            f"{base_url}/api/streamers",
            payload={
                "soop_user_id": "external_scheduler_streamer",
                "nickname": "External Scheduler Stream",
                "channel_url": "https://fixture.test/station/external_scheduler_streamer",
                "replay_url": "https://fixture.test/replay/external_scheduler_streamer",
                "category_no": "",
                "active": True,
            },
        )
        streamer_id = int(created["item"]["id"])
        scheduler_trace = wait_for_scheduler_work(base_url, streamer_id, timeout_seconds=15)
        health_trace.extend(
            {
                **item,
                "label": f"scheduler_trace_{index + 1}",
            }
            for index, item in enumerate(scheduler_trace)
        )
        jobs_before_stop = http_json("GET", f"{base_url}/api/jobs")
        health_before_stop = http_json("GET", f"{base_url}/api/health")

        stop_requested_at = time.time()
        process.send_signal(signal.CTRL_BREAK_EVENT)
        exited_cleanly = False
        forced_terminate = False
        try:
            process.wait(timeout=6)
            exited_cleanly = True
        except subprocess.TimeoutExpired:
            forced_terminate = True
            process.kill()
            process.wait(timeout=3)

    finished_at = time.time()
    if not CHILD_RUNTIME_SUMMARY_PATH.exists():
        raise RuntimeError("external scheduler child did not write its shutdown summary")

    child_runtime = json.loads(CHILD_RUNTIME_SUMMARY_PATH.read_text(encoding="utf-8"))
    fetch_trace = json.loads(CHILD_FETCH_LOG_PATH.read_text(encoding="utf-8"))
    collector_runs = select_rows("SELECT * FROM collector_runs ORDER BY id ASC")
    live_state_rows = select_rows("SELECT * FROM streamer_live_state ORDER BY streamer_id ASC")
    vod_rows = select_rows("SELECT * FROM vods ORDER BY id ASC")

    stop_duration_seconds = round(finished_at - stop_requested_at, 3)
    process_evidence = {
        "process": {
            "pid": process.pid,
            "port": port,
            "started_at_epoch": started_at,
            "stop_requested_at_epoch": stop_requested_at,
            "finished_at_epoch": finished_at,
            "stop_duration_seconds": stop_duration_seconds,
            "returncode": process.returncode,
            "exited_cleanly": exited_cleanly,
            "forced_terminate": forced_terminate,
        },
        "health_before_stop": health_before_stop,
        "jobs_before_stop_count": jobs_before_stop["count"],
        "child_runtime_summary": child_runtime,
        "bounded_shutdown": {
            "scheduler_thread_alive_after_exit": child_runtime["scheduler_state_after_exit"]["thread_alive"],
            "scheduler_started_after_exit": child_runtime["scheduler_state_after_exit"]["started"],
            "scheduler_stop_requested_after_exit": child_runtime["scheduler_state_after_exit"]["stop"],
            "scheduler_stopped_at_after_exit": child_runtime["scheduler_state_after_exit"]["stopped_at"],
            "fetch_calls_recorded": len(fetch_trace),
            "collector_runs_recorded": len(collector_runs),
            "live_state_rows_recorded": len(live_state_rows),
            "vod_rows_recorded": len(vod_rows),
        },
    }

    write_json(HEALTH_TRACE_PATH, health_trace)
    write_json(PROCESS_EVIDENCE_PATH, process_evidence)
    write_json(COLLECTOR_RUNS_PATH, collector_runs)
    write_json(LIVE_STATE_PATH, live_state_rows)
    write_json(VOD_ROWS_PATH, vod_rows)

    notes = [
        "TASK-016 external-process scheduler supervision verification",
        "",
        f"child pid: {process.pid}",
        f"port: {port}",
        f"jobs before stop: {jobs_before_stop['count']}",
        f"collector runs recorded: {len(collector_runs)}",
        f"live rows recorded: {len(live_state_rows)}",
        f"vod rows recorded: {len(vod_rows)}",
        f"fetch calls recorded: {len(fetch_trace)}",
        "",
        "Graceful stop evidence:",
        f"- stop duration seconds: {stop_duration_seconds}",
        f"- process exited cleanly: {exited_cleanly}",
        f"- process forced terminate used: {forced_terminate}",
        f"- scheduler thread alive after exit: {child_runtime['scheduler_state_after_exit']['thread_alive']}",
        f"- scheduler started after exit: {child_runtime['scheduler_state_after_exit']['started']}",
        f"- scheduler stop requested after exit: {child_runtime['scheduler_state_after_exit']['stop']}",
        f"- scheduler stopped_at after exit: {child_runtime['scheduler_state_after_exit']['stopped_at']}",
        "",
        "Operational ownership notes:",
        "- external supervision was exercised by running the FastAPI app in a separate Python process",
        "- graceful stop was requested with CTRL_BREAK_EVENT against a dedicated process group on Windows",
        "- the child wrote a shutdown summary after uvicorn returned, which proves the app got a graceful shutdown path rather than a hard kill",
        "- if a future service manager cannot send a graceful console-break style signal, that manager needs a wrapper or stop command equivalent before hard terminate",
    ]
    NOTES_PATH.write_text("\n".join(notes) + "\n", encoding="utf-8")

    RUNBOOK_PATH.write_text(
        "\n".join(
            [
                "# TASK-016 External Scheduler Service Runbook",
                "",
                "## Scope",
                "",
                "This runbook covers service-style ownership for `app_live_vod.py` as an externally supervised process.",
                "",
                "## Proven Local Supervision Pattern",
                "",
                "1. Start the app as its own Python process.",
                "2. Wait for `GET /api/health` to report a live scheduler thread.",
                "3. Use `GET /api/jobs` and `GET /api/admin/collector-visibility` for runtime visibility.",
                "4. Stop the process with a graceful console-break style signal first, not a hard kill.",
                "5. Confirm bounded shutdown by checking process exit time plus scheduler state in the saved runtime summary.",
                "",
                "## Verified Local Command Shape",
                "",
                "```powershell",
                "python app_live_vod.py",
                "```",
                "",
                "The verifier for this task used a dedicated child wrapper to keep DB path, fake upstream responses, and artifact logging deterministic:",
                "",
                "```powershell",
                "python agents/artifacts/TASK-016-external-process-scheduler-supervision-and-graceful-stop/verify_external_scheduler_supervision.py",
                "```",
                "",
                "## Health Checks",
                "",
                "- `GET /api/health`",
                "  confirms DB reachability plus scheduler thread state",
                "- `GET /api/jobs`",
                "  confirms collector runs are being written",
                "- `GET /api/admin/collector-visibility`",
                "  confirms recent status and backoff visibility",
                "",
                "## Graceful Stop Expectation",
                "",
                "- On Windows, prefer sending `CTRL_BREAK_EVENT` to a dedicated process group.",
                "- Treat hard terminate as a fallback only when graceful stop times out.",
                "- A bounded stop is considered proven when the process exits within the configured wait window and the final scheduler snapshot shows `thread_alive=false` and `started=false`.",
                "",
                "## Evidence Files",
                "",
                "- `external_scheduler_process_evidence.json`",
                "- `external_scheduler_health_trace.json`",
                "- `external_scheduler_fetch_trace.json`",
                "- `external_scheduler_child_runtime_summary.json`",
                "- `collector_runs_after_external_process.json`",
                "- `live_state_after_external_process.json`",
                "- `vod_rows_after_external_process.json`",
                "- `external_scheduler_verification_notes.txt`",
                "",
                "## Remaining Dependencies",
                "",
                "- A later product-hardening slice can add a repo-owned launcher or service wrapper if deployment moves beyond ad hoc Python process supervision.",
                "- If the production supervisor cannot emit a graceful stop signal equivalent to the verified local pattern, that integration needs its own stop-contract evidence.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
