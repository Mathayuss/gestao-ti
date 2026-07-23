import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["AUTO_SEED_DEMO"] = "0"
os.environ["SHOW_DEMO_CREDENTIALS"] = "0"

import app as tic  # noqa: E402


settings_routes = sys.modules["routes.settings"]


class FakeCommandResult:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def fake_update_command(args, timeout=30):
    if args == ["git", "rev-parse", "--short", "HEAD"]:
        return FakeCommandResult("abc123\n"), None
    if args == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
        return FakeCommandResult("main\n"), None
    if args == ["git", "config", "--get", "branch.main.remote"]:
        return FakeCommandResult("origin\n"), None
    if args == ["git", "diff", "--ignore-cr-at-eol", "HEAD"]:
        return FakeCommandResult(""), None
    if args == ["git", "fetch", "--prune", "origin"]:
        return FakeCommandResult(""), None
    if args == ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
        return FakeCommandResult("origin/main\n"), None
    if args == ["git", "show", "origin/main:VERSION"]:
        return FakeCommandResult("1.3.6\n"), None
    if args == ["git", "rev-list", "--left-right", "--count", "HEAD...origin/main"]:
        return FakeCommandResult("0\t2\n"), None
    return FakeCommandResult("", returncode=1, stderr="comando inesperado"), None


class SystemUpdateStatusTest(unittest.TestCase):
    def setUp(self):
        tic.app.config.update(TESTING=True)

    def test_update_check_works_when_apply_is_disabled(self):
        with patch.dict(os.environ, {"SELF_UPDATE_ENABLED": "0"}, clear=False), \
             patch("routes.settings.shutil.which", return_value="/usr/bin/git"), \
             patch("routes.settings.os.path.isdir", return_value=True), \
             patch("routes.settings._run_update_command", side_effect=fake_update_command):
            status = settings_routes._system_update_status(fetch=True)

        self.assertTrue(status["supported"])
        self.assertTrue(status["checkSupported"])
        self.assertFalse(status["enabled"])
        self.assertFalse(status["applySupported"])
        self.assertTrue(status["updateAvailable"])
        self.assertFalse(status["canApply"])
        self.assertEqual(status["availableVersion"], "1.3.6")
        self.assertIn("desativada", status["blockReason"])

    def test_update_apply_can_be_enabled_explicitly(self):
        with patch.dict(os.environ, {"SELF_UPDATE_ENABLED": "1"}, clear=False), \
             patch("routes.settings.shutil.which", return_value="/usr/bin/git"), \
             patch("routes.settings.os.path.isdir", return_value=True), \
             patch("routes.settings._run_update_command", side_effect=fake_update_command):
            status = settings_routes._system_update_status(fetch=True)

        self.assertTrue(status["enabled"])
        self.assertTrue(status["applySupported"])
        self.assertTrue(status["updateAvailable"])
        self.assertTrue(status["canApply"])

    def test_update_check_explains_missing_git_metadata(self):
        with patch.dict(os.environ, {"SELF_UPDATE_ENABLED": "1"}, clear=False), \
             patch("routes.settings.shutil.which", return_value="/usr/bin/git"), \
             patch("routes.settings.os.path.isdir", return_value=False):
            status = settings_routes._system_update_status(fetch=True)

        self.assertFalse(status["supported"])
        self.assertFalse(status["checkSupported"])
        self.assertFalse(status["applySupported"])
        self.assertIn(".git", status["message"])


if __name__ == "__main__":
    unittest.main()
