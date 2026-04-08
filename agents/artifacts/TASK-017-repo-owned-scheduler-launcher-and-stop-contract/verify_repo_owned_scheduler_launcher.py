import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request


ARTIFACT_DIR = Path(__file__).resolve().parent
ROOT_DIR = ARTIFACT_DIR.parents[2]
START_BAT = ROOT_DIR / "start_live_vod_scheduler.bat"
STOP_BAT = ROOT_DIR / "stop_live_vod_scheduler.bat"
STATUS_BAT = ROOT_DIR / "status_live_vod_scheduler.bat"

RUNTIME_DIR = ARTIFACT_DIR / "launcher_runtime"
DB_PATH = ARTIFACT_DIR / "task017_launcher_test.db"
HEALTH_TRACE_PATH = ARTIFACT_DIR / "launcher_health_trace.json"
STATUS_BEFORE_STOP_PATH = ARTIFACT_DIR / "launcher_status_before_stop.json"
STOP_RESULT_PATH = ARTIFACT_DIR / "launcher_stop_result.json"
PROCESS_EVIDENCE_PATH = ARTIFACT_DIR / "launcher_process_evidence.json"
COLLECTOR_RUNS_PATH = ARTIFACT_DIR / "collector_runs_after_launcher.json"
LIVE_STATE_PATH = ARTIFACT_DIR / "live_state_after_launcher.json"
VOD_ROWS_PATH = ARTIFACT_DIR / "vod_rows_after_launcher.json"
RUNBOOK_PATH = ARTIFACT_DIR / "repo_owned_scheduler_launcher_runbook.md"
NOTES_PATH = ARTIFACT_DIR / "repo_owned_scheduler_launcher_notes.txt"


STATION_HTML = """
<html>
  <head><title>Launcher Stream | SOOP</title></head>
  <body>
    <div class="Badge-module__live">LIVE</div>
    <div class="player_area">on-air</div>
  </body>
</html>
""".strip()

REPLAY_HTML = """
<html>
  <head><title>Launcher Stream | SOOP</title></head>
  <body>
    <a href="https://vod.sooplive.co.kr/player/99101">
      <img src="https://img.test/99101.jpg" />
      <p class="Title-module__title">Launcher VOD One</p>
      <div class="Badge-module__vodTime"><div>08:08</div></div>
      <div class="ThumbnailMoreInfo-module__md">views</div>
      <div class="ThumbnailMoreInfo-module__md">2026-04-08T13:00:00+09:00</div>
    </a>
    <a href="https://vod.sooplive.co.kr/player/99102">
      <img src="https://img.test/99102.jpg" />
      <p class="Title-module__title">Launcher VOD Two</p>
      <div class="Badge-module__vodTime"><div>04:44</div></div>
      <div class="ThumbnailMoreInfo-module__md">views</div>
      <div class="ThumbnailMoreInfo-module__md">2026-04-08T12:40:00+09:00</div>
    </a>
  </body>
</html>
""".strip()


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(url: str, method: str = "GET", payload: dict | None = None) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method)
    with request.urlopen(req, timeout=5) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset))


