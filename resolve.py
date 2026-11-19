"""Deep module for choosing an answer from the question bank or the LLM adapter."""

from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Sequence

import ds_model


@dataclass(frozen=True)
class Resolution:
    text: str
    chosen: Optional[str]
    source: str
    error: Optional[str] = None
    usage: Dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None


def match_option(answer: str, options: Sequence[str]) -> Optional[str]:
    """One fuzzy-match rule shared by answer choice and truth detection."""
    if not answer:
        return None
    text = answer.strip().lower()
    for option in options:
        if text == option.strip().lower():
            return option
    for option in options:
        candidate = option.strip().lower()
        if candidate and (candidate in text or text in candidate):
            return option
    return None


class Resolver:
    """One seam: bank and LLM are adapters behind it, not branches in the quiz loop."""

    def __init__(self, lookup: Callable, ask: Callable, settings=None):
        self._lookup = lookup
        self._ask = ask
        self._settings = settings

    def resolve(self, question: str, options: Sequence[str]) -> Resolution:
        entry, _key = self._lookup(question, options)
        if entry:
            answer = entry.get("a", "")
            return Resolution(answer, match_option(answer, options), "BANK")

        if self._settings is None:
            result = self._ask(question, options)
        else:
            result = self._ask(question, options, self._settings)
        if not result.ok:
            return Resolution("", None, "API", result.error)
        return Resolution(result.text, match_option(result.text, options), "API", usage=result.usage)


def should_learn(source: str) -> bool:
    """Only newly fetched answers may be written back to the bank."""
    return source == "API"


def default_resolver(bank=None):
    import qbank

    bank = bank or qbank.QuestionBank()
    return Resolver(bank.lookup, ds_model.ask, ds_model.load_settings())
