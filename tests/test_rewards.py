from datetime import date
import unittest

from core.rewards import (
    attendance_reward,
    furniture_progress_from_auth_minutes,
    next_pet_stage,
    pet_current_level_exp,
    pet_current_level_required_exp,
    pet_exp_from_verified_seconds,
    pet_level_from_exp,
    pet_stage_name,
)


class RewardFormulaTest(unittest.TestCase):
    def test_pet_exp_is_one_per_five_verified_minutes(self):
        self.assertEqual(pet_exp_from_verified_seconds(0), 0)
        self.assertEqual(pet_exp_from_verified_seconds(299), 0)
        self.assertEqual(pet_exp_from_verified_seconds(300), 1)
        self.assertEqual(pet_exp_from_verified_seconds(3600), 12)

    def test_pet_exp_never_goes_negative(self):
        self.assertEqual(pet_exp_from_verified_seconds(-10), 0)

    def test_pet_level_thresholds(self):
        self.assertEqual(pet_level_from_exp(0), 1)
        self.assertEqual(pet_level_from_exp(20), 2)
        self.assertEqual(pet_level_from_exp(80), 3)
        self.assertEqual(pet_level_from_exp(200), 4)
        self.assertEqual(pet_level_from_exp(400), 5)

    def test_pet_level_stays_at_previous_stage_before_threshold(self):
        self.assertEqual(pet_level_from_exp(19), 1)
        self.assertEqual(pet_level_from_exp(79), 2)
        self.assertEqual(pet_level_from_exp(199), 3)
        self.assertEqual(pet_level_from_exp(399), 4)

    def test_pet_stage_name_matches_level(self):
        self.assertEqual(pet_stage_name(1), "알")
        self.assertEqual(pet_stage_name(4), "어른")
        self.assertEqual(pet_stage_name(5), "전공 용품")
        self.assertEqual(pet_stage_name(6), "전공 용품")

    def test_next_pet_stage_returns_none_at_max_level(self):
        self.assertEqual(next_pet_stage(0)["level"], 2)
        self.assertIsNone(next_pet_stage(400))

    def test_pet_current_level_progress_uses_current_level_requirement(self):
        self.assertEqual(pet_level_from_exp(199), 3)
        self.assertEqual(pet_current_level_exp(199), 119)
        self.assertEqual(pet_current_level_required_exp(199), 120)

    def test_first_attendance_gives_base_bonus(self):
        reward = attendance_reward(None, 0, date(2026, 5, 29))

        self.assertTrue(reward.is_first_attendance_today)
        self.assertEqual(reward.streak_days, 1)
        self.assertEqual(reward.bonus_exp, 2)

    def test_same_day_attendance_does_not_pay_twice(self):
        reward = attendance_reward(date(2026, 5, 29), 4, date(2026, 5, 29))

        self.assertFalse(reward.is_first_attendance_today)
        self.assertEqual(reward.streak_days, 4)
        self.assertEqual(reward.bonus_exp, 0)

    def test_consecutive_third_day_attendance_bonus(self):
        reward = attendance_reward(date(2026, 5, 28), 2, date(2026, 5, 29))

        self.assertEqual(reward.streak_days, 3)
        self.assertEqual(reward.bonus_exp, 7)

    def test_consecutive_seventh_day_attendance_bonus(self):
        reward = attendance_reward(date(2026, 5, 28), 6, date(2026, 5, 29))

        self.assertEqual(reward.streak_days, 7)
        self.assertEqual(reward.bonus_exp, 12)

    def test_missed_day_resets_streak(self):
        reward = attendance_reward(date(2026, 5, 25), 5, date(2026, 5, 29))

        self.assertEqual(reward.streak_days, 1)
        self.assertEqual(reward.bonus_exp, 2)

    def test_furniture_progress_table(self):
        cases = [
            (1, 5),
            (14, 5),
            (15, 10),
            (34, 10),
            (35, 15),
            (49, 15),
            (50, 20),
            (59, 20),
            (60, 25),
            (69, 25),
            (70, 30),
            (79, 30),
            (80, 35),
            (89, 35),
            (90, 40),
            (120, 40),
        ]

        for minute, expected_progress in cases:
            with self.subTest(minute=minute):
                self.assertEqual(furniture_progress_from_auth_minutes(minute), expected_progress)


if __name__ == "__main__":
    unittest.main()
