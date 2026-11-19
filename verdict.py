"""Deep module for turning page feedback into one quiz outcome."""

import time
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from resolve import match_option


@dataclass(frozen=True)
class Outcome:
    ok: bool
    revealed: Optional[str]
    body: str
    error: Optional[str] = None
    stored: bool = False


class Verdict:
    """Owns polling, feedback parsing, truth selection and the bank write."""

    def __init__(
        self,
        read_body: Callable[[], str],
        read_spans: Callable[[], Sequence[str]],
        store=None,
        sleep: Callable[[float], None] = time.sleep,
        poll_count=60,
        interval=0.25,
    ):
        self._read_body = read_body
        self._read_spans = read_spans
        self._store = store
        self._sleep = sleep
        self._poll_count = poll_count
        self._interval = interval

    def observe(self, question, options, chosen, should_store=False, on_poll=None):
        body = ""
        revealed = None
        decided = False

        for _ in range(self._poll_count):
            self._sleep(self._interval)
            body = self._read_body()
            if on_poll is not None:
                on_poll(body)

            if "Correct Answer" in body:
                spans = self._read_spans()
                if spans and spans[0].strip():
                    candidate = spans[0].strip()
                    revealed = match_option(candidate, options)
                decided = True
                break

            if "Energy" in body and "Incorrect" not in body:
                decided = True
                break

        if not decided:
            return Outcome(False, None, body, "no verdict within polling window")

        ok = "Correct Answer" not in body and "Incorrect" not in body and "Energy" in body
        truth = chosen if ok else revealed
        stored = False
        if should_store and truth and self._store is not None:
            self._store(question, options, truth)
            stored = True
        return Outcome(ok, revealed, body, stored=stored)
