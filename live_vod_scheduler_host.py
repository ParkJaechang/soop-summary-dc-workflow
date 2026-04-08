import json
import os
import threading
import time
from pathlib import Path

import uvicorn

import app_live_vod as live


BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = Path(os.getenv("SOOP_LIVE_VOD_RUNTIME_DIR", str(BASE_DIR / "data" / "live_vod_scheduler_runtime")))
DB_OVERRIDE = os.getenv("SOOP_LIVE_VOD_DB_PATH", "").strip()
HOST = os.getenv("SOOP_LIVE_VOD_HOST", "127.0.0.1").strip() or "127.0.0.1"
PORT = int(os.getenv("SOOP_LIVE_VOD_PORT", "8877"))
STOP_FILE = RUNTIME_DIR / "stop_requested.json"
RUNTIME_SUMMARY_PATH = RUNTIME_DIR / "host_runtime_summary.json"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def stop_watcher(server: uvicorn.Server, stop_seen: dict[str, object]) -> None:
    while not server.should_exit:
        if STOP_FILE.exists():
            stop_seen["requested"] = True
            stop_seen["requested_at"] = live.now_iso()
            try:
                payload = json.loads(STOP_FILE.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            stop_seen["payload"] = payload
            server.should_exit = True
            break
        time.sleep(0.1)


def main() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    if DB_OVERRIDE:
        live.DB_PATH = Path(DB_OVERRIDE)

    config = uvicorn.Config(live.app, host=HOST, port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None

    stop_seen: dict[str, object] = {
        "requested": False,
        "requested_at": None,
        "payload": None,
    }
    watcher = threading.Thread(target=stop_watcher, args=(server, stop_seen), daemon=True, name="live-vod-stop-watcher")
    watcher.start()

    started_at = live.now_iso()
    exit_kind = "clean_return"
    runtime_error = None
    try:
        server.run()
    except KeyboardInterrupt:
        exit_kind = "keyboard_interrupt"
    except BaseException as exc:  # pragma: no cover - launcher artifact
        exit_kind = "exception"
        runtime_error = repr(exc)
        raise
    finally:
        watcher.join(timeout=0.2)
        write_json(
            RUNTIME_SUMMARY_PATH,
            {
                "started_at": started_at,
                "finished_at": live.now_iso(),
                "runtime_dir": str(RUNTIME_DIR),
                "db_path": str(live.DB_PATH),
                "host": HOST,
                "port": PORT,
                "exit_kind": exit_kind,
                "runtime_error": runtime_error,
                "stop_request_seen": stop_seen,
                "scheduler_state_after_exit": live.get_scheduler_state_snapshot(),
            },
        )


if __name__ == "__main__":
    main()
