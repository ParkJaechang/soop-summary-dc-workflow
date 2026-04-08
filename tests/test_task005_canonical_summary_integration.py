import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import app_dc_publisher


CANONICAL_PAYLOAD_PATH = Path(
    r"C:\python\agents\artifacts\TASK-004-canonical-summary-payload-artifact-from-soop-summery-local-v3\sample_job\summaries\summary_payload.json"
)


class CanonicalSummaryIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        app_dc_publisher.DB_PATH = Path(self.temp_dir.name) / "dc_publisher_task005.db"
        app_dc_publisher.init_db()
        self.client = TestClient(app_dc_publisher.app)

    def tearDown(self) -> None:
        self.client.close()
        self.temp_dir.cleanup()

    def create_target(self) -> int:
        response = self.client.post(
            "/api/targets",
            json={
                "name": "TASK-005 Canonical Summary Review",
                "platform": "dcinside_gallery",
                "gallery_id": "task005_review",
                "board_url": "https://gall.dcinside.com/mgallery/board/lists/?id=task005_review",
                "active": True,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]

    def load_canonical_payload(self) -> dict:
        return json.loads(CANONICAL_PAYLOAD_PATH.read_text(encoding="utf-8"))

    def test_canonical_summary_payload_maps_into_draft_job(self) -> None:
        target_id = self.create_target()
        canonical_payload = self.load_canonical_payload()

        bridge_payload = app_dc_publisher.build_summary_bridge_payload_from_canonical_summary(
            canonical_payload,
            target_id=target_id,
        )

        response = self.client.post(
            "/api/summary-bridge/draft-job",
            json=bridge_payload.model_dump(),
        )
        self.assertEqual(response.status_code, 200, response.text)
        job = response.json()

        self.assertEqual(job["status"], "draft")
        self.assertEqual(job["source_type"], "summary_payload")
        self.assertEqual(job["title"], canonical_payload["title"])
        self.assertEqual(job["body"], canonical_payload["body"])
        self.assertEqual(job["source_ref"], canonical_payload["metadata"]["source"]["canonical_source_url"])
        self.assertEqual(
            job["metadata"]["publisher_bridge"]["canonical_source_ref"],
            "soop_vod:71021072",
        )
        self.assertEqual(
            job["metadata"]["summary_payload"]["contract_version"],
            canonical_payload["contract_version"],
        )
        self.assertEqual(
            job["metadata"]["summary_payload"]["dedupe_basis"]["canonical_source_url"],
            canonical_payload["dedupe_basis"]["canonical_source_url"],
        )
        self.assertEqual(job["metadata"]["source"]["source_id"], canonical_payload["metadata"]["source"]["source_id"])


if __name__ == "__main__":
    unittest.main()
