import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from cli.main import main

TASKS = [
    {"id": 1, "title": "Write docs", "status": "open", "due": "2026-05-01"},
    {"id": 2, "title": "Ship 1.0", "status": "done", "due": None},
]


class CliTestCase(unittest.TestCase):
    """Runs the CLI against a temporary task file and captures stdout."""

    tasks = TASKS

    def setUp(self):
        handle, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(handle, "w") as f:
            json.dump(self.tasks, f)
        self.addCleanup(os.remove, path)
        patcher = mock.patch.dict(os.environ, {"TASKTRACK_FILE": path})
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = main(list(argv))
        return status, out.getvalue()
