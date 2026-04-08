import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import app_dc_publisher


class SummaryBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        app_dc_publisher.DB_PATH = Path(self.temp_dir.name) / "dc_publisher_test.db"
        app_dc_publisher.init_db()
        self.client = TestClient(app_dc_publisher.app)

    def tearDown(self) -> None:
        self.client.close()
        self.temp_dir.cleanup()

    def create_target(self) -> int:
        response = self.client.post(
            "/api/targets",
            json={
                "name": "SOOP Summary Review",
                "platform": "dcinside_gallery",
                "gallery_id": "soop_review",
                "board_url": "https://gall.dcinside.com/mgallery/board/lists/?id=soop_review",
                "active": True,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]

    def summary_payload(self, target_id: int) -> dict:
        return {
            "target_id": target_id,
            "title": "[VOD 요약] 새벽 랭크전 핵심 장면 정리",
            "body": "1. 초반 운영 요약\n2. 중반 교전 포인트\n3. 마무리 총평",
            "producer": "soop_summery_local_v3",
            "source_url": "https://vod.sooplive.co.kr/player/123456",
            "source_id": "vod-123456",
            "metadata": {
                "streamer_id": "nanamoon777",
                "streamer_name": "나나문",
                "vod_id": "123456",
                "vod_url": "https://vod.sooplive.co.kr/player/123456",
                "summary_mode": "timeline_merge",
                "summary_path": "C:/python/data/example/summaries/final_summary.txt",
            },
        }

    def test_summary_bridge_creates_reviewable_draft_job(self) -> None:
        target_id = self.create_target()
        response = self.client.post(
            "/api/summary-bridge/draft-job",
            json=self.summary_payload(target_id),
        )
        self.assertEqual(response.status_code, 200, response.text)
        job = response.json()

        self.assertEqual(job["status"], "draft")
        self.assertEqual(job["source_type"], "summary_payload")
        self.assertEqual(job["source_ref"], "https://vod.sooplive.co.kr/player/123456")
        self.assertTrue(job["dedupe_key"].startswith(f"summary-draft:v1:{target_id}:"))
        self.assertEqual(job["metadata"]["streamer_id"], "nanamoon777")
        self.assertEqual(job["metadata"]["publisher_bridge"]["producer"], "soop_summery_local_v3")
        self.assertEqual(job["metadata"]["publisher_bridge"]["canonical_source_ref"], "soop_vod:123456")
        self.assertTrue(job["metadata"]["publisher_bridge"]["draft_only"])

    def test_summary_bridge_rejects_duplicate_source_on_same_target(self) -> None:
        target_id = self.create_target()
        payload = self.summary_payload(target_id)

        first = self.client.post("/api/summary-bridge/draft-job", json=payload)
        second = self.client.post("/api/summary-bridge/draft-job", json=payload)

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 409, second.text)
        self.assertIn("Duplicate dedupe_key", second.text)

    def test_summary_bridge_dedupes_mixed_source_id_and_source_url_for_same_source(self) -> None:
        target_id = self.create_target()
        id_only_payload = self.summary_payload(target_id)
        id_only_payload["source_url"] = ""
        id_only_payload["source_ref"] = ""

        mixed_identity_payload = self.summary_payload(target_id)

        first = self.client.post("/api/summary-bridge/draft-job", json=id_only_payload)
        second = self.client.post("/api/summary-bridge/draft-job", json=mixed_identity_payload)

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["metadata"]["publisher_bridge"]["canonical_source_ref"], "soop_vod:123456")
        self.assertEqual(second.status_code, 409, second.text)
        self.assertIn("Duplicate dedupe_key", second.text)

    def test_job_patch_rejects_status_changes(self) -> None:
        target_id = self.create_target()
        created = self.client.post("/api/summary-bridge/draft-job", json=self.summary_payload(target_id))
        self.assertEqual(created.status_code, 200, created.text)
        job_id = created.json()["id"]

        response = self.client.patch(f"/api/jobs/{job_id}", json={"status": "approved"})

        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("Use dedicated approval", response.text)

    def test_job_patch_trims_dedupe_key_without_corrupting_updated_at(self) -> None:
        target_id = self.create_target()
        created = self.client.post("/api/summary-bridge/draft-job", json=self.summary_payload(target_id))
        self.assertEqual(created.status_code, 200, created.text)
        original_job = created.json()
        job_id = original_job["id"]

        response = self.client.patch(f"/api/jobs/{job_id}", json={"dedupe_key": "   "})

        self.assertEqual(response.status_code, 200, response.text)
        patched_job = response.json()
        self.assertEqual(patched_job["dedupe_key"], "")
        self.assertEqual(patched_job["title"], original_job["title"])
        self.assertEqual(patched_job["source_ref"], original_job["source_ref"])
        self.assertTrue(patched_job["updated_at"])

    def test_job_patch_updates_title_and_metadata_fields_in_place(self) -> None:
        target_id = self.create_target()
        created = self.client.post("/api/summary-bridge/draft-job", json=self.summary_payload(target_id))
        self.assertEqual(created.status_code, 200, created.text)
        original_job = created.json()
        job_id = original_job["id"]

        response = self.client.patch(
            f"/api/jobs/{job_id}",
            json={
                "title": "Updated review title",
                "metadata": {
                    "streamer_id": "nanamoon777",
                    "summary_mode": "patched",
                },
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        patched_job = response.json()
        self.assertEqual(patched_job["title"], "Updated review title")
        self.assertEqual(patched_job["metadata"]["summary_mode"], "patched")
        self.assertEqual(patched_job["dedupe_key"], original_job["dedupe_key"])
        self.assertTrue(patched_job["updated_at"])


if __name__ == "__main__":
    unittest.main()