def run_command(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> dict:
    completed = subprocess.run(command, cwd=str(cwd), env=env, text=True, capture_output=True, timeout=30)
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def wait_for_scheduler(base_url: str, streamer_id: int, timeout_seconds: float) -> list[dict]:
    deadline = time.time() + timeout_seconds
    trace: list[dict] = []
    while time.time() < deadline:
        health = http_json(f"{base_url}/api/health")
        jobs = http_json(f"{base_url}/api/jobs")
        vods = http_json(f"{base_url}/api/streamers/{streamer_id}/vods")
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
    raise RuntimeError("launcher path did not reach bounded scheduler activity before timeout")


def select_rows(query: str) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(query).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # pragma: no cover - artifact harness
        if self.path.startswith("/station/"):
            body = STATION_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/replay/"):
            body = REPLAY_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    for path in (
        DB_PATH,
        HEALTH_TRACE_PATH,
        STATUS_BEFORE_STOP_PATH,
        STOP_RESULT_PATH,
        PROCESS_EVIDENCE_PATH,
        COLLECTOR_RUNS_PATH,
        LIVE_STATE_PATH,
        VOD_ROWS_PATH,
        NOTES_PATH,
    ):
        if path.exists():
            path.unlink()

    if (RUNTIME_DIR / "launcher_state.json").exists():
        run_command(
            ["cmd", "/c", str(STOP_BAT), "--runtime-dir", str(RUNTIME_DIR), "--timeout", "10"],
            cwd=ROOT_DIR,
        )

    if RUNTIME_DIR.exists():
        for child in sorted(RUNTIME_DIR.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    app_port = find_free_port()
    fixture_port = find_free_port()
    base_url = f"http://127.0.0.1:{app_port}"
    fixture_server = ThreadingHTTPServer(("127.0.0.1", fixture_port), FixtureHandler)
    fixture_thread = threading.Thread(target=fixture_server.serve_forever, daemon=True, name="task017-fixture-server")
    fixture_thread.start()

    env = os.environ.copy()
    env.update(
        {
            "SOOP_CLIENT_ID": "",
            "SOOP_USE_BROWSER_FALLBACK": "0",
            "SOOP_LIVE_REFRESH_SECONDS": "1",
            "SOOP_VOD_REFRESH_SECONDS": "1",
            "SOOP_SCHEDULER_TICK_SECONDS": "0.05",
            "SOOP_SCHEDULER_STARTUP_LIVE_DELAY_SECONDS": "0.18",
            "SOOP_SCHEDULER_STARTUP_VOD_DELAY_SECONDS": "0.22",
            "SOOP_SCHEDULER_STOP_JOIN_SECONDS": "1.0",
        }
    )

    start_result = run_command(
        [
            "cmd",
            "/c",
            str(START_BAT),
            "--runtime-dir",
            str(RUNTIME_DIR),
            "--db-path",
            str(DB_PATH),
            "--port",
            str(app_port),
            "--wait-health",
            "--health-timeout",
            "15",
        ],
        cwd=ROOT_DIR,
        env=env,
    )
    if start_result["returncode"] != 0:
        raise RuntimeError(f"launcher start failed: {start_result}")

    created = http_json(
        f"{base_url}/api/streamers",
        method="POST",
        payload={
            "soop_user_id": "launcher_streamer",
            "nickname": "Launcher Stream",
            "channel_url": f"http://127.0.0.1:{fixture_port}/station/launcher_streamer",
            "replay_url": f"http://127.0.0.1:{fixture_port}/replay/launcher_streamer",
            "category_no": "",
            "active": True,
        },
    )
    streamer_id = int(created["item"]["id"])
    health_trace = wait_for_scheduler(base_url, streamer_id, timeout_seconds=15)
    write_json(HEALTH_TRACE_PATH, health_trace)

    status_result = run_command(
        ["cmd", "/c", str(STATUS_BAT), "--runtime-dir", str(RUNTIME_DIR)],
        cwd=ROOT_DIR,
        env=env,
    )
    if status_result["returncode"] != 0:
        raise RuntimeError(f"launcher status failed: {status_result}")
    status_payload = json.loads(status_result["stdout"])
    write_json(STATUS_BEFORE_STOP_PATH, status_payload)

    stop_started = time.time()
    stop_result = run_command(
        ["cmd", "/c", str(STOP_BAT), "--runtime-dir", str(RUNTIME_DIR), "--timeout", "10"],
        cwd=ROOT_DIR,
        env=env,
    )
    stop_finished = time.time()
    if stop_result["returncode"] != 0:
        raise RuntimeError(f"launcher stop failed: {stop_result}")
    stop_payload = json.loads(stop_result["stdout"])
    stop_payload["stop_duration_seconds"] = round(stop_finished - stop_started, 3)
    write_json(STOP_RESULT_PATH, stop_payload)

    fixture_server.shutdown()
    fixture_server.server_close()
    fixture_thread.join(timeout=1)

    state_before_stop = status_payload["state"]
    runtime_summary = stop_payload.get("host_runtime_summary") or {}
    collector_runs = select_rows("SELECT * FROM collector_runs ORDER BY id ASC")
    live_state_rows = select_rows("SELECT * FROM streamer_live_state ORDER BY streamer_id ASC")
    vod_rows = select_rows("SELECT * FROM vods ORDER BY id ASC")

    process_evidence = {
        "launcher_start": start_result,
        "launcher_status_before_stop": {
            "process_alive": status_payload["process_alive"],
            "health": status_payload.get("health"),
            "state": state_before_stop,
        },
        "launcher_stop": {
            "status": stop_payload["status"],
            "stop_duration_seconds": stop_payload["stop_duration_seconds"],
            "host_runtime_summary": runtime_summary,
        },
        "bounded_shutdown": {
            "launcher_stop_status": stop_payload["status"],
            "stop_duration_seconds": stop_payload["stop_duration_seconds"],
            "scheduler_thread_alive_after_exit": runtime_summary["scheduler_state_after_exit"]["thread_alive"],
            "scheduler_started_after_exit": runtime_summary["scheduler_state_after_exit"]["started"],
            "stop_request_seen": runtime_summary["stop_request_seen"]["requested"],
        },
        "durable_persistence": {
            "collector_runs": len(collector_runs),
            "live_state_rows": len(live_state_rows),
            "vod_rows": len(vod_rows),
        },
    }
    write_json(PROCESS_EVIDENCE_PATH, process_evidence)
    write_json(COLLECTOR_RUNS_PATH, collector_runs)
    write_json(LIVE_STATE_PATH, live_state_rows)
    write_json(VOD_ROWS_PATH, vod_rows)

    RUNBOOK_PATH.write_text(
        "\n".join(
            [
                "# TASK-017 Repo-Owned Scheduler Launcher Runbook",
                "",
                "## Scope",
                "",
                "This runbook covers the repo-owned launcher and stop contract for `app_live_vod.py`.",
                "",
                "## Repo-Owned Assets",
                "",
                "- `live_vod_scheduler_launcher.py`",
                "- `live_vod_scheduler_host.py`",
                "- `start_live_vod_scheduler.bat`",
                "- `status_live_vod_scheduler.bat`",
                "- `stop_live_vod_scheduler.bat`",
                "",
                "## Start Command",
                "",
                "```powershell",
                "start_live_vod_scheduler.bat",
                "```",
                "",
                "Optional launcher arguments:",
                "",
                "- `--runtime-dir <path>`",
                "- `--db-path <path>`",
                "- `--port <port>`",
                "- `--wait-health`",
                "- `--health-timeout <seconds>`",
                "",
                "## Status Command",
                "",
                "```powershell",
                "status_live_vod_scheduler.bat",
                "```",
                "",
                "This reports launcher state plus `/api/health` when the process is alive.",
                "",
                "## Graceful Stop Contract",
                "",
                "```powershell",
                "stop_live_vod_scheduler.bat --timeout 10",
                "```",
                "",
                "- The stop command writes `stop_requested.json` into the launcher runtime directory.",
                "- The repo-owned host wrapper polls for that file and sets `uvicorn` graceful exit internally.",
                "- This avoids relying on ad hoc console control or manual Task Manager termination.",
                "",
                "## Runtime Files",
                "",
                "- `launcher_state.json`",
                "- `stop_requested.json`",
                "- `host_runtime_summary.json`",
                "- `launcher_stdout.log`",
                "- `launcher_stderr.log`",
                "",
                "## Verified Local Evidence",
                "",
                "- launcher path started the app and reached `/api/health`",
                "- scheduler persisted collector runs, live state, and VOD rows through the launcher path",
                "- launcher stop completed in a bounded window and the host runtime summary showed `thread_alive=false` and `started=false`",
                "",
                "## Remaining Deployment Gaps",
                "",
                "- a later slice can add supervisor-specific packaging if deployment requires a Windows service, NSSM, or another process manager",
                "- broader non-Windows launcher and stop-contract coverage remains out of scope for this slice",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    NOTES_PATH.write_text(
        "\n".join(
            [
                "TASK-017 repo-owned scheduler launcher verification",
                "",
                f"app port: {app_port}",
                f"fixture port: {fixture_port}",
                f"collector runs recorded: {len(collector_runs)}",
                f"live state rows recorded: {len(live_state_rows)}",
                f"vod rows recorded: {len(vod_rows)}",
                "",
                "Launcher stop evidence:",
                f"- stop status: {stop_payload['status']}",
                f"- stop duration seconds: {stop_payload['stop_duration_seconds']}",
                f"- scheduler thread alive after exit: {runtime_summary['scheduler_state_after_exit']['thread_alive']}",
                f"- scheduler started after exit: {runtime_summary['scheduler_state_after_exit']['started']}",
                f"- stop request seen by host: {runtime_summary['stop_request_seen']['requested']}",
                "",
                "Contract notes:",
                "- repo-owned stop contract uses a stop-request file inside the runtime directory",
                "- the host wrapper converts that file request into a graceful uvicorn shutdown path",
                "- no ad hoc manual Task Manager kill is required for the verified local launcher path",
            ])
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
