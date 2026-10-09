from tests.helpers import CliTestCase


class ListTest(CliTestCase):
    def test_shows_table(self):
        status, out = self.run_cli("list")
        self.assertEqual(status, 0)
        self.assertIn("TITLE", out)
        self.assertIn("Write docs", out)

    def test_filters_by_status(self):
        _, out = self.run_cli("list", "--status", "done")
        self.assertIn("Ship 1.0", out)
        self.assertNotIn("Write docs", out)
