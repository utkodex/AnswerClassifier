"""Claude writes the free-text answers no rule covers: essays and unusual short questions.

Needs ANTHROPIC_API_KEY in .env. The profile sits in a cached system prompt; each call
asks for one answer and nothing else. Server-side refusal fallbacks are enabled by
default so a safety decline is retried on another model inside the same request.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from .models import Question

DEFAULT_MODEL = "claude-opus-5-5"
MODEL_ENV_VARS = ("JOBANSWER_MODEL",)

SYSTEM = """You fill in job-application forms for the applicant described in the JSON profile below.
Write in the first person as the applicant. Use only facts from the profile; never invent employers,
dates, numbers or credentials. Follow the profile's rules: remote work preferred (hybrid/onsite only in
Delhi NCR or Lucknow), needs visa sponsorship outside India, 1-month notice period.

Reply with ONLY the text that goes into the form field. No preamble, no quotes, no markdown.

APPLICANT PROFILE (JSON):
"""


@dataclass
class LLMResult:
    text: str
    model: str
    refused: bool = False


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover
        return
    from pathlib import Path

    for p in (Path.cwd() / ".env", Path(__file__).resolve().parents[1] / ".env"):
        if p.is_file():
            load_dotenv(p, override=False)


def resolve_model(model: str | None) -> str:
    if model:
        return model
    for var in MODEL_ENV_VARS:
        v = os.environ.get(var, "").strip()
        if v:
            return v
    return DEFAULT_MODEL


def has_key() -> bool:
    _load_env()
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


class ClaudeWriter:
    """`client` can be any object whose `.beta.messages.create(**kw)` / `.messages.create(**kw)` returns a Message."""

    def __init__(self, profile: dict[str, Any], *, client: Any | None = None, model: str | None = None,
                 api_key: str | None = None) -> None:
        _load_env()
        self.model = resolve_model(model)
        self.system_text = SYSTEM + json.dumps(profile, ensure_ascii=False, sort_keys=True)
        if client is None:
            import anthropic

            key = api_key or os.environ.get("ANTHROPIC_API_KEY", "").strip()
            if not key:
                raise RuntimeError("ANTHROPIC_API_KEY is not set; put it in .env or pass api_key=")
            client = anthropic.Anthropic(api_key=key)
        self.client = client

    def answer(self, q: Question, *, hint: str | None = None, essay: bool = False) -> LLMResult:
        parts = [f"Form field: {q.text}"]
        if q.choices:
            parts.append("Options: " + " | ".join(q.choices))
            parts.append("Reply with the exact option text" + (" (several, separated by ' | ')" if q.kind == "multi" else "") + ".")
        if q.context:
            parts.append(f"Job context: {q.context}")
        if hint:
            parts.append(f"What the profile says (use it): {hint}")
        if essay:
            parts.append("Write 90-150 words, specific to the profile, confident but not boastful.")
        else:
            parts.append("Keep it short: a word, a number, a name or one sentence, whatever the field expects.")
        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=1024 if essay else 200,
            system=[{"type": "text", "text": self.system_text, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": "\n".join(parts)}],
            output_config={"effort": "medium" if essay else "low"},
        )
        try:
            msg = self.client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
            )
        except TypeError:  # older SDK without server-side fallbacks
            msg = self.client.messages.create(**kwargs)
        if getattr(msg, "stop_reason", "") == "refusal":
            return LLMResult(text="", model=getattr(msg, "model", self.model), refused=True)
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        return LLMResult(text=text, model=getattr(msg, "model", self.model))
