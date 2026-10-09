import unittest

from app.routes import dispatch


class RoutesTest(unittest.TestCase):
    def test_health(self):
        self.assertEqual(dispatch("/health", {}), {"status": 200, "body": {"ok": True}})

    def test_unknown_path_is_404(self):
        self.assertEqual(dispatch("/nope", {})["status"], 404)


if __name__ == "__main__":
    unittest.main()
