"""Map a Fact onto the form's own option strings.

Three matchers, tried in order: numeric buckets ("$120,000-$149,999", "3-5 years"),
yes/no polarity ("No military service" counts as No), then text / keyword similarity.
"Decline to answer"-style options are never picked.
"""
from __future__ import annotations

import difflib
import math
import re

from .models import Fact
from .profile import USD_INR

DECLINE = re.compile(r"decline|prefer not|rather not|do not wish|don't wish|wish not|choose not|not to (answer|say|disclose|self)"
                     r"|don't want to|do not want to|unspecified|not specified|i don't know|not sure", re.I)
NEG = re.compile(r"^\s*(no|n|false|none|never|nope|nil)\b|\b(i am not|i'm not|i do not|i don't|i have not|i haven't|not a\b"
                 r"|not applicable|n/a|\bno\b|without)", re.I)
POS = re.compile(r"^\s*(yes|y|true|yep|agree|i agree|i accept|i confirm|i am|i'm|i have|i do|i identify|i consent)\b|\byes\b", re.I)

NUMBER = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(k\b|lakhs?|lacs?|lpa|\bl\b|cr\b|crores?|m\b|million|%)?", re.I)
LESS = re.compile(r"less than|under|below|up ?to|upto|fewer than|<|at most|maximum|max\.?\b|within", re.I)
MORE = re.compile(r"more than|over|above|\+|>|at least|or more|minimum|min\.?\b|greater than", re.I)
STOP = {"a", "an", "the", "of", "or", "and", "to", "in", "i", "am", "my", "degree", "level", "option"}


# ---- helpers ---------------------------------------------------------------------------

def normalize(s: str) -> str:
    s = s.lower().replace("'s", "").replace("’s", "")
    s = re.sub(r"[^a-z0-9+#$₹%./ -]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[\s/,()\-]+", normalize(s)) if t and t not in STOP}


def is_decline(opt: str) -> bool:
    return bool(DECLINE.search(opt))


def polarity(opt: str) -> bool | None:
    if is_decline(opt):
        return None
    if NEG.search(opt):
        return False
    if POS.search(opt):
        return True
    return None


def _multiplier(suffix: str | None, unit: str | None) -> float:
    s = (suffix or "").lower().rstrip(".")
    if s in ("k",):
        return 1e3
    if s in ("lakh", "lakhs", "lac", "lacs", "lpa", "l"):
        return 1e5
    if s in ("cr", "crore", "crores"):
        return 1e7
    if s in ("m", "million"):
        return 1e6
    return 1.0


def _option_currency(opt: str) -> str | None:
    if re.search(r"\$|\busd\b|dollar", opt, re.I):
        return "usd"
    if re.search(r"₹|\binr\b|\brs\.?|rupee|lpa|lakh|lac\b|crore", opt, re.I):
        return "inr"
    return None


def _time_scale(opt: str, unit: str) -> float:
    """Factor that converts the option's time unit into the fact's unit (days or years)."""
    o = opt.lower()
    if unit == "days":
        if "month" in o:
            return 30.0
        if "week" in o:
            return 7.0
        if "year" in o:
            return 365.0
        return 1.0
    if unit == "years":
        if "month" in o:
            return 1 / 12
        if "week" in o:
            return 1 / 52
        return 1.0
    return 1.0


def parse_range(opt: str, unit: str | None) -> tuple[float, float] | None:
    """Numeric interval an option covers, in the fact's unit. None when the option has no number."""
    o = opt.lower()
    if unit == "days" and re.search(r"immediate|right away|asap|available now", o):
        return (0.0, 0.0)
    if unit == "years" and re.search(r"fresher|no experience|entry[- ]level|none", o):
        return (0.0, 0.0)
    nums = [(float(n.replace(",", "")), suf) for n, suf in NUMBER.findall(o) if n]
    nums = [(v, s) for v, s in nums if s != "%" or unit == "percent"]
    if not nums:
        return None
    scale = _time_scale(o, unit) if unit in ("days", "years") else 1.0
    if unit in ("inr", "usd"):
        mult = max(_multiplier(s, unit) for _, s in nums)  # "20-30 LPA": the suffix after the last number applies to both
        vals = [v * (_multiplier(s, unit) if s else mult) for v, s in nums]
        cur = _option_currency(opt)
        if cur and cur != unit:
            vals = [v * (USD_INR if (cur == "usd" and unit == "inr") else 1 / USD_INR) for v in vals]
    else:
        vals = [v * scale for v, _ in nums]
    if len(vals) >= 2:
        return (min(vals[0], vals[1]), max(vals[0], vals[1]))
    v = vals[0]
    if LESS.search(o):
        return (0.0, v)
    if MORE.search(o):
        return (v, math.inf)
    return (v, v)


