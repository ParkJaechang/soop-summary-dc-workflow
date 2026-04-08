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
INSTALL_PS1 = ROOT_DIR / "install_live_vod_scheduler_task_noninteractive.ps1"
RUN_PS1 = ROOT_DIR / "run_live_vod_scheduler_task.ps1"
STATUS_PS1 = ROOT_DIR / "status_live_vod_scheduler_task.ps1"
STOP_PS1 = ROOT_DIR / "stop_live_vod_scheduler_task.ps1"
REMOVE_PS1 = ROOT_DIR / "remove_live_vod_scheduler_task.ps1"

TASK_NAME = "SOOP-LiveVOD-Task019"
RUNTIME_DIR = ROOT_DIR / "data" / "t019rt"
DB_PATH = ROOT_DIR / "data" / "t019.db"
TASK_XML_PATH = ARTIFACT_DIR / "noninteractive_task_scheduler_task_definition.xml"
REGISTRATION_MANIFEST_PATH = ARTIFACT_DIR / "noninteractive_task_scheduler_registration_manifest.json"
INSTALL_RESULT_PATH = ARTIFACT_DIR / "noninteractive_task_scheduler_install_result.json"
PROCESS_EVIDENCE_PATH = ARTIFACT_DIR / "noninteractive_task_scheduler_process_evidence.json"
BLOCKER_SUMMARY_PATH = ARTIFACT_DIR / "noninteractive_task_scheduler_blocker_summary.json"
PERMISSION_PROBE_PATH = ARTIFACT_DIR / "noninteractive_task_scheduler_permission_probe.txt"
RUNBOOK_PATH = ARTIFACT_DIR / "noninteractive_task_scheduler_runbook.md"
NOTES_PATH = ARTIFACT_DIR / "noninteractive_task_scheduler_notes.txt"
RUN_RESULT_PATH = ARTIFACT_DIR / "noninteractive_task_scheduler_run_result.json"
STATUS_BEFORE_STOP_PATH = ARTIFACT_DIR / "noninteractive_task_scheduler_status_before_stop.json"
STOP_RESULT_PATH = ARTIFACT_DIR / "noninteractive_task_scheduler_stop_result.json"
HOST_RUNTIME_SUMMARY_PATH = ARTIFACT_DIR / "noninteractive_task_scheduler_host_runtime_summary.json"
HEALTH_TRACE_PATH = ARTIFACT_DIR / "noninteractive_task_scheduler_health_trace.json"
COLLECTOR_RUNS_PATH = ARTIFACT_DIR / "collector_runs_after_noninteractive_task_scheduler.json"
LIVE_STATE_PATH = ARTIFACT_DIR / "live_state_after_noninteractive_task_scheduler.json"
VOD_ROWS_PATH = ARTIFACT_DIR / "vod_rows_after_noninteractive_task_scheduler.json"
LAUNCHER_STDOUT_PATH = ARTIFACT_DIR / "noninteractive_task_scheduler_launcher_stdout.log"
LAUNCHER_STDERR_PATH = ARTIFACT_DIR / "noninteractive_task_scheduler_launcher_stderr.log"


STATION_HTML = """
<html>
  <head><title>Task Scheduler S4U Stream | SOOP</title></head>
  <body>
    <div class="Badge-module__live">LIVE</div>
    <div class="player_area">on-air</div>
  </body>
</html>
""".strip()

