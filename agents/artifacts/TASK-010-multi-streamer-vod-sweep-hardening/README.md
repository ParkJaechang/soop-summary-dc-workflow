# TASK-010 Artifacts

This folder stores local evidence for the multi-streamer VOD sweep hardening slice.

Saved artifacts:
- `multi_streamer_fixture_map.json`
  records the local replay fixtures used for alpha, beta, gamma, and the inactive delta control row
- `multi_streamer_vod_refresh_result.json`
  captures `POST /api/vods/refresh` output with mixed per-streamer results
- `per_streamer_vod_api_results.json`
  captures API-visible VOD rows from `GET /api/streamers/{id}/vods`
- `vod_rows_after_multi_sweep.json`
  snapshots normalized `vods` persistence after the sweep
- `collector_runs_after_multi_sweep.json`
  snapshots sweep-level and per-streamer `collector_runs` visibility
- `streamers_after_multi_sweep.json`
  snapshots the registered streamers used in the test, including the inactive control streamer
- `multi_streamer_verification_notes.txt`
  summarizes the local verification outcome and counts

Verification shape:
- active streamers:
  alpha, beta, gamma
- inactive control:
  delta
- mixed outcome:
  alpha completed, beta completed, gamma failed, delta excluded by active filter
- persisted VOD rows:
  3 total rows across 2 successful streamers
- collector-run visibility:
  1 sweep-level completed run plus 3 per-streamer runs
