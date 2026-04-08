import json
import os
import socket
import sqlite3
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request


ARTIFACT_DIR = Path(__file__).resolve().parent
ROOT_DIR = ARTIFACT_DIR.parents[2]
INSTALL_PS1 = ROOT_DIR / "install_live_vod_scheduler_task.ps1"
RUN_PS1 = ROOT_DIR / "run_live_vod_scheduler_task.ps1"
STATUS_PS1 = ROOT_DIR / "status_live_vod_scheduler_task.ps1"
STOP_PS1 = ROOT_DIR / "stop_live_vod_scheduler_task.ps1"
REMOVE_PS1 = ROOT_DIR / "remove_live_vod_scheduler_task.ps1"

TASK_NAME = "SOOP-LiveVOD-Task018"
RUNTIME_DIR = ROOT_DIR / "data" / "t018rt"
DB_PATH = ROOT_DIR / "data" / "t018.db"
REGISTRATION_PATH = ARTIFACT_DIR / "task_scheduler_registration.json"
TASK_XML_PATH = ARTIFACT_DIR / "task_scheduler_definition.xml"
RUN_RESULT_PATH = ARTIFACT_DIR / "task_scheduler_run_result.json"
STATUS_BEFORE_STOP_PATH = ARTIFACT_DIR / "task_scheduler_status_before_stop.json"
STOP_RESULT_PATH = ARTIFACT_DIR / "task_scheduler_stop_result.json"
PROCESS_EVIDENCE_PATH = ARTIFACT_DIR / "task_scheduler_process_evidence.json"
HEALTH_TRACE_PATH = ARTIFACT_DIR / "task_scheduler_health_trace.json"
HOST_RUNTIME_SUMMARY_PATH = ARTIFACT_DIR / "task_scheduler_host_runtime_summary.json"
LAUNCHER_STDOUT_PATH = ARTIFACT_DIR / "task_scheduler_launcher_stdout.log"
LAUNCHER_STDERR_PATH = ARTIFACT_DIR / "task_scheduler_launcher_stderr.log"
COLLECTOR_RUNS_PATH = ARTIFACT_DIR / "collector_runs_after_task_scheduler.json"
LIVE_STATE_PATH = ARTIFACT_DIR / "live_state_after_task_scheduler.json"
VOD_ROWS_PATH = ARTIFACT_DIR / "vod_rows_after_task_scheduler.json"
RUNBOOK_PATH = ARTIFACT_DIR / "task_scheduler_supervisor_runbook.md"
NOTES_PATH = ARTIFACT_DIR / "task_scheduler_supervisor_notes.txt"


STATION_HTML = """
<html>
  <head><title>Task Scheduler Stream | SOOP</title></head>
  <body>
    <div class="Badge-module__live">LIVE</div>
    <div class="player_area">on-air</div>
  </body>
</html>
""".strip()

