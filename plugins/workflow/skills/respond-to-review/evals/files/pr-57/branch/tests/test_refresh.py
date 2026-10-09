import unittest

from session.refresh import SESSION_TTL_SECONDS, refresh
from session.store import TokenStore


def make_store():
    store = TokenStore()
    store.put("r1", {"user_id": 7, "used": False, "expires_at": 1000})
    return store


class RefreshTest(unittest.TestCase):
    def test_issues_new_pair(self):
        store = make_store()
        out = refresh(store, "r1", now=10)
        self.assertNotEqual(out["refresh_token"], "r1")
        self.assertEqual(store.get(out["refresh_token"])["expires_at"], 10 + SESSION_TTL_SECONDS)

    def test_rejects_reuse(self):
        store = make_store()
        refresh(store, "r1", now=10)
        with self.assertRaises(PermissionError):
            refresh(store, "r1", now=11)

    def test_rejects_expired(self):
        with self.assertRaises(PermissionError):
            refresh(make_store(), "r1", now=1001)
