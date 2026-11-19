"""Tests for quiz outcome interpretation through the Verdict interface."""

import unittest

from verdict import Verdict


class Scripted:
    def __init__(self, values):
        self.values = list(values)
        self.calls = 0

    def __call__(self):
        if not self.values:
            self.calls += 1
            return ""
        value = self.values[min(self.calls, len(self.values) - 1)]
        self.calls += 1
        return value


class VerdictTest(unittest.TestCase):
    def make(self, bodies, spans=None, store=None):
        return Verdict(
            Scripted(bodies),
            Scripted([spans] if spans else [[]]),
            store=store,
            sleep=lambda _: None,
            poll_count=5,
        )

    def test_energy_without_error_marks_correct(self):
        outcome = self.make(["Energy 100"]).observe("q", ["Paris", "Rome"], "Paris")
        self.assertTrue(outcome.ok)
        self.assertIsNone(outcome.error)
        self.assertFalse(outcome.stored)

    def test_revealed_answer_is_matched_and_stored_as_truth(self):
        saved = []
        subject = self.make(
            ["Incorrect!", "Incorrect", "Correct Answer: Paris"],
            spans=["Paris", "extra"],
            store=lambda *args: saved.append(args),
        )
        outcome = subject.observe("q", ["Paris", "Rome"], "Rome", should_store=True)
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.revealed, "Paris")
        self.assertTrue(outcome.stored)
        self.assertEqual(saved, [("q", ["Paris", "Rome"], "Paris")])

    def test_incorrect_exclamation_is_not_treated_as_success(self):
        outcome = self.make(["Incorrect!"]).observe("q", ["Paris"], "Paris")
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.error, "no verdict within polling window")

    def test_timeout_reports_error(self):
        outcome = self.make(["waiting"]).observe("q", ["Paris"], "Paris")
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.error, "no verdict within polling window")

    def test_bank_sourced_answers_are_not_stored(self):
        saved = []
        subject = self.make(
            ["Incorrect!", "Correct Answer: Rome"],
            spans=["Rome"],
            store=lambda *args: saved.append(args),
        )
        outcome = subject.observe("q", ["Paris", "Rome"], "Paris", should_store=False)
        self.assertEqual(outcome.revealed, "Rome")
        self.assertEqual(saved, [])
        self.assertFalse(outcome.stored)


if __name__ == "__main__":
    unittest.main()
