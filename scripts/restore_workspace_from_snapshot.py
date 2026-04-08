from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    snapshot_path = repo_root / "exports" / "soop-summary-dc-workflow-snapshot.json"

    if not snapshot_path.exists():
        raise SystemExit(f"Snapshot not found: {snapshot_path}")

    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    files = snapshot.get("files", [])

    restored = 0
    for item in files:
        rel_path = Path(item["path"])
        target = repo_root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item["content"], encoding="utf-8", newline="")
        restored += 1

    print(f"Restored {restored} files from {snapshot_path.name}")
    print("Open this folder in VSCode and start with agents/board/progress.md")


if __name__ == "__main__":
    main()