REPLAY_HTML = """
<html>
  <head><title>Task Scheduler Stream | SOOP</title></head>
  <body>
    <a href="https://vod.sooplive.co.kr/player/99201">
      <img src="https://img.test/99201.jpg" />
      <p class="Title-module__title">Task Scheduler VOD One</p>
      <div class="Badge-module__vodTime"><div>07:07</div></div>
      <div class="ThumbnailMoreInfo-module__md">views</div>
      <div class="ThumbnailMoreInfo-module__md">2026-04-08T14:00:00+09:00</div>
    </a>
    <a href="https://vod.sooplive.co.kr/player/99202">
      <img src="https://img.test/99202.jpg" />
      <p class="Title-module__title">Task Scheduler VOD Two</p>
      <div class="Badge-module__vodTime"><div>03:33</div></div>
      <div class="ThumbnailMoreInfo-module__md">views</div>
      <div class="ThumbnailMoreInfo-module__md">2026-04-08T13:40:00+09:00</div>
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
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def run_powershell(script: Path, args: list[str], env: dict[str, str]) -> dict:
    return run_command(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *args],
        cwd=ROOT_DIR,
        env=env,
    )


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
    raise RuntimeError("task scheduler packaging did not reach bounded scheduler activity before timeout")


def select_rows(query: str) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(query).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
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


def cleanup_previous(env: dict[str, str]) -> None:
    run_powershell(REMOVE_PS1, ["-TaskName", TASK_NAME], env)
    if (RUNTIME_DIR / "launcher_state.json").exists():
        run_powershell(
            STOP_PS1,
            ["-TaskName", TASK_NAME, "-RuntimeDir", str(RUNTIME_DIR), "-DbPath", str(DB_PATH), "-TimeoutSeconds", "5"],
            env,
        )
    if RUNTIME_DIR.exists():
        for child in sorted(RUNTIME_DIR.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    for path in (
        DB_PATH,
        REGISTRATION_PATH,
        TASK_XML_PATH,
        RUN_RESULT_PATH,
        STATUS_BEFORE_STOP_PATH,
        STOP_RESULT_PATH,
        PROCESS_EVIDENCE_PATH,
        HEALTH_TRACE_PATH,
        HOST_RUNTIME_SUMMARY_PATH,
        LAUNCHER_STDOUT_PATH,
        LAUNCHER_STDERR_PATH,
        COLLECTOR_RUNS_PATH,
        LIVE_STATE_PATH,
        VOD_ROWS_PATH,
        NOTES_PATH,
    ):
        if path.exists():
            path.unlink()

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

    cleanup_previous(env)

    app_port = find_free_port()
    fixture_port = find_free_port()
    base_url = f"http://127.0.0.1:{app_port}"
    fixture_server = ThreadingHTTPServer(("127.0.0.1", fixture_port), FixtureHandler)
    fixture_thread = threading.Thread(target=fixture_server.serve_forever, daemon=True, name="task018-fixture-server")
    fixture_thread.start()

    install_result = run_powershell(
        INSTALL_PS1,
        [
            "-TaskName",
            TASK_NAME,
            "-RuntimeDir",
            str(RUNTIME_DIR),
            "-DbPath",
            str(DB_PATH),
            "-Port",
            str(app_port),
            "-HealthTimeout",
            "15",
        ],
        env,
    )
    if install_result["returncode"] != 0:
        raise RuntimeError(f"task registration failed: {install_result}")
    registration_payload = json.loads(install_result["stdout"])
    write_json(REGISTRATION_PATH, registration_payload)

    export_result = run_command(
        ["schtasks", "/query", "/tn", TASK_NAME, "/xml"],
        cwd=ROOT_DIR,
        env=env,
    )
    if export_result["returncode"] != 0:
        raise RuntimeError(f"task export failed: {export_result}")
    TASK_XML_PATH.write_text(export_result["stdout"], encoding="utf-8")

    run_result = run_powershell(
        RUN_PS1,
        [
            "-TaskName",
            TASK_NAME,
            "-RuntimeDir",
            str(RUNTIME_DIR),
            "-DbPath",
            str(DB_PATH),
            "-Port",
            str(app_port),
            "-TimeoutSeconds",
            "20",
        ],
        env,
    )
    if run_result["returncode"] != 0:
        raise RuntimeError(f"scheduled task start failed: {run_result}")
    run_payload = json.loads(run_result["stdout"])
    write_json(RUN_RESULT_PATH, run_payload)

    created = http_json(
        f"{base_url}/api/streamers",
        method="POST",
        payload={
            "soop_user_id": "task_scheduler_streamer",
            "nickname": "Task Scheduler Stream",
            "channel_url": f"http://127.0.0.1:{fixture_port}/station/task_scheduler_streamer",
            "replay_url": f"http://127.0.0.1:{fixture_port}/replay/task_scheduler_streamer",
            "category_no": "",
            "active": True,
        },
    )
    streamer_id = int(created["item"]["id"])
    health_trace = wait_for_scheduler(base_url, streamer_id, timeout_seconds=15)
    write_json(HEALTH_TRACE_PATH, health_trace)

    status_result = run_powershell(
        STATUS_PS1,
        [
            "-TaskName",
            TASK_NAME,
            "-RuntimeDir",
            str(RUNTIME_DIR),
            "-DbPath",
            str(DB_PATH),
        ],
        env,
    )
    if status_result["returncode"] != 0:
        raise RuntimeError(f"scheduled task status failed: {status_result}")
    status_payload = json.loads(status_result["stdout"])
    write_json(STATUS_BEFORE_STOP_PATH, status_payload)

    stop_started = time.time()
    stop_result = run_powershell(
        STOP_PS1,
        [
            "-TaskName",
            TASK_NAME,
            "-RuntimeDir",
            str(RUNTIME_DIR),
            "-DbPath",
            str(DB_PATH),
            "-TimeoutSeconds",
            "10",
        ],
        env,
    )
    stop_finished = time.time()
    if stop_result["returncode"] != 0:
        raise RuntimeError(f"scheduled task stop failed: {stop_result}")
    stop_payload = json.loads(stop_result["stdout"])
    stop_payload["stop_duration_seconds"] = round(stop_finished - stop_started, 3)
    write_json(STOP_RESULT_PATH, stop_payload)

    remove_result = run_powershell(REMOVE_PS1, ["-TaskName", TASK_NAME], env)
    if remove_result["returncode"] != 0:
        raise RuntimeError(f"scheduled task cleanup failed: {remove_result}")

    fixture_server.shutdown()
    fixture_server.server_close()
    fixture_thread.join(timeout=1)

    runtime_summary = stop_payload["stop"].get("host_runtime_summary") or {}
    write_json(HOST_RUNTIME_SUMMARY_PATH, runtime_summary)
    stdout_runtime_path = Path(stop_payload["stop"]["host_runtime_summary"]["runtime_dir"]) / "launcher_stdout.log"
    stderr_runtime_path = Path(stop_payload["stop"]["host_runtime_summary"]["runtime_dir"]) / "launcher_stderr.log"
    if stdout_runtime_path.exists():
        LAUNCHER_STDOUT_PATH.write_text(stdout_runtime_path.read_text(encoding="utf-8"), encoding="utf-8")
    if stderr_runtime_path.exists():
        LAUNCHER_STDERR_PATH.write_text(stderr_runtime_path.read_text(encoding="utf-8"), encoding="utf-8")
    collector_runs = select_rows("SELECT * FROM collector_runs ORDER BY id ASC")
    live_state_rows = select_rows("SELECT * FROM streamer_live_state ORDER BY streamer_id ASC")
    vod_rows = select_rows("SELECT * FROM vods ORDER BY id ASC")

    process_evidence = {
        "supervisor_pattern": "windows_task_scheduler",
        "task_registration": {
            "task_name": TASK_NAME,
            "registration_path": str(REGISTRATION_PATH),
            "task_definition_path": str(TASK_XML_PATH),
            "task_state_before_stop": status_payload["task"]["State"],
            "last_task_result_before_stop": status_payload["task"]["LastTaskResult"],
        },
        "packaged_start": {
            "status": run_payload["status"],
            "launcher_status": run_payload["launcher_status"]["status"],
            "launcher_process_alive": run_payload["launcher_status"]["process_alive"],
        },
        "bounded_stop": {
            "stop_status": stop_payload["stop"]["status"],
            "stop_duration_seconds": stop_payload["stop_duration_seconds"],
            "scheduler_thread_alive_after_exit": runtime_summary["scheduler_state_after_exit"]["thread_alive"],
            "scheduler_started_after_exit": runtime_summary["scheduler_state_after_exit"]["started"],
            "stop_request_seen": runtime_summary["stop_request_seen"]["requested"],
            "exit_kind": runtime_summary["exit_kind"],
        },
        "durable_persistence": {
            "collector_runs": len(collector_runs),
            "live_state_rows": len(live_state_rows),
            "vod_rows": len(vod_rows),
        },
        "deployment_stop_contract": {
            "stop_wrapper": str(STOP_PS1),
            "notes": "Do not use End-ScheduledTask for normal shutdown. Use the task stop wrapper so the host sees stop_requested.json and exits cleanly.",
        },
    }
    write_json(PROCESS_EVIDENCE_PATH, process_evidence)
    write_json(COLLECTOR_RUNS_PATH, collector_runs)
    write_json(LIVE_STATE_PATH, live_state_rows)
    write_json(VOD_ROWS_PATH, vod_rows)

    RUNBOOK_PATH.write_text(
        "\n".join(
            [
                "# TASK-018 Windows Task Scheduler Packaging Runbook",
                "",
                "## Scope",
                "",
                "This runbook covers one supervisor-specific packaging path for the reviewed live/VOD launcher: Windows Task Scheduler.",
                "",
                "## Repo-Owned Packaging Assets",
                "",
                "- `live_vod_scheduler_task_action.ps1`",
                "- `install_live_vod_scheduler_task.ps1`",
                "- `run_live_vod_scheduler_task.ps1`",
                "- `status_live_vod_scheduler_task.ps1`",
                "- `stop_live_vod_scheduler_task.ps1`",
                "- `remove_live_vod_scheduler_task.ps1`",
                "",
                "## Register The Task",
                "",
                "```powershell",
                ".\\install_live_vod_scheduler_task.ps1",
                "```",
                "",
                "Optional arguments:",
                "",
                "- `-TaskName <name>`",
                "- `-RuntimeDir <path>`",
                "- `-DbPath <path>`",
                "- `-Port <port>`",
                "- `-HealthTimeout <seconds>`",
                "",
                "## Start Through The Supervisor Path",
                "",
                "```powershell",
                ".\\run_live_vod_scheduler_task.ps1",
                "```",
                "",
                "This starts the registered Task Scheduler entry on demand and waits for the repo-owned launcher health path.",
                "",
                "## Inspect Runtime Health",
                "",
                "```powershell",
                ".\\status_live_vod_scheduler_task.ps1",
                "```",
                "",
                "This returns both scheduled-task metadata and launcher `/api/health` status for the configured runtime directory.",
                "",
                "## Deployment-Facing Graceful Stop Contract",
                "",
                "```powershell",
                ".\\stop_live_vod_scheduler_task.ps1 -TimeoutSeconds 10",
                "```",
                "",
                "- Do not use `End-ScheduledTask` for normal shutdown because it bypasses the host-side graceful stop path.",
                "- The task stop wrapper delegates to the repo-owned launcher stop contract, which writes `stop_requested.json` inside the task runtime directory.",
                "- The host wrapper observes that stop file and returns cleanly after joining the scheduler thread.",
                "",
                "## Cleanup",
                "",
                "```powershell",
                ".\\remove_live_vod_scheduler_task.ps1",
                "```",
                "",
                "## Verified Local Evidence",
                "",
                "- the Task Scheduler path registered a named task and exported its task definition",
                "- the packaged path started the app and reached `/api/health`",
                "- the deployment-facing stop wrapper stopped the host in a bounded way without using forced task termination",
                "- collector runs, live state, and VOD rows were still persisted through the packaged path",
                "",
                "## Remaining Deployment Gaps",
                "",
                "- this slice proves one Windows Task Scheduler pattern only; NSSM or Windows Service packaging can be a later ops slice if needed",
                "- the verified task principal is current-user interactive-token based, so service-account or machine-start semantics remain later deployment-specific work",
                "- non-Windows supervisor packaging remains out of scope",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    NOTES_PATH.write_text(
        "\n".join(
            [
                "TASK-018 Windows Task Scheduler packaging verification",
                "",
                f"task name: {TASK_NAME}",
                f"app port: {app_port}",
                f"fixture port: {fixture_port}",
                f"collector runs recorded: {len(collector_runs)}",
                f"live state rows recorded: {len(live_state_rows)}",
                f"vod rows recorded: {len(vod_rows)}",
                "",
                "Bounded stop evidence:",
                f"- stop status: {stop_payload['stop']['status']}",
                f"- stop duration seconds: {stop_payload['stop_duration_seconds']}",
                f"- exit kind: {runtime_summary['exit_kind']}",
                f"- scheduler thread alive after exit: {runtime_summary['scheduler_state_after_exit']['thread_alive']}",
                f"- scheduler started after exit: {runtime_summary['scheduler_state_after_exit']['started']}",
                f"- stop request seen by host: {runtime_summary['stop_request_seen']['requested']}",
                "",
                "Stop contract notes:",
                "- use the task stop wrapper, not End-ScheduledTask, for normal shutdown",
                "- the supervisor owns task registration and on-demand start",
                "- the repo-owned stop file remains the graceful stop boundary for the host wrapper",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
