import unittest

from session.store import TokenStore


class StoreTest(unittest.TestCase):
    def test_round_trip(self):
        store = TokenStore()
        store.put("t1", {"user_id": 7, "used": False, "expires_at": 100})
        self.assertEqual(store.get("t1")["user_id"], 7)

    def test_mark_used(self):
        store = TokenStore()
        store.put("t1", {"user_id": 7, "used": False, "expires_at": 100})
        store.mark_used("t1")
        self.assertTrue(store.get("t1")["used"])
