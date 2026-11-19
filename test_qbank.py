"""Tests for the question bank module through lookup/store only."""

import json
import os
import tempfile
import unittest

from qbank import QuestionBank


class QuestionBankTest(unittest.TestCase):
    def test_store_is_visible_to_a_reloaded_bank_and_key_is_order_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "qbank.json")
            bank = QuestionBank(path)
            self.assertEqual(len(bank), 0)
            self.assertIsNone(bank.lookup("Capital?", ["Paris", "Rome"])[0])

            key = bank.store("Capital?", ["Paris", "Rome"], "Paris")
            self.assertEqual(len(bank), 1)
            self.assertFalse(os.path.exists(path + ".tmp"))

            reloaded = QuestionBank(path)
            entry, found_key = reloaded.lookup("Capital?", ["Rome", "Paris"])
            self.assertEqual(found_key, key)
            self.assertEqual(entry["a"], "Paris")
            self.assertEqual(entry["opts"], ["Paris", "Rome"])

    def test_corrupt_file_starts_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "qbank.json")
            with open(path, "w") as out:
                out.write("not json")
            bank = QuestionBank(path)
            self.assertEqual(len(bank), 0)

    def test_writes_leave_no_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "qbank.json")
            bank = QuestionBank(path)
            bank.store("Q", ["A"], "A")
            with open(path, encoding="utf-8") as source:
                entries = json.load(source)
            self.assertEqual(len(entries), 1)
            self.assertFalse(os.path.exists(path + ".tmp"))


if __name__ == "__main__":
    unittest.main()
