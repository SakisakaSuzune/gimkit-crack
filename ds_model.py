"""LLM adapter with explicit, resolved settings and a structured result."""

import json
import os
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, Optional, Sequence

SYS = (
    "Answer multiple-choice trivia. Reply with ONLY the exact correct option text, "
    "copied verbatim. No explanation, no letter prefix."
)

DEFAULT_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-flash"
ENV_FILE = ".env.local"


@dataclass(frozen=True)
class Settings:
    api_url: str
    api_key: str
    model: str
    system: str = SYS


@dataclass(frozen=True)
class LLMResult:
    text: str
    usage: Dict = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _read_env(path):
    values = {}
    try:
        with open(path, encoding="utf-8") as source:
            for line in source:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    except OSError:
        pass
    return values


def load_settings(environ=None, script_dir=None, cwd=None):
    """Resolve each key independently: environment, script dir, cwd, default."""
    environ = os.environ if environ is None else environ
    script_dir = os.path.dirname(os.path.abspath(__file__)) if script_dir is None else script_dir
    cwd = os.getcwd() if cwd is None else cwd

    nearby = _read_env(os.path.join(script_dir, ENV_FILE))
    local = _read_env(os.path.join(cwd, ENV_FILE))

    def pick(key, default=""):
        return environ.get(key) or nearby.get(key) or local.get(key) or default

    return Settings(
        api_url=pick("BASE_URL", DEFAULT_URL),
        api_key=pick("API_KEY"),
        model=pick("MODEL", DEFAULT_MODEL),
    )


def ask(question, options: Sequence[str], settings: Optional[Settings] = None) -> LLMResult:
    settings = load_settings() if settings is None else settings
    if not settings.api_key:
        return LLMResult("", {}, "API_KEY missing (set it in .env.local)")

    user = question + "\nOptions: " + " | ".join(options)
    body = json.dumps(
        {
            "model": settings.model,
            "messages": [
                {"role": "system", "content": settings.system},
                {"role": "user", "content": user},
            ],
            "max_tokens": 60,
            "stream": False,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        settings.api_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + settings.api_key,
        },
    )

    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read())
            message = payload["choices"][0]["message"]
            content = (message.get("content") or "").strip().strip('"').strip()
            if not content:
                reasoning = message.get("reasoning_content") or ""
                for option in sorted(options, key=len, reverse=True):
                    if option and option.lower() in reasoning.lower():
                        content = option
                        break
            if not content and attempt < 2:
                time.sleep(0.5)
                continue
            return LLMResult(content, payload.get("usage", {}))
        except Exception as error:
            if attempt == 2:
                return LLMResult("", {}, str(error)[:60])
            time.sleep(1)
    return LLMResult("", {}, "empty response")
