"""Tests for settings resolution and the LLM adapter's structured result."""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

import ds_model


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class SettingsTest(unittest.TestCase):
    def test_each_key_falls_back_independently(self):
        with tempfile.TemporaryDirectory() as script_dir, tempfile.TemporaryDirectory() as cwd:
            with open(os.path.join(script_dir, ".env.local"), "w") as out:
                out.write("BASE_URL=https://from-script.test\nAPI_KEY=sk-script\n")
            with open(os.path.join(cwd, ".env.local"), "w") as out:
                out.write("MODEL=model-from-cwd\nAPI_KEY=sk-cwd\n")

            settings = ds_model.load_settings(environ={}, script_dir=script_dir, cwd=cwd)

            self.assertEqual(settings.api_url, "https://from-script.test")
            self.assertEqual(settings.api_key, "sk-script")
            self.assertEqual(settings.model, "model-from-cwd")

    def test_environment_overrides_files(self):
        with tempfile.TemporaryDirectory() as script_dir, tempfile.TemporaryDirectory() as cwd:
            with open(os.path.join(script_dir, ".env.local"), "w") as out:
                out.write("API_KEY=sk-script\n")
            settings = ds_model.load_settings(
                environ={"API_KEY": "sk-env"}, script_dir=script_dir, cwd=cwd
            )
            self.assertEqual(settings.api_key, "sk-env")

    def test_settings_are_immutable(self):
        settings = ds_model.Settings("https://x.test", "k", "m")
        with self.assertRaises(Exception):
            settings.api_key = "other"


class AskTest(unittest.TestCase):
    def test_missing_key_returns_structured_error(self):
        settings = ds_model.Settings("https://x.test", "", "m")
        result = ds_model.ask("q", ["a", "b"], settings)
        self.assertFalse(result.ok)
        self.assertIn("API_KEY", result.error)

    def test_answer_is_returned_as_text(self):
        payload = {"choices": [{"message": {"content": "Paris"}}], "usage": {"total_tokens": 5}}
        settings = ds_model.Settings("https://x.test", "k", "m")
        with patch("ds_model.urllib.request.urlopen", return_value=FakeResponse(payload)):
            result = ds_model.ask("Capital?", ["Paris", "Rome"], settings)
        self.assertTrue(result.ok)
        self.assertEqual(result.text, "Paris")
        self.assertEqual(result.usage, {"total_tokens": 5})

    def test_reasoning_content_is_used_as_fallback(self):
        payload = {
            "choices": [
                {"message": {"content": "", "reasoning_content": "The answer is Paris."}}
            ]
        }
        settings = ds_model.Settings("https://x.test", "k", "m")
        with patch("ds_model.urllib.request.urlopen", return_value=FakeResponse(payload)):
            result = ds_model.ask("Capital?", ["Paris", "Rome"], settings)
        self.assertEqual(result.text, "Paris")


if __name__ == "__main__":
    unittest.main()
