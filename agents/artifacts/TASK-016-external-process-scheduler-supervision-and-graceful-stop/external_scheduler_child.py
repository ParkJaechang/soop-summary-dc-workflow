import json
import os
import signal
import sys
import threading
import time
from pathlib import Path

import uvicorn


ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app_live_vod as live


ARTIFACT_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ["TASK016_DB_PATH"])
PORT = int(os.environ["TASK016_PORT"])
FETCH_LOG_PATH = Path(os.environ["TASK016_CHILD_FETCH_LOG"])
RUNTIME_SUMMARY_PATH = Path(os.environ["TASK016_CHILD_RUNTIME_SUMMARY"])

STATION_HTML = """
<html>
  <head><title>External Scheduler Stream | SOOP</title></head>
  <body>
    <div class="Badge-module__live">LIVE</div>
    <div class="player_area">on-air</div>
  </body>
</html>
""".strip()

REPLAY_HTML = """
<html>
  <head><title>External Scheduler Stream | SOOP</title></head>
  <body>
    <a href="https://vod.sooplive.co.kr/player/99001">
      <img src="https://img.test/99001.jpg" />
      <p class="Title-module__title">External Process VOD One</p>
      <div class="Badge-module__vodTime"><div>10:10</div></div>
      <div class="ThumbnailMoreInfo-module__md">views</div>
      <div class="ThumbnailMoreInfo-module__md">2026-04-08T12:00:00+09:00</div>
    </a>
    <a href="https://vod.sooplive.co.kr/player/99002">
      <img src="https://img.test/99002.jpg" />
      <p class="Title-module__title">External Process VOD Two</p>
      <div class="Badge-module__vodTime"><div>05:05</div></div>
      <div class="ThumbnailMoreInfo-module__md">views</div>
      <div class="ThumbnailMoreInfo-module__md">2026-04-08T11:40:00+09:00</div>
    </a>
  </body>
</html>
""".strip()


fetch_lock = threading.Lock()
fetch_trace: list[dict[str, object]] = []
fetch_counts = {
    "station": 0,
    "replay": 0,
}
shutdown_signals: list[dict[str, object]] = []


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


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
        raise AssertionError(f"unexpected URL in TASK-016 child: {url}")

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


def configure_runtime() -> None:
    live.DB_PATH = DB_PATH
    live.SOOP_CLIENT_ID = ""
    live.USE_BROWSER_FALLBACK = False
    live.LIVE_REFRESH_SECONDS = 0.35
    live.VOD_REFRESH_SECONDS = 0.45
    live.SCHEDULER_TICK_SECONDS = 0.05
    live.SCHEDULER_STARTUP_LIVE_DELAY_SECONDS = 0.18
    live.SCHEDULER_STARTUP_VOD_DELAY_SECONDS = 0.22
    live.SCHEDULER_STOP_JOIN_SECONDS = 1.0
    live.fetch_text = fake_fetch_text


def serialize_fetch_trace() -> list[dict[str, object]]:
    with fetch_lock:
        if not fetch_trace:
            return []
        first_called_at = fetch_trace[0]["called_at"]
        return [
            {
                **item,
                "offset_seconds": round(float(item["called_at"]) - float(first_called_at), 3),
            }
            for item in fetch_trace
        ]


def main() -> None:
    configure_runtime()
    config = uvicorn.Config(live.app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None

    started_at = live.now_iso()
    exit_kind = "clean_return"
    runtime_error = None

    def request_shutdown(sig: int, _frame: object) -> None:
        shutdown_signals.append(
            {
                "signal": int(sig),
                "received_at": live.now_iso(),
            }
        )
        server.should_exit = True

    for sig in (signal.SIGINT, signal.SIGTERM, getattr(signal, "SIGBREAK", None)):
        if sig is not None:
            signal.signal(sig, request_shutdown)

    try:
        server.run()
    except KeyboardInterrupt:
        exit_kind = "keyboard_interrupt"
    except BaseException as exc:  # pragma: no cover - artifact harness
        exit_kind = "exception"
        runtime_error = repr(exc)
        raise
    finally:
        write_json(FETCH_LOG_PATH, serialize_fetch_trace())
        write_json(
            RUNTIME_SUMMARY_PATH,
            {
                "started_at": started_at,
                "finished_at": live.now_iso(),
                "port": PORT,
                "db_path": str(DB_PATH),
                "exit_kind": exit_kind,
                "runtime_error": runtime_error,
                "fetch_counts": dict(fetch_counts),
                "shutdown_signals": shutdown_signals,
                "scheduler_state_after_exit": live.get_scheduler_state_snapshot(),
            },
        )


if __name__ == "__main__":
    main()
