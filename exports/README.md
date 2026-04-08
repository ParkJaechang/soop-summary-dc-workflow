# Export Bundle

This folder contains a repo-friendly export of the current workspace.

## Contents

- `soop-summary-dc-workflow-snapshot.json`
  A text-file snapshot of the current project excluding local-only binaries, cookies, models, and generated database files.
- `file_manifest.txt`
  A line-by-line list of the exported file paths.

## Restore

From the repository root:

```bash
python scripts/restore_workspace_from_snapshot.py
```

For the smoothest experience with the existing absolute-path prompts, restore and work from `C:\python` on the next PC if possible.
