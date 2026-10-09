import json

from tests.helpers import CliTestCase


class ShowTest(CliTestCase):
    def test_json_prints_one_record(self):
        status, out = self.run_cli("show", "1", "--json")
        self.assertEqual(status, 0)
        self.assertEqual(
            json.loads(out),
            {"id": 1, "title": "Write docs", "status": "open", "due": "2026-05-01"},
        )

    def test_unknown_id(self):
        status, out = self.run_cli("show", "99")
        self.assertEqual(status, 1)
        self.assertIn("no task with id 99", out)
