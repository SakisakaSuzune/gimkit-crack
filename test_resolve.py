"""Tests for answer resolution through one interface with two injected adapters."""

import unittest

import ds_model
from resolve import Resolver, match_option


class FakeBank:
    def __init__(self, entry=None):
        self.entry = entry
        self.calls = []

    def lookup(self, question, options):
        self.calls.append((question, options))
        return self.entry, "key"


def fake_ask(question, options, settings=None):
    return ds_model.LLMResult("Paris", {"total_tokens": 3})


class MatchOptionTest(unittest.TestCase):
    def test_exact_match_wins_over_containment(self):
        options = ["Paris", "Parisette"]
        self.assertEqual(match_option("The city is Paris", options), "Paris")

    def test_no_match_returns_none(self):
        self.assertIsNone(match_option("Berlin", ["Paris", "Rome"]))


class ResolverTest(unittest.TestCase):
    def test_bank_hit_skips_llm(self):
        bank = FakeBank({"a": "Rome"})
        calls = []

        def ask(*args, **kwargs):
            calls.append(args)
            return ds_model.LLMResult("Paris")

        result = Resolver(bank.lookup, ask).resolve("Capital?", ["Paris", "Rome"])
        self.assertTrue(result.ok)
        self.assertEqual(result.source, "BANK")
        self.assertEqual(result.chosen, "Rome")
        self.assertEqual(calls, [])

    def test_llm_answer_is_matched_and_kept(self):
        bank = FakeBank()
        result = Resolver(bank.lookup, fake_ask).resolve("Capital?", ["Paris", "Rome"])
        self.assertEqual(result.source, "API")
        self.assertEqual(result.text, "Paris")
        self.assertEqual(result.chosen, "Paris")
        self.assertEqual(result.usage, {"total_tokens": 3})

    def test_llm_error_becomes_result_error_not_string(self):
        def ask(*args, **kwargs):
            return ds_model.LLMResult("", {}, "provider down")

        result = Resolver(FakeBank().lookup, ask).resolve("Capital?", ["Paris"])
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "provider down")
        self.assertIsNone(result.chosen)


class LearnPolicyTest(unittest.TestCase):
    def test_only_api_answers_are_learned(self):
        from resolve import should_learn

        self.assertTrue(should_learn("API"))
        self.assertFalse(should_learn("BANK"))


if __name__ == "__main__":
    unittest.main()
