import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib import error, request


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_RUNTIME_DIR = BASE_DIR / "data" / "live_vod_scheduler_runtime"
HOST_SCRIPT = BASE_DIR / "live_vod_scheduler_host.py"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8877


def now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def state_path(runtime_dir: Path) -> Path:
    return runtime_dir / "launcher_state.json"


def stop_file_path(runtime_dir: Path) -> Path:
    return runtime_dir / "stop_requested.json"


def host_summary_path(runtime_dir: Path) -> Path:
    return runtime_dir / "host_runtime_summary.json"


def stdout_log_path(runtime_dir: Path) -> Path:
    return runtime_dir / "launcher_stdout.log"


def stderr_log_path(runtime_dir: Path) -> Path:
    return runtime_dir / "launcher_stderr.log"


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        stdout = completed.stdout or ""
        return str(pid) in stdout and "No tasks are running" not in stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def http_json(url: str) -> dict:
    req = request.Request(url, method="GET")
    with request.urlopen(req, timeout=5) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset))


def wait_for_health(health_url: str, timeout_seconds: float) -> dict:
    deadline = time.time() + timeout_seconds
    last_error = None
    while time.time() < deadline:
        try:
            return http_json(health_url)
        except Exception as exc:  # pragma: no cover - runtime polling
            last_error = repr(exc)
            time.sleep(0.2)
    raise RuntimeError(f"launcher health wait timed out: {last_error}")


def resolve_runtime_dir(value: str | None) -> Path:
    if value:
        return Path(value).resolve()
    return DEFAULT_RUNTIME_DIR.resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Repo-owned launcher for app_live_vod.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start")
    start.add_argument("--runtime-dir", default=None)
    start.add_argument("--host", default=DEFAULT_HOST)
    start.add_argument("--port", type=int, default=DEFAULT_PORT)
    start.add_argument("--db-path", default=None)
    start.add_argument("--wait-health", action="store_true")
    start.add_argument("--health-timeout", type=float, default=15.0)

    status = subparsers.add_parser("status")
    status.add_argument("--runtime-dir", default=None)

    stop = subparsers.add_parser("stop")
    stop.add_argument("--runtime-dir", default=None)
    stop.add_argument("--timeout", type=float, default=10.0)

    return parser


def command_start(args: argparse.Namespace) -> int:
    runtime_dir = resolve_runtime_dir(args.runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_path(runtime_dir)
    existing = load_json(state_file)
    if existing and pid_alive(int(existing.get("pid", 0))):
        print(json.dumps({"status": "already_running", "state": existing}, ensure_ascii=False, indent=2))
        return 1

    stop_file = stop_file_path(runtime_dir)
    summary_file = host_summary_path(runtime_dir)
    for path in (stop_file, summary_file, stdout_log_path(runtime_dir), stderr_log_path(runtime_dir)):
        if path.exists():
            path.unlink()

    env = os.environ.copy()
    env["SOOP_LIVE_VOD_RUNTIME_DIR"] = str(runtime_dir)
    env["SOOP_LIVE_VOD_HOST"] = str(args.host)
    env["SOOP_LIVE_VOD_PORT"] = str(args.port)
    if args.db_path:
        env["SOOP_LIVE_VOD_DB_PATH"] = str(Path(args.db_path).resolve())

    creationflags = 0
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags |= subprocess.CREATE_NO_WINDOW

    with stdout_log_path(runtime_dir).open("w", encoding="utf-8") as stdout_handle, stderr_log_path(runtime_dir).open(
        "w", encoding="utf-8"
    ) as stderr_handle:
        process = subprocess.Popen(
            [sys.executable, str(HOST_SCRIPT)],
            cwd=str(BASE_DIR),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=stdout_handle,
            stderr=stderr_handle,
            creationflags=creationflags,
        )

    state = {
        "pid": process.pid,
        "runtime_dir": str(runtime_dir),
        "host": args.host,
        "port": args.port,
        "health_url": f"http://{args.host}:{args.port}/api/health",
        "db_path": str(Path(args.db_path).resolve()) if args.db_path else None,
        "started_at": now_iso(),
        "stop_file": str(stop_file),
        "host_runtime_summary": str(summary_file),
        "stdout_log": str(stdout_log_path(runtime_dir)),
        "stderr_log": str(stderr_log_path(runtime_dir)),
    }
    write_json(state_file, state)

    if args.wait_health:
        state["health"] = wait_for_health(state["health_url"], args.health_timeout)
        write_json(state_file, state)

    print(json.dumps({"status": "started", "state": state}, ensure_ascii=False, indent=2))
    return 0


def command_status(args: argparse.Namespace) -> int:
    runtime_dir = resolve_runtime_dir(args.runtime_dir)
    state = load_json(state_path(runtime_dir))
    if not state:
        print(json.dumps({"status": "not_started", "runtime_dir": str(runtime_dir)}, ensure_ascii=False, indent=2))
        return 1
    pid = int(state.get("pid", 0))
    process_alive = pid_alive(pid)
    payload = {
        "status": "running" if process_alive else "stopped",
        "state": state,
        "process_alive": process_alive,
        "host_runtime_summary": load_json(host_summary_path(runtime_dir)),
    }
    if process_alive:
        try:
            payload["health"] = http_json(state["health_url"])
        except Exception as exc:  # pragma: no cover - runtime polling
            payload["health_error"] = repr(exc)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if process_alive else 1


def command_stop(args: argparse.Namespace) -> int:
    runtime_dir = resolve_runtime_dir(args.runtime_dir)
    state = load_json(state_path(runtime_dir))
    if not state:
        print(json.dumps({"status": "not_started", "runtime_dir": str(runtime_dir)}, ensure_ascii=False, indent=2))
        return 1

    pid = int(state.get("pid", 0))
    stop_file = stop_file_path(runtime_dir)
    stop_payload = {
        "requested_at": now_iso(),
        "requested_by": "live_vod_scheduler_launcher.py",
        "pid": pid,
    }
    write_json(stop_file, stop_payload)

    deadline = time.time() + max(0.1, args.timeout)
    while time.time() < deadline:
        if not pid_alive(pid):
            result = {
                "status": "stopped",
                "pid": pid,
                "stop_payload": stop_payload,
                "host_runtime_summary": load_json(host_summary_path(runtime_dir)),
            }
            try:
                state_path(runtime_dir).unlink()
            except OSError:
                pass
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        time.sleep(0.2)

    result = {
        "status": "stop_timeout",
        "pid": pid,
        "stop_payload": stop_payload,
        "host_runtime_summary": load_json(host_summary_path(runtime_dir)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "start":
        return command_start(args)
    if args.command == "status":
        return command_status(args)
    if args.command == "stop":
        return command_stop(args)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