# ---- matchers --------------------------------------------------------------------------

def match_numeric(fact: Fact, options: list[str]) -> tuple[str, float, str] | None:
    if fact.number is None:
        return None
    lo_f, hi_f = fact.number, fact.number_max if fact.number_max is not None else fact.number
    parsed = [(o, parse_range(o, fact.unit)) for o in options if not is_decline(o)]
    parsed = [(o, r) for o, r in parsed if r is not None]
    if not parsed:
        return None
    best: tuple[str, float, str] | None = None
    for o, (lo, hi) in parsed:
        if lo <= lo_f <= hi or lo <= hi_f <= hi or (lo_f <= lo and hi <= hi_f):
            # containment: for an exact-value option prefer the tightest bucket
            width = (hi - lo) if math.isfinite(hi) else 1e18
            score = 1.0 - min(width / max(abs(hi_f) + 1, 1), 0.3) * 0.1
            if lo_f == lo and lo > 0:  # "5-8 years" means 5 or more: a boundary value belongs to the upper bucket
                score = min(1.0, score + 0.05)
            cand = (o, round(score, 3), f"{fact.short()} falls in '{o}'")
        else:
            gap = min(abs(lo - hi_f), abs(hi - lo_f)) if math.isfinite(hi) else abs(lo - hi_f)
            rel = gap / max(abs(hi_f), 1)
            cand = (o, round(max(0.3, 0.6 - rel), 3), f"nearest bucket to {fact.short()}")
        if best is None or cand[1] > best[1]:
            best = cand
    return best


def match_boolean(fact: Fact, options: list[str]) -> tuple[str, float, str] | None:
    if fact.boolean is None:
        return None
    hits = [o for o in options if polarity(o) is fact.boolean]
    if not hits:
        return None
    hits.sort(key=len)
    return hits[0], 0.95, f"{'yes' if fact.boolean else 'no'} polarity"


def text_score(candidate: str, opt: str) -> float:
    c, o = normalize(candidate), normalize(opt)
    if not c or not o:
        return 0.0
    if c == o:
        return 1.0
    ct, ot = tokens(c), tokens(o)
    if ct and ot and (ct <= ot or ot <= ct):
        return 0.9
    if re.search(r"(?<![\w])" + re.escape(c) + r"(?![\w])", o):
        return 0.85
    ratio = difflib.SequenceMatcher(None, c, o).ratio()
    return ratio if ratio >= 0.86 else 0.0


def match_text(fact: Fact, options: list[str]) -> tuple[str, float, str] | None:
    candidates = [c for c in [fact.text] + fact.keywords + fact.items if c]
    best: tuple[str, float, str] | None = None
    for o in options:
        if is_decline(o):
            continue
        for c in candidates:
            s = text_score(c, o)
            if s >= 0.6 and (best is None or s > best[1]):
                best = (o, round(s, 3), f"matches '{c}'")
    if best is None and fact.fallbacks:
        for o in options:
            for c in fact.fallbacks:
                if text_score(c, o) >= 0.85:
                    return o, 0.7, f"fallback '{c}'"
    return best


def match_multi(fact: Fact, options: list[str]) -> tuple[list[str], float, str]:
    wanted = [c for c in fact.items + fact.keywords if c] or ([fact.text] if fact.text else [])
    picked: list[str] = []
    for o in options:
        if is_decline(o):
            continue
        if any(text_score(c, o) >= 0.8 for c in wanted):
            picked.append(o)
    if picked:
        return picked, 0.9, "ticked every option that is in the profile"
    single = select(fact, options)
    if single:
        return [single[0]], single[1] * 0.9, single[2]
    return [], 0.0, "no option matches the profile"


def select(fact: Fact, options: list[str]) -> tuple[str, float, str] | None:
    """Best single option for a Fact, or None."""
    for m in (match_numeric, match_boolean, match_text):
        r = m(fact, options)
        if r:
            return r
    # a boolean fact with a text-only option list: a "yes" fact may still name the matching option
    return None
