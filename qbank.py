"""Question bank module: lookup and store over a private JSON dictionary."""

import hashlib
import json
import os


def make_key(question, options):
    """Stable key from question text plus the sorted option set."""
    normalized_question = " ".join(question.strip().lower().split())
    normalized_options = sorted(" ".join(option.strip().lower().split()) for option in options)
    raw = normalized_question + "||" + "|".join(normalized_options)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


class QuestionBank:
    def __init__(self, path=None):
        self._path = path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "qbank.json"
        )
        try:
            with open(self._path, encoding="utf-8") as source:
                loaded = json.load(source)
            self._entries = loaded if isinstance(loaded, dict) else {}
        except (OSError, ValueError):
            self._entries = {}

    def __len__(self):
        return len(self._entries)

    def lookup(self, question, options):
        key = make_key(question, options)
        return self._entries.get(key), key

    def store(self, question, options, answer):
        key = make_key(question, options)
        self._entries[key] = {
            "q": question.strip(),
            "opts": sorted(option.strip() for option in options),
            "a": answer.strip(),
        }
        self._flush()
        return key

    def _flush(self):
        temporary = self._path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as target:
            json.dump(self._entries, target, ensure_ascii=False, indent=1)
        os.replace(temporary, self._path)


if __name__ == "__main__":
    print("entries", len(QuestionBank()))
