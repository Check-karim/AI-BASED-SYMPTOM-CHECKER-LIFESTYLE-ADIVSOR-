import unittest

from engines import evaluate_symptoms
from validators import (
    account_errors,
    validate_email,
    validate_full_name,
    validate_new_password,
    validate_phone,
    validate_username,
)


class ValidatorTests(unittest.TestCase):
    def test_name_rules(self):
        self.assertEqual(validate_full_name("  Marie   Claire ")[1], "Marie Claire")
        self.assertIn("numbers or special", validate_full_name("Jean2")[0])
        self.assertIn("numbers or special", validate_full_name("Jean-Paul")[0])
        self.assertEqual(validate_full_name("   ")[1], "")

    def test_username_rules(self):
        self.assertEqual(validate_username("nurse1")[1], "nurse1")
        self.assertIn("spaces", validate_username("nu rse")[0])
        self.assertIn("number", validate_username("1nurse")[0])
        self.assertIn("special", validate_username("_nurse")[0])
        self.assertIn("special", validate_username("@nurse")[0])
        self.assertIn("letters and numbers", validate_username("nurse!")[0])
        self.assertIn("at least 3", validate_username("nu")[0])
        self.assertIn("reserved", validate_username("Admin")[0])

    def test_password_minimum(self):
        self.assertIn("at least 6", validate_new_password("admin", "admin"))
        self.assertEqual(validate_new_password("clinic", "clinic"), "")
        self.assertIn("do not match", validate_new_password("clinic", "clinic1"))

    def test_email_and_phone(self):
        self.assertEqual(validate_email("Nurse@KFH.RW")[1], "nurse@kfh.rw")
        self.assertTrue(validate_email("not-an-email")[0])
        self.assertEqual(validate_phone("078 123 4567")[1], "+250781234567")
        self.assertEqual(validate_phone("250781234567")[1], "+250781234567")
        self.assertEqual(validate_phone("+250781234567")[1], "+250781234567")
        self.assertEqual(validate_phone("+14155552671")[1], "+14155552671")
        self.assertTrue(validate_phone("0711234567")[0])
        self.assertTrue(validate_phone("12345")[0])

    def test_account_form(self):
        errors, cleaned = account_errors(
            {
                "full_name": "Aline Uwase",
                "username": "aline1",
                "email": "aline@example.com",
                "phone": "0731234567",
                "password": "secret1",
                "confirm_password": "secret1",
            }
        )
        self.assertEqual(errors, {})
        self.assertEqual(cleaned["username"], "aline1")


class EngineTests(unittest.TestCase):
    def test_mild_cold_stays_home_care(self):
        result = evaluate_symptoms(
            ["cough", "sore_throat", "runny_nose"],
            "under_24h",
            "mild",
            "adult",
            "no",
            "",
        )
        self.assertEqual(result["urgency"], "self_care")

    def test_severe_chest_pain_is_emergency(self):
        result = evaluate_symptoms(["chest"], "1_3_days", "severe", "adult", "no", "")
        self.assertEqual(result["urgency"], "emergency")

    def test_mild_chest_pain_is_same_day(self):
        result = evaluate_symptoms(["chest"], "under_24h", "mild", "adult", "no", "")
        self.assertEqual(result["urgency"], "urgent")

    def test_fainting_is_emergency(self):
        result = evaluate_symptoms(["fainting"], "under_24h", "mild", "adult", "no", "")
        self.assertEqual(result["urgency"], "emergency")

    def test_crisis_language_is_emergency(self):
        result = evaluate_symptoms(["sleep"], "1_3_days", "mild", "adult", "no", "I want to die")
        self.assertEqual(result["urgency"], "emergency")
        self.assertIn("immediate", result["title"].lower())

    def test_child_is_not_left_on_self_care(self):
        result = evaluate_symptoms(
            ["cough", "runny_nose"],
            "under_24h",
            "mild",
            "under_12",
            "no",
            "",
        )
        self.assertNotEqual(result["urgency"], "self_care")


if __name__ == "__main__":
    unittest.main()
