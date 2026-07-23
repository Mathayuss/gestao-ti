import os
import tempfile
import unittest
from unittest.mock import patch

from config import (
    DEFAULT_SECRET_KEY_DEV,
    database_engine_options,
    flask_config,
    resolve_secret_key,
    runtime_server_config,
    startup_retry_config,
)


class ConfigTest(unittest.TestCase):
    def test_secret_key_is_required_outside_debug(self):
        with patch.dict(os.environ, {"FLASK_DEBUG": "0"}, clear=True):
            with self.assertRaises(RuntimeError):
                resolve_secret_key()

    def test_secret_key_allows_debug_fallback(self):
        with patch.dict(os.environ, {"FLASK_DEBUG": "1"}, clear=True):
            with self.assertLogs("ti_control", level="WARNING"):
                self.assertEqual(resolve_secret_key(), DEFAULT_SECRET_KEY_DEV)

    def test_flask_config_reads_version_and_security_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "VERSION"), "w", encoding="utf-8") as fh:
                fh.write("2.0.0-test\n")
            env = {
                "SECRET_KEY": "secret-test",
                "DATABASE_URL": "postgresql+psycopg://user:pass@db/app",
                "DATABASE_POOL_SIZE": "7",
                "DATABASE_MAX_OVERFLOW": "3",
                "DATABASE_POOL_TIMEOUT": "20",
                "APP_BASE_URL": "https://ti.example.com/",
                "SESSION_SECURE": "1",
                "SHOW_DEMO_CREDENTIALS": "1",
                "AUTO_CREATE_DB": "0",
            }
            with patch.dict(os.environ, env, clear=True):
                cfg = flask_config(tmp)

        self.assertEqual(cfg["BUILD_VERSION"], "2.0.0-test")
        self.assertEqual(cfg["APP_BASE_URL"], "https://ti.example.com")
        self.assertTrue(cfg["SESSION_COOKIE_SECURE"])
        self.assertTrue(cfg["REMEMBER_COOKIE_SECURE"])
        self.assertTrue(cfg["SHOW_DEMO_CREDENTIALS"])
        self.assertFalse(cfg["AUTO_CREATE_DB"])
        self.assertEqual(cfg["SQLALCHEMY_ENGINE_OPTIONS"]["pool_size"], 7)
        self.assertEqual(cfg["SQLALCHEMY_ENGINE_OPTIONS"]["max_overflow"], 3)
        self.assertEqual(cfg["SQLALCHEMY_ENGINE_OPTIONS"]["pool_timeout"], 20)

    def test_build_version_env_overrides_version_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "VERSION"), "w", encoding="utf-8") as fh:
                fh.write("2.0.0-test\n")
            with patch.dict(os.environ, {"SECRET_KEY": "secret-test", "BUILD_VERSION": "9.9.9"}, clear=True):
                self.assertEqual(flask_config(tmp)["BUILD_VERSION"], "9.9.9")

    def test_sqlite_keeps_engine_options_minimal(self):
        with patch.dict(os.environ, {"DATABASE_POOL_SIZE": "9"}, clear=True):
            options = database_engine_options("sqlite:///:memory:")

        self.assertEqual(options["pool_recycle"], 300)
        self.assertNotIn("pool_size", options)

    def test_runtime_and_startup_env_helpers(self):
        env = {
            "APP_PORT": "6000",
            "FLASK_PORT": "7000",
            "FLASK_DEBUG": "0",
            "DB_STARTUP_RETRIES": "0",
            "DB_STARTUP_RETRY_DELAY": "-5",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(runtime_server_config(), ("0.0.0.0", 7000, False))
            self.assertEqual(startup_retry_config(), (1, 0))


if __name__ == "__main__":
    unittest.main()
