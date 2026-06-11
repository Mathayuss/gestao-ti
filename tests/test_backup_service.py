import unittest
from datetime import datetime

from services.backup_service import (
    backup_is_due,
    backup_scheduled_at_for_period,
    last_day_of_month,
    normalize_backup_config,
    parse_backup_schedule_time,
    update_backup_config,
)


class BackupServiceTest(unittest.TestCase):
    def test_parse_backup_schedule_time_accepts_valid_times(self):
        self.assertEqual(parse_backup_schedule_time("2:05").strftime("%H:%M"), "02:05")
        self.assertEqual(parse_backup_schedule_time("23:59").strftime("%H:%M"), "23:59")
        self.assertIsNone(parse_backup_schedule_time("24:00"))
        self.assertIsNone(parse_backup_schedule_time("10:99"))
        self.assertIsNone(parse_backup_schedule_time("manha"))

    def test_normalize_backup_config_applies_safe_defaults(self):
        cfg = normalize_backup_config({
            "enabled": "on",
            "frequency": "invalid",
            "schedule_time": "99:99",
            "weekly_day": 99,
            "monthly_day": 0,
            "retention": 0,
            "include_audit": "sim",
        })

        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["frequency"], "daily")
        self.assertEqual(cfg["schedule_time"], "02:00")
        self.assertEqual(cfg["weekly_day"], 6)
        self.assertEqual(cfg["monthly_day"], 1)
        self.assertEqual(cfg["retention"], 1)
        self.assertTrue(cfg["include_audit"])

    def test_update_backup_config_validates_api_changes(self):
        cfg, error = update_backup_config({}, {
            "enabled": True,
            "frequency": "weekly",
            "schedule_time": "22:30",
            "weekly_day": 5,
            "monthly_day": 15,
            "retention": 120,
        })

        self.assertIsNone(error)
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["frequency"], "weekly")
        self.assertEqual(cfg["schedule_time"], "22:30")
        self.assertEqual(cfg["weekly_day"], 5)
        self.assertEqual(cfg["monthly_day"], 15)
        self.assertEqual(cfg["retention"], 90)

        self.assertEqual(update_backup_config({}, {"frequency": "yearly"})[1], "Frequência de backup inválida.")
        self.assertEqual(update_backup_config({}, {"schedule_time": "25:00"})[1], "Horário de backup inválido.")
        self.assertEqual(update_backup_config({}, {"weekly_day": 7})[1], "Dia da semana do backup inválido.")
        self.assertEqual(update_backup_config({}, {"monthly_day": 32})[1], "Dia do mês do backup inválido.")

    def test_scheduled_at_supports_daily_weekly_and_monthly(self):
        now = datetime(2026, 6, 10, 12, 0)  # quarta-feira

        daily = backup_scheduled_at_for_period({"frequency": "daily", "schedule_time": "02:00"}, now)
        weekly = backup_scheduled_at_for_period({"frequency": "weekly", "weekly_day": 1, "schedule_time": "03:00"}, now)
        monthly = backup_scheduled_at_for_period({"frequency": "monthly", "monthly_day": 31, "schedule_time": "04:00"}, now)

        self.assertEqual(daily, datetime(2026, 6, 10, 2, 0))
        self.assertEqual(weekly, datetime(2026, 6, 8, 3, 0))
        self.assertEqual(monthly, datetime(2026, 6, 30, 4, 0))
        self.assertEqual(last_day_of_month(2026, 2), 28)

    def test_backup_is_due_considers_schedule_and_last_run(self):
        now = datetime(2026, 6, 10, 12, 0)
        base = {"enabled": True, "frequency": "daily", "schedule_time": "02:00"}

        self.assertTrue(backup_is_due({**base, "last_run": ""}, now))
        self.assertTrue(backup_is_due({**base, "last_run": "2026-06-09T02:00:00"}, now))
        self.assertFalse(backup_is_due({**base, "last_run": "2026-06-10T02:00:00"}, now))
        self.assertFalse(backup_is_due({**base, "enabled": False}, now))
        self.assertFalse(backup_is_due({**base, "schedule_time": "23:00"}, now))


if __name__ == "__main__":
    unittest.main()