REPLAY_HTML = """
<html>
  <head><title>Task Scheduler S4U Stream | SOOP</title></head>
  <body>
    <a href="https://vod.sooplive.co.kr/player/99301">
      <img src="https://img.test/99301.jpg" />
      <p class="Title-module__title">Task Scheduler S4U VOD One</p>
      <div class="Badge-module__vodTime"><div>06:16</div></div>
      <div class="ThumbnailMoreInfo-module__md">views</div>
      <div class="ThumbnailMoreInfo-module__md">2026-04-08T15:00:00+09:00</div>
    </a>
    <a href="https://vod.sooplive.co.kr/player/99302">
      <img src="https://img.test/99302.jpg" />
      <p class="Title-module__title">Task Scheduler S4U VOD Two</p>
      <div class="Badge-module__vodTime"><div>02:28</div></div>
      <div class="ThumbnailMoreInfo-module__md">views</div>
      <div class="ThumbnailMoreInfo-module__md">2026-04-08T14:30:00+09:00</div>
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


def run_command(command: list[str], cwd: Path, env: dict[str, str] | None = None, timeout: int = 60) -> dict:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
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
    raise RuntimeError("non-interactive task scheduler path did not reach bounded scheduler activity before timeout")


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


def write_runbook(blocked: bool) -> None:
    lines = [
        "# TASK-019 Non-Interactive Task Scheduler Runbook",
        "",
        "## Scope",
        "",
        "This runbook covers one non-interactive Task Scheduler packaging path for the reviewed live/VOD launcher: current-user S4U XML registration.",
        "",
        "## Packaging Asset",
        "",
        "- `install_live_vod_scheduler_task_noninteractive.ps1`",
        "- existing repo-owned task wrappers: `run_live_vod_scheduler_task.ps1`, `status_live_vod_scheduler_task.ps1`, `stop_live_vod_scheduler_task.ps1`, `remove_live_vod_scheduler_task.ps1`",
        "",
        "## Register The Non-Interactive Task",
        "",
        "```powershell",
        ".\\install_live_vod_scheduler_task_noninteractive.ps1",
        "```",
        "",
        "Optional arguments:",
        "",
        "- `-TaskName <name>`",
        "- `-TaskUser <DOMAIN\\user>`",
        "- `-RuntimeDir <path>`",
        "- `-DbPath <path>`",
        "- `-Port <port>`",
        "- `-HealthTimeout <seconds>`",
        "- `-TaskXmlPath <path>`",
        "",
        "## Start, Status, And Graceful Stop",
        "",
        "```powershell",
        ".\\run_live_vod_scheduler_task.ps1 -TaskName <name> -RuntimeDir <path> -DbPath <path>",
        ".\\status_live_vod_scheduler_task.ps1 -TaskName <name> -RuntimeDir <path> -DbPath <path>",
        ".\\stop_live_vod_scheduler_task.ps1 -TaskName <name> -RuntimeDir <path> -DbPath <path> -TimeoutSeconds 10",
        "```",
        "",
        "- Keep using the repo-owned stop wrapper for normal shutdown.",
        "- Do not use `End-ScheduledTask` for normal shutdown because it bypasses the launcher stop-request-file contract.",
        "",
        "## Packaging Mode",
        "",
        "- registration mode: `xml_s4u_current_user_noninteractive`",
        "- Task Scheduler logon type: `S4U`",
        "- intended shape: no interactive desktop dependency and no stored password in the repo-owned packaging asset",
        "",
        "## Local Verification Notes",
    ]
    if blocked:
        lines.extend(
            [
                "",
                "- local verification in this medium-integrity session hit `Access is denied` during S4U task registration",
                "- the packaging asset and task XML were still generated and saved as evidence",
                "- a deployment context with elevated Task Scheduler rights or an approved credentialed supervisor is required to finish the start/health/stop proof for this mode",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "- local verification completed the registration, packaged start, health check, and bounded graceful stop flow",
            ]
        )
    lines.extend(
        [
            "",
            "## Remaining Deployment Gaps",
            "",
            "- if S4U registration remains blocked in the target environment, the next deployment-shaped alternative is an approved service account or elevated supervisor-owned task registration process",
            "- alternate supervisors outside Task Scheduler remain out of scope",
        ]
    )
    RUNBOOK_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    for path in (
        TASK_XML_PATH,
        REGISTRATION_MANIFEST_PATH,
        INSTALL_RESULT_PATH,
        PROCESS_EVIDENCE_PATH,
        BLOCKER_SUMMARY_PATH,
        PERMISSION_PROBE_PATH,
        NOTES_PATH,
        RUN_RESULT_PATH,
        STATUS_BEFORE_STOP_PATH,
        STOP_RESULT_PATH,
        HOST_RUNTIME_SUMMARY_PATH,
        HEALTH_TRACE_PATH,
        COLLECTOR_RUNS_PATH,
        LIVE_STATE_PATH,
        VOD_ROWS_PATH,
        LAUNCHER_STDOUT_PATH,
        LAUNCHER_STDERR_PATH,
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

    whoami = run_command(["whoami", "/all"], ROOT_DIR, env=env, timeout=30)
    PERMISSION_PROBE_PATH.write_text((whoami["stdout"] or "") + (whoami["stderr"] or ""), encoding="utf-8")

    app_port = find_free_port()
    fixture_port = find_free_port()
    base_url = f"http://127.0.0.1:{app_port}"
    fixture_server = ThreadingHTTPServer(("127.0.0.1", fixture_port), FixtureHandler)
    fixture_thread = threading.Thread(target=fixture_server.serve_forever, daemon=True, name="task019-fixture-server")
    fixture_thread.start()

    install_result = run_powershell(
        INSTALL_PS1,
        [
            "-TaskName",
            TASK_NAME,
            "-TaskUser",
            "DESKTOP-PJC\\PJC",
            "-RuntimeDir",
            str(RUNTIME_DIR),
            "-DbPath",
            str(DB_PATH),
            "-Port",
            str(app_port),
            "-HealthTimeout",
            "15",
            "-TaskXmlPath",
            str(TASK_XML_PATH),
        ],
        env,
    )

    install_payload = None
    if install_result["stdout"]:
        try:
            install_payload = json.loads(install_result["stdout"])
        except json.JSONDecodeError:
            install_payload = {
                "status": "unparsed_stdout",
                "raw_stdout": install_result["stdout"],
            }
    write_json(
        INSTALL_RESULT_PATH,
        {
            "command": install_result["command"],
            "returncode": install_result["returncode"],
            "stdout": install_result["stdout"],
            "stderr": install_result["stderr"],
            "payload": install_payload,
        },
    )
    if install_payload and isinstance(install_payload, dict):
        manifest_path = install_payload.get("manifest_path")
        if manifest_path and Path(manifest_path).exists():
            REGISTRATION_MANIFEST_PATH.write_text(Path(manifest_path).read_text(encoding="utf-8"), encoding="utf-8")

    if install_result["returncode"] != 0:
        blocker = {
            "status": "blocked",
            "supervisor_pattern": "windows_task_scheduler_s4u_noninteractive",
            "blocking_stage": "registration",
            "registration_returncode": install_result["returncode"],
            "registration_output": (install_payload or {}).get("create_result") or install_result["stderr"] or install_result["stdout"],
            "task_xml_path": str(TASK_XML_PATH),
            "required_dependency": "elevated Task Scheduler registration rights or an approved credentialed deployment context for S4U/non-interactive registration",
            "observed_user": "DESKTOP-PJC\\PJC",
            "observed_privilege_summary": "whoami /all shows medium-integrity interactive session without enabled administrative privileges",
            "stop_contract": {
                "wrapper": str(STOP_PS1),
                "notes": "If registration succeeds in deployment, graceful stop should still use the repo-owned stop wrapper rather than End-ScheduledTask."
            },
        }
        write_json(BLOCKER_SUMMARY_PATH, blocker)
        write_json(
            PROCESS_EVIDENCE_PATH,
            {
                "status": "blocked",
                "supervisor_pattern": "windows_task_scheduler_s4u_noninteractive",
                "install_result_path": str(INSTALL_RESULT_PATH),
                "task_xml_path": str(TASK_XML_PATH),
                "permission_probe_path": str(PERMISSION_PROBE_PATH),
                "blocker_summary_path": str(BLOCKER_SUMMARY_PATH),
                "notes": "The non-interactive S4U packaging asset was generated, but local registration was denied before start/health/stop proof could run.",
            },
        )
        write_runbook(blocked=True)
        NOTES_PATH.write_text(
            "\n".join(
                [
                    "TASK-019 non-interactive Task Scheduler verification",
                    "",
                    "Result: blocked at S4U registration",
                    f"task name: {TASK_NAME}",
                    "observed user: DESKTOP-PJC\\PJC",
                    f"registration return code: {install_result['returncode']}",
                    f"registration stderr: {install_result['stderr'].strip()}",
                    "",
                    "Next requirement:",
                    "- run the same installer in a deployment context that has permission to register non-interactive or service-account Task Scheduler entries",
                    "- then reuse the existing run/status/stop task wrappers to complete start, health, and graceful-stop proof",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        fixture_server.shutdown()
        fixture_server.server_close()
        fixture_thread.join(timeout=1)
        return

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
        raise RuntimeError(f"non-interactive task scheduler start failed: {run_result}")
    run_payload = json.loads(run_result["stdout"])
    write_json(RUN_RESULT_PATH, run_payload)

    created = http_json(
        f"{base_url}/api/streamers",
        method="POST",
        payload={
            "soop_user_id": "task_scheduler_s4u_streamer",
            "nickname": "Task Scheduler S4U Stream",
            "channel_url": f"http://127.0.0.1:{fixture_port}/station/task_scheduler_s4u_streamer",
            "replay_url": f"http://127.0.0.1:{fixture_port}/replay/task_scheduler_s4u_streamer",
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
        raise RuntimeError(f"non-interactive task scheduler status failed: {status_result}")
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
        raise RuntimeError(f"non-interactive task scheduler stop failed: {stop_result}")
    stop_payload = json.loads(stop_result["stdout"])
    stop_payload["stop_duration_seconds"] = round(stop_finished - stop_started, 3)
    write_json(STOP_RESULT_PATH, stop_payload)

    remove_result = run_powershell(REMOVE_PS1, ["-TaskName", TASK_NAME], env)
    if remove_result["returncode"] != 0:
        raise RuntimeError(f"non-interactive task scheduler cleanup failed: {remove_result}")

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
    write_json(COLLECTOR_RUNS_PATH, collector_runs)
    write_json(LIVE_STATE_PATH, live_state_rows)
    write_json(VOD_ROWS_PATH, vod_rows)

    write_json(
        PROCESS_EVIDENCE_PATH,
        {
            "status": "verified",
            "supervisor_pattern": "windows_task_scheduler_s4u_noninteractive",
            "packaged_start": {
                "status": run_payload["status"],
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
        },
    )
    write_runbook(blocked=False)
    NOTES_PATH.write_text("TASK-019 non-interactive Task Scheduler verification completed successfully.\n", encoding="utf-8")


if __name__ == "__main__":
    main()
