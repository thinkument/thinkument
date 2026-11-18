import unittest

from thinkument.daemon.server import create_daemon_app


class TestDaemonJobLookup(unittest.TestCase):
    def test_unknown_job_returns_json_not_found(self):
        client = create_daemon_app().test_client()

        response = client.get("/api/v1/ops/jobs/missing-job/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.get_json(),
            {"error": "Job not found", "job_id": "missing-job"},
        )
