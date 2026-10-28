"""Load job_profile.json and turn classifier paths (category.subcategory) into Facts."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from .models import Fact

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "profile" / "job_profile.json"
USD_INR = 83.0

# Country mentions in a question.
COUNTRY_PATTERNS: dict[str, re.Pattern[str]] = {
    k: re.compile(v, re.I)
    for k, v in {
        "india": r"\bindia\b|\bindian\b",
        "usa": r"\b(usa?|u\.s\.a?\.?|united states|america|american)\b",
        "uk": r"\b(uk|u\.k\.|united kingdom|britain|british|england)\b",
        "canada": r"\bcanad(a|ian)\b",
        "australia": r"\baustralia(n)?\b",
        "eu": r"\b(eu|european union|europe|eea|germany|german|france|french|netherlands|dutch|ireland|irish|"
              r"spain|italy|poland|sweden|portugal|belgium|austria|denmark|finland|norway|switzerland|swiss)\b",
        "singapore": r"\bsingapore\b",
        "uae": r"\b(uae|dubai|emirates)\b",
        "japan": r"\bjapan\b",
    }.items()
}

SKILL_UMBRELLA_TERMS = [
    "machine learning", "deep learning", "ml", "ai", "artificial intelligence", "nlp",
    "natural language processing", "generative ai", "genai", "llm", "llms", "large language models",
    "data science", "mlops", "cloud", "python", "sql", "rag", "agents", "ai agents", "agentic",
    "time series", "forecasting", "fine-tuning", "finetuning", "vector databases", "docker", "ci/cd",
    "aws", "gcp", "google cloud", "databricks", "huggingface", "hugging face", "openai api",
    "langchain", "langgraph", "fastapi", "postgres", "postgresql", "git", "github", "linux",
]

YEARS_RX = re.compile(r"years?|yrs|how long|how many", re.I)


def countries_in(text: str | None) -> list[str]:
    if not text:
        return []
    return [k for k, rx in COUNTRY_PATTERNS.items() if rx.search(text)]


def _age(dob: str) -> int | None:
    m = re.search(r"(\d{1,2})\W+([A-Za-z]+|\d{1,2})\W+(\d{4})", dob or "")
    if not m:
        return None
    d, mon, y = m.groups()
    months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    mm = months.index(mon[:3].lower()) + 1 if mon.isalpha() else int(mon)
    born = date(int(y), mm, int(d))
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def polarity_like(option: str) -> bool:
    """True for yes/no style options ('Yes', 'No', 'None', 'Not applicable')."""
    return bool(re.match(r"^\s*(yes|no|y|n|true|false|none|n/a|not applicable|prefer not|decline)\b", option, re.I))


def _yesno(value: bool, text: str | None = None, **kw: Any) -> Fact:
    return Fact(text=text or ("Yes" if value else "No"), boolean=value, **kw)


class Profile:
    """The applicant's profile, with lookups that return Facts."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_PROFILE
        self.data: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))

    # ---- raw access -------------------------------------------------------------------

    def get(self, *keys: str, default: Any = None) -> Any:
        cur: Any = self.data
        for k in keys:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                return default
        return cur

    def for_model(self) -> dict[str, Any]:
        """Profile as sent to jev / Claude (without the bookkeeping block)."""
        return {k: v for k, v in self.data.items() if not k.startswith("_")}

    @property
    def acceptable_cities(self) -> list[str]:
        return [c.lower() for c in self.get("work_preferences", "acceptable_onsite_hybrid_locations", default=[])]

    def mentions_acceptable_city(self, text: str | None) -> bool:
        t = (text or "").lower()
        for c in self.acceptable_cities:
            for part in re.split(r"[()/]", c):
                part = part.strip()
                if part and re.search(r"\b" + re.escape(part) + r"\b", t):
                    return True
        return bool(re.search(r"\b(ncr|delhi ncr)\b", t))

    @property
    def skills(self) -> list[str]:
        out: list[str] = []
        for v in self.get("skills", default={}).values():
            if isinstance(v, list):
                out.extend(v)
        return out

    @property
    def skill_terms(self) -> list[str]:
        """Skill names plus umbrella terms a form may use, lower-cased, longest first."""
        terms: set[str] = set(SKILL_UMBRELLA_TERMS)
        for s in self.skills:
            terms.add(s.lower())
            for part in re.split(r"[(),/+]", s):
                part = part.strip().lower()
                if len(part) > 1:
                    terms.add(part)
        return sorted(terms, key=len, reverse=True)

    # ---- facts ------------------------------------------------------------------------

    def fact_for(self, category: str, subcategory: str, question: str = "", context: str | None = None,
                 options: list[str] | None = None) -> Fact | None:
        """Fact for a classifier path such as ('contact', 'phone'). None when the profile has nothing."""
        cat = {"eeo_self_identification": "eeo", "work_preferences": "work_preference", "professional": "experience",
               "employment_history_checks": "employment_check", "documents": "document"}.get(category, category)
        fn = getattr(self, f"_fact_{cat}", None)
        if fn is None:
            return None
        fact = fn(subcategory, question, context, options or [])
        if fact is not None and not fact.rule:
            fact.rule = f"{cat}.{subcategory}"
        return fact

    def _text(self, *keys: str, **kw: Any) -> Fact | None:
        v = self.get(*keys)
        if v in (None, ""):
            return None
        return Fact(text=str(v), **kw)

    # personal ------------------------------------------------------------------------

    def _fact_personal(self, sub: str, q: str, ctx: str | None, opts: list[str]) -> Fact | None:
        p = self.data.get("personal", {})
        if sub == "date_of_birth":
            if re.search(r"\bage\b|how old", q, re.I):
                return self.age_fact()
            return self._text("personal", "date_of_birth")
        if sub == "gender":
            return self.gender_fact()
        if sub in ("nationality", "citizenship"):
            return self.citizenship_fact(q, ctx)
        if sub == "marital_status":
            return None
        return self._text("personal", sub)

    def age_fact(self) -> Fact | None:
        a = _age(self.get("personal", "date_of_birth", default=""))
        return Fact(text=str(a), number=float(a), unit="years") if a is not None else None

    def gender_fact(self) -> Fact:
        g = str(self.get("personal", "gender", default=""))
        return Fact(text=g, keywords=[g.lower(), "man" if g.lower() == "male" else "woman"])

    def citizenship_fact(self, q: str, ctx: str | None) -> Fact:
        cs = countries_in(q)
        others = [c for c in cs if c != "india"]
        if others and "india" not in cs:
            return Fact(text="No", boolean=False, reasoning=f"citizen of India, not {others[0]}")
        if re.search(r"\bcitizen", q, re.I):
            return Fact(text=self.get("personal", "citizenship", default="India"), boolean=True, keywords=["india", "indian"])
        return Fact(text=self.get("personal", "nationality", default="Indian"), boolean=True, keywords=["indian", "india"])

    # contact -------------------------------------------------------------------------

    def _fact_contact(self, sub: str, q: str, ctx: str | None, opts: list[str]) -> Fact | None:
        if sub == "confirm_email":
            sub = "email"
        if sub == "phone":
            return self.phone_fact(q)
        if sub == "social_profile":
            return Fact(text="N/A", confidence=0.6)
        if sub == "portfolio":
            return self._text("contact", "portfolio") or self._text("contact", "github")
        return self._text("contact", sub)

    def phone_fact(self, q: str) -> Fact | None:
        c = self.data.get("contact", {})
        if re.search(r"country code|dial", q, re.I) and not re.search(r"with|including", q, re.I):
            return Fact(text=c.get("phone_country_code", "+91"), keywords=["+91", "india"])
        if re.search(r"country code|international|with code|\+\d", q, re.I):
            return Fact(text=c.get("phone_international") or c.get("phone", ""))
        return self._text("contact", "phone")

    # address -------------------------------------------------------------------------

    def _fact_address(self, sub: str, q: str, ctx: str | None, opts: list[str]) -> Fact | None:
        a = self.data.get("address", {})
        if sub == "state":
            return Fact(text=a.get("state", ""), keywords=[a.get("state", "").lower()],
                        fallbacks=["foreign countries", "foreign country", "outside us", "outside the us", "outside united states",
                                   "non-us", "non us", "international", "other", "not applicable"],
                        reasoning="when the state list has no Indian states pick 'Foreign Countries' / 'Other'")
        if sub == "country":
            return Fact(text=a.get("country", ""), keywords=[a.get("country", "").lower(), "india"])
        if sub == "city":
            return Fact(text=a.get("city", ""), keywords=[a.get("city", "").lower()])
        return self._text("address", sub)

    # work authorization ----------------------------------------------------------------

    def _fact_work_authorization(self, sub: str, q: str, ctx: str | None, opts: list[str]) -> Fact | None:
        wa = self.data.get("work_authorization", {})
        if sub == "authorized_to_work":
            return self.authorized_fact(q, ctx)
        if sub == "requires_sponsorship":
            return self.sponsorship_fact(q, ctx)
        if sub == "current_visa_status":
            return self._text("work_authorization", "current_visa_status")
        if sub == "passport":
            return Fact(text="Indian passport", keywords=["india", "indian"])
        if sub == "citizenship_country":
            return self.citizenship_fact(q, ctx)
        if sub == "export_control":
            return Fact(text=wa.get("export_control_answer", "None"), boolean=False, keywords=["none", "not applicable", "no"])
        if sub == "security_clearance":
            v = str(wa.get("security_clearance", "No"))
            return Fact(text=v, boolean=v.lower().startswith("y"), confidence=0.7)
        if sub == "country_of_residence":
            return Fact(text=wa.get("country_of_residence", "India"), keywords=["india"])
        return None

    def authorized_fact(self, q: str, ctx: str | None) -> Fact:
        cs = countries_in(q) or countries_in(ctx)
        if "india" in cs:
            return Fact(text="Yes", boolean=True, reasoning="authorized to work in India")
        if cs:
            return Fact(text="No", boolean=False, reasoning=f"not authorized to work in {cs[0]} without sponsorship")
        return Fact(text="No", boolean=False, confidence=0.5, needs_review=True,
                    reasoning="country not stated; authorized only in India")

    def sponsorship_fact(self, q: str, ctx: str | None) -> Fact:
        cs = countries_in(q) or countries_in(ctx)
        if cs == ["india"]:
            return Fact(text="No", boolean=False, reasoning="no sponsorship needed in India")
        return Fact(text="Yes", boolean=True, keywords=["yes"],
                    long=self.get("work_authorization", "standard_answer"),
                    reasoning="needs visa sponsorship for roles outside India")

    # eeo -----------------------------------------------------------------------------

    def _fact_eeo(self, sub: str, q: str, ctx: str | None, opts: list[str]) -> Fact | None:
        e = self.data.get("eeo_self_identification", {})
        if sub == "gender":
            return self.gender_fact()
        if sub == "veteran_status":
            return Fact(text=e.get("veteran_status", "No"), boolean=False, keywords=["not a veteran", "not a protected veteran", "no"])
        if sub == "protected_veteran":
            return Fact(text="I am not a protected veteran", boolean=False, keywords=["not a protected veteran", "no"])
        if sub == "military_service":
            return Fact(text=e.get("military_service", "None"), boolean=False, keywords=["none", "no military", "no"])
        if sub == "disability_status":
            return Fact(text=e.get("disability_status", "No"), boolean=False, keywords=["do not have a disability", "no"])
        if sub == "race_ethnicity":
            return Fact(text=e.get("race_ethnicity_us_form", "Asian"), keywords=["asian", "indian", "south asian"])
        if sub == "religion":
            return self._text("eeo_self_identification", "religion")
        if sub == "sexual_orientation":
            return Fact(text=e.get("sexual_orientation", ""), keywords=["heterosexual", "straight"])
        if sub == "transgender_experience":
            return Fact(text="No", boolean=False)
        if sub == "accommodation":
            return Fact(text=e.get("accommodation_answer", "N/A"), boolean=False, keywords=["no"])
        return None

    # employment checks -------------------------------------------------------------------

    def _fact_employment_check(self, sub: str, q: str, ctx: str | None, opts: list[str]) -> Fact | None:
        yes = {"age_over_18", "background_check_consent", "drug_screening"}
        no = {"previously_worked_here", "previously_applied", "relatives_at_company", "non_compete",
              "government_procurement", "referral", "criminal_history"}
        if sub in yes:
            return _yesno(True)
        if sub in no:
            if sub == "referral" and re.search(r"^who|name", q, re.I):
                return Fact(text="N/A", boolean=False)
            return _yesno(False)
        return None

    # work preferences --------------------------------------------------------------------

    def _fact_work_preference(self, sub: str, q: str, ctx: str | None, opts: list[str]) -> Fact | None:
        wp = self.data.get("work_preferences", {})
        if sub in ("work_arrangement", "preferred_location"):
            return self.arrangement_fact(q, ctx)
        if sub == "willing_to_relocate":
            return self.relocate_fact(q, ctx)
        if sub == "willing_to_travel":
            return self.travel_fact(q)
        if sub == "employment_type":
            return self.employment_type_fact(q)
        if sub == "open_to_international":
            return _yesno(bool(wp.get("open_to_international_roles", True)))
        if sub == "schedule":
            return Fact(text="Yes, flexible (IST, comfortable working across time zones)", boolean=True, confidence=0.6)
        return None

    def arrangement_fact(self, q: str, ctx: str | None) -> Fact:
        ok_city = self.mentions_acceptable_city(q) or self.mentions_acceptable_city(ctx)
        asks_onsite = re.search(r"on-?site|in-?office|in person|hybrid|\boffice\b", q, re.I) and not re.search(r"remote", q, re.I)
        if asks_onsite:
            return Fact(text="Yes" if ok_city else "No", boolean=bool(ok_city),
                        keywords=["yes"] if ok_city else ["no", "remote"],
                        reasoning="onsite/hybrid only in Delhi NCR or Lucknow")
        items = ["Remote"] + (["Hybrid", "On-site"] if ok_city else [])
        return Fact(text="Remote", boolean=True, items=items,
                    keywords=["remote", "work from home", "wfh", "fully remote", "remote only"],
                    long=self.get("work_preferences", "preferred_work_arrangement_answer"))

    def relocate_fact(self, q: str, ctx: str | None) -> Fact:
        if self.mentions_acceptable_city(q) or self.mentions_acceptable_city(ctx):
            return Fact(text="Yes", boolean=True, reasoning="relocation within Delhi NCR / Lucknow is acceptable")
        return Fact(text="No", boolean=False, keywords=["no"],
                    long=self.get("common_form_answers", "Are you willing to relocate?"),
                    reasoning="relocates only to Delhi NCR or Lucknow; otherwise remote")

    def travel_fact(self, q: str) -> Fact:
        m = re.search(r"(\d{1,3})\s*%", q)
        if m and int(m.group(1)) > 25:
            return Fact(text="Yes", boolean=True, confidence=0.6, needs_review=True,
                        reasoning=f"travel {m.group(1)}% exceeds the 20% the profile confirms")
        return Fact(text="Yes", boolean=True)

    def employment_type_fact(self, q: str) -> Fact:
        items = list(self.get("work_preferences", "employment_types", default=["Full-time"]))
        lowered = q.lower()
        asked = [t for t in ("full-time", "full time", "part-time", "part time", "contract", "freelance",
                             "internship", "intern", "temporary") if t in lowered]
        if asked:
            ok = any(a.replace(" ", "-")[:4] in {i.lower()[:4] for i in items} for a in asked)
            return Fact(text="Yes" if ok else "No", boolean=ok, items=items, keywords=[i.lower() for i in items])
        return Fact(text=items[0], items=items, keywords=[i.lower() for i in items] + ["permanent"])

    # compensation -----------------------------------------------------------------------

    def _fact_compensation(self, sub: str, q: str, ctx: str | None, opts: list[str]) -> Fact | None:
        if sub == "current_ctc":
            return self.current_ctc_fact(q, ctx, opts)
        if sub == "expected_ctc":
            return self.expected_ctc_fact(q, ctx, opts)
        if sub == "currency":
            return Fact(text="INR", keywords=["inr", "rupee", "₹"])
        if sub == "salary_negotiable":
            return _yesno(bool(self.get("compensation", "salary_negotiable", default=True)))
        return None

    @staticmethod
    def currency_for(q: str, options: list[str] | None, ctx: str | None) -> str:
        blob = " ".join([q or ""] + list(options or []))
        if re.search(r"\$|\busd\b|dollar", blob, re.I):
            return "usd"
        if re.search(r"₹|\binr\b|\brs\.?\b|rupee|lpa|lakh|lac\b|crore", blob, re.I):
            return "inr"
        cs = countries_in(q) or countries_in(ctx)
        if cs and "india" not in cs:
            return "usd"
        return "inr"

    def current_ctc_fact(self, q: str, ctx: str | None, options: list[str] | None = None) -> Fact:
        inr = float(self.get("compensation", "current_ctc", "inr", default=0))
        if self.currency_for(q, options, ctx) == "usd":
            usd = round(inr / USD_INR)
            return Fact(text=f"{usd:,} USD", number=float(usd), unit="usd", reasoning="current CTC converted to USD")
        return Fact(text=self.get("compensation", "current_ctc", "amount", default=""), number=inr, unit="inr")

    def expected_ctc_fact(self, q: str, ctx: str | None, options: list[str] | None = None) -> Fact:
        exp = self.get("compensation", "expected_ctc", default={})
        intl = exp.get("international", {})
        cur = self.currency_for(q, options, ctx)
        cs = countries_in(q) or countries_in(ctx)
        international = cur == "usd" or (bool(cs) and "india" not in cs)
        if international:
            other_currency = re.search(r"€|\beur\b|euro|£|\bgbp\b|pound|\bcad\b|\baud\b|\bsgd\b|\baed\b|\bchf\b", " ".join([q] + list(options or [])), re.I)
            if cur == "usd":
                return Fact(text=intl.get("usd_approx", ""), number=float(intl.get("usd_min", 0)),
                            number_max=float(intl.get("usd_max", 0)), unit="usd",
                            needs_review=bool(other_currency), confidence=0.6 if other_currency else 0.9,
                            reasoning="international role: USD range" + ("; the form asks in another currency, convert before submitting" if other_currency else ""))
            return Fact(text=intl.get("range", ""), number=float(intl.get("inr_min", 0)),
                        number_max=float(intl.get("inr_max", 0)), unit="inr", reasoning="international role: INR range")
        india = exp.get("india", {})
        return Fact(text=india.get("amount", ""), number=float(india.get("inr", 0)), unit="inr",
                    long=exp.get("summary"), reasoning="India role")

    # availability -----------------------------------------------------------------------

    def _fact_availability(self, sub: str, q: str, ctx: str | None, opts: list[str]) -> Fact | None:
        av = self.data.get("availability", {})
        days = float(av.get("notice_period_days", 30))
        if sub == "notice_period":
            return Fact(text=av.get("notice_period", "1 month"), number=days, unit="days", long=av.get("standard_answer"))
        if sub == "earliest_start_date":
            return Fact(text=f"About {int(days)} days after accepting the offer", number=days, unit="days",
                        long=av.get("standard_answer"), keywords=["1 month", "one month", "30 days", "4 weeks"])
        if sub == "available_immediately":
            return _yesno(bool(av.get("available_immediately", False)))
        return None

    # education ---------------------------------------------------------------------------

    def _fact_education(self, sub: str, q: str, ctx: str | None, opts: list[str]) -> Fact | None:
        ed = (self.get("education", default=[{}]) or [{}])[0]
        if sub == "highest_education_level":
            return Fact(text=ed.get("highest_education_level", ""), keywords=["bachelor", "bachelors", "undergraduate"])
        if sub == "currently_enrolled":
            return _yesno(bool(ed.get("currently_enrolled", False)))
        if sub == "degree":
            return Fact(text=ed.get("degree", ""), keywords=["bachelor", "bba", "llb"])
        if sub == "institution":
            return Fact(text=ed.get("institution", ""), keywords=[ed.get("institution_short", "").lower()])
        if sub == "grade":
            digits = re.sub(r"[^\d.]", "", str(ed.get("grade", "")))
            return Fact(text=ed.get("grade", ""), number=float(digits) if digits else None)
        if sub in ("start_year", "graduation_year"):
            y = str(ed.get(sub, ""))
            return Fact(text=y, number=float(y) if y.isdigit() else None) if y else None
        v = ed.get(sub)
        return Fact(text=str(v)) if v else None

    # experience --------------------------------------------------------------------------

    def _fact_experience(self, sub: str, q: str, ctx: str | None, opts: list[str]) -> Fact | None:
        pro = self.data.get("professional", {})
        exp = self.get("experience", default=[]) or []
        if sub == "years_of_experience":
            y = float(pro.get("years_of_experience", 0))
            return Fact(text=str(int(y)), number=y, unit="years")
        if sub == "currently_employed":
            return _yesno(bool(pro.get("currently_employed", False)))
        if sub == "seniority_level":
            return Fact(text=pro.get("seniority_level", ""), keywords=["senior", "mid-level", "mid level", "mid"])
        if sub == "summary":
            return Fact(text=pro.get("headline", ""), long=pro.get("summary"))
        if sub == "past_title":
            return Fact(text=exp[1]["title"]) if len(exp) > 1 else None
        if sub == "past_company":
            return Fact(text=exp[1]["company"], items=[e["company"] for e in exp]) if len(exp) > 1 else None
        if sub == "past_dates":
            return Fact(text=f'{exp[1]["start_date"]} to {exp[1]["end_date"]}') if len(exp) > 1 else None
        if sub == "responsibilities":
            return Fact(text=exp[0]["bullets"][0], long=" ".join(exp[0]["bullets"])) if exp else None
        return self._text("professional", sub)

    # skills ------------------------------------------------------------------------------

    def _fact_skills(self, sub: str, q: str, ctx: str | None, opts: list[str]) -> Fact | None:
        sk = self.data.get("skills", {})
        if sub == "languages_spoken":
            return self.languages_fact(q)
        if sub == "specific_skill_experience":
            return self.specific_skill_fact(q, opts)
        if sub == "skill_list":
            return self.skill_list_fact()
        v = sk.get(sub)
        if isinstance(v, list):
            return Fact(text=", ".join(v), items=list(v), keywords=[s.lower() for s in v])
        return None

    def languages_fact(self, q: str) -> Fact:
        langs = self.get("languages", default=[]) or []
        text = ", ".join(f'{l["language"]} ({l["proficiency"]})' for l in langs)
        return Fact(text=text, items=[l["language"] for l in langs], boolean=True,
                    keywords=["professional", "fluent", "native", "advanced", "full professional"])

    def skill_list_fact(self) -> Fact:
        umbrella = ["Machine Learning", "Deep Learning", "Generative AI", "NLP", "MLOps", "Data Science", "LLMs"]
        return Fact(text=self.get("skills", "flat_list_comma_separated", default=""), items=self.skills + umbrella)

    def specific_skill_fact(self, q: str, options: list[str] | None = None) -> Fact:
        lowered = q.lower()
        hits = [t for t in self.skill_terms if re.search(r"(?<![\w+#])" + re.escape(t) + r"(?![\w+#])", lowered)]
        years = float(self.get("professional", "years_of_experience", default=0))
        asks_years = bool(YEARS_RX.search(lowered))
        if not hits and options and not all(polarity_like(o) for o in options):
            # "Which of the following have you worked with?" + a list of tools: tick the ones in the profile
            return self.skill_list_fact()
        if hits:
            if asks_years:
                return Fact(text=str(int(years)), number=years, unit="years", boolean=True, confidence=0.7,
                            reasoning=f"skill {hits[0]!r} is in the profile; total experience used")
            return Fact(text="Yes", boolean=True, reasoning=f"skill {hits[0]!r} is in the profile")
        if asks_years:
            return Fact(text="0", number=0.0, unit="years", boolean=False, confidence=0.5, needs_review=True,
                        reasoning="named tool not in profile")
        return Fact(text="No", boolean=False, confidence=0.5, needs_review=True, reasoning="named tool not in profile")

    # source / motivation / consent / document ----------------------------------------------

    def _fact_source(self, sub: str, q: str, ctx: str | None, opts: list[str]) -> Fact | None:
        if sub == "how_did_you_hear":
            src = str(self.get("form_filling_rules", "how_did_you_hear", default="LinkedIn"))
            return Fact(text=src, keywords=[src.lower(), "job board", "social media", "online"])
        if sub == "referred_by":
            return Fact(text="N/A", boolean=False)
        return None

    def _fact_motivation(self, sub: str, q: str, ctx: str | None, opts: list[str]) -> Fact | None:
        summary = self.get("professional", "summary", default="")
        if sub == "about_yourself":
            return Fact(text=summary, long=summary, essay=True, confidence=0.6)
        return Fact(essay=True, confidence=0.0, needs_review=True, reasoning="needs writing for this job")

    def _fact_consent(self, sub: str, q: str, ctx: str | None, opts: list[str]) -> Fact | None:
        return Fact(text="Yes", boolean=True, keywords=["agree", "accept", "yes", "i consent", "confirm"])

    def _fact_document(self, sub: str, q: str, ctx: str | None, opts: list[str]) -> Fact | None:
        if sub == "resume":
            return Fact(text=str(ROOT / "profile" / self.get("_meta", "source_resume", default="")),
                        needs_review=True, confidence=0.5, reasoning="file upload")
        return Fact(text="", needs_review=True, confidence=0.0, reasoning="file upload")
