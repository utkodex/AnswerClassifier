"""Offline tests for the jobanswer engine (rules + option mapping); the jev path uses a fake client."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobanswer import Engine, Question  # noqa: E402
from jobanswer import matching  # noqa: E402
from jobanswer.models import Fact  # noqa: E402


@pytest.fixture(scope="module")
def eng() -> Engine:
    return Engine(use_jev="never", use_llm="never")


def ask(eng: Engine, text: str, options: list[str] | None = None, **kw):
    return eng.answer(Question(text=text, options=list(options or []), **kw))


# ---- short answers ---------------------------------------------------------------------

@pytest.mark.parametrize("q, expected", [
    ("What is your name?", "Utkarsh Sinha"),
    ("First name", "Utkarsh"),
    ("Last name", "Sinha"),
    ("Email address", "sinhautkarshgc@gmail.com"),
    ("Phone number", "9044657997"),
    ("Phone number with country code", "+91 9044657997"),
    ("LinkedIn profile", "https://linkedin.com/in/smm-utkarsh-sinha"),
    ("City", "Kanpur"),
    ("Zip / Postal code", "208023"),
    ("Country", "India"),
    ("What is your notice period?", "1 month"),
    ("Current company", "Aztra AI"),
    ("Current job title", "Data Scientist & GenAI Engineer"),
    ("Total years of experience", "5"),
    ("Expected CTC", "24 LPA"),
    ("Current CTC", "9 LPA"),
    ("How did you hear about this position?", "LinkedIn"),
    ("Highest level of education", "Bachelor's degree"),
    ("University / College", "Guru Gobind Singh Indraprastha University"),
    ("Graduation year", "2021"),
    ("Nationality", "Indian"),
    ("Gender", "Male"),
    ("Pronouns", "He/Him"),
])
def test_short_text_answers(eng, q, expected):
    a = ask(eng, q)
    assert a.answer == expected, (q, a)
    assert not a.needs_review


def test_short_answer_is_short_not_a_sentence(eng):
    a = ask(eng, "When can you start?")
    assert len(a.answer) < 60 and "30 days" in a.answer


def test_textarea_gets_the_long_form(eng):
    a = ask(eng, "What is your notice period?", qtype="textarea")
    assert "1-month notice" in a.answer


def test_expected_salary_in_usd_context(eng):
    a = ask(eng, "Expected salary", context="Senior ML Engineer, Acme, San Francisco, USA")
    assert "USD" in a.answer


def test_age_is_computed_from_dob(eng):
    a = ask(eng, "Age")
    assert a.answer.isdigit() and 25 <= int(a.answer) <= 40


# ---- yes / no ---------------------------------------------------------------------------

@pytest.mark.parametrize("q, expected", [
    ("Are you willing to relocate?", "No"),
    ("Are you willing to relocate to Noida?", "Yes"),
    ("Do you require visa sponsorship?", "Yes"),
    ("Will you now or in the future require sponsorship for employment visa status?", "Yes"),
    ("Are you legally authorized to work in India?", "Yes"),
    ("Are you legally authorized to work in the United States?", "No"),
    ("Are you authorized to work in the UK?", "No"),
    ("Are you 18 years of age or older?", "Yes"),
    ("Have you previously worked for this company?", "No"),
    ("Do you have relatives employed at this company?", "No"),
    ("Are you currently employed?", "Yes"),
    ("Are you a veteran?", "No"),
    ("Do you have a disability?", "No"),
    ("Are you open to working remotely?", "Yes"),
    ("Are you willing to work onsite in Bangalore?", "No"),
    ("Are you willing to work from our Gurgaon office?", "Yes"),
    ("Are you willing to travel up to 20%?", "Yes"),
    ("Do you have experience with Python?", "Yes"),
    ("Do you have experience with LangChain?", "Yes"),
    ("Do you hold a security clearance?", "Yes"),
    ("Are you a US citizen?", "No"),
    ("Are you currently a student?", "No"),
    ("Can you join immediately?", "No"),
    ("Do you agree to the privacy policy?", "Yes"),
    ("Are you open to part-time work?", "No"),
    ("Are you open to contract roles?", "Yes"),
])
def test_yes_no(eng, q, expected):
    a = ask(eng, q, ["Yes", "No"])
    assert a.selected_options == [expected], (q, a)
    assert a.answer == expected
    assert not a.needs_review


def test_boolean_type_without_options(eng):
    a = ask(eng, "Do you require sponsorship?", qtype="boolean")
    assert a.answer == "Yes" and a.selected_options == ["Yes"]


def test_unknown_tool_is_flagged(eng):
    a = ask(eng, "Do you have experience with COBOL?", ["Yes", "No"])
    assert a.selected_options == ["No"] and a.needs_review


def test_authorization_without_country_is_flagged(eng):
    a = ask(eng, "Are you legally authorized to work in the country of this job?", ["Yes", "No"])
    assert a.needs_review


# ---- option wording -----------------------------------------------------------------------

def test_veteran_long_options(eng):
    opts = ["I identify as one or more of the classifications of a protected veteran",
            "I am not a protected veteran", "I don't wish to answer"]
    a = ask(eng, "Protected veteran status", opts)
    assert a.selected_options == ["I am not a protected veteran"]


def test_disability_avoids_decline(eng):
    opts = ["Yes, I have a disability, or have a history/record of having a disability",
            "No, I do not have a disability", "I do not want to answer"]
    assert ask(eng, "Disability status", opts).selected_options == ["No, I do not have a disability"]


def test_military_service_polarity(eng):
    assert ask(eng, "Military service", ["Served in the military", "No military service"]).selected_options == ["No military service"]


def test_gender_does_not_pick_female(eng):
    assert ask(eng, "Gender", ["Female", "Male", "Non-binary", "Decline to self-identify"]).selected_options == ["Male"]


def test_race(eng):
    opts = ["Hispanic or Latino", "White", "Black or African American", "Asian", "Two or More Races", "Decline"]
    assert ask(eng, "Race / Ethnicity", opts).selected_options == ["Asian"]


def test_education_level_options(eng):
    opts = ["High School", "Associate's Degree", "Bachelor's Degree", "Master's Degree", "Doctorate"]
    assert ask(eng, "Highest level of education", opts).selected_options == ["Bachelor's Degree"]


def test_work_arrangement_options(eng):
    assert ask(eng, "Preferred work arrangement", ["On-site", "Hybrid", "Remote"]).selected_options == ["Remote"]


def test_how_did_you_hear_options(eng):
    opts = ["Company website", "LinkedIn", "Indeed", "Referral", "Other"]
    assert ask(eng, "How did you hear about us?", opts).selected_options == ["LinkedIn"]


def test_state_dropdown_without_indian_states(eng):
    opts = ["Alabama", "California", "New York", "Texas", "Foreign Countries"]
    a = ask(eng, "State", opts)
    assert a.selected_options == ["Foreign Countries"]


def test_state_dropdown_with_indian_state(eng):
    assert ask(eng, "State", ["Karnataka", "Uttar Pradesh", "Delhi"]).selected_options == ["Uttar Pradesh"]


def test_country_dropdown(eng):
    assert ask(eng, "Country", ["United States", "United Kingdom", "India", "Other"]).selected_options == ["India"]


# ---- numeric buckets ----------------------------------------------------------------------

def test_notice_period_buckets(eng):
    opts = ["Immediate", "15 days", "30 days", "60 days", "90 days"]
    assert ask(eng, "Notice period", opts).selected_options == ["30 days"]


def test_notice_period_month_buckets(eng):
    assert ask(eng, "Notice period", ["Immediate", "Less than 1 month", "1 month", "2 months", "3+ months"]).selected_options == ["1 month"]


def test_experience_buckets(eng):
    assert ask(eng, "Years of experience", ["0-1 years", "1-3 years", "3-5 years", "5-8 years", "8+ years"]).selected_options == ["5-8 years"]


def test_experience_plus_bucket(eng):
    assert ask(eng, "How many years of experience do you have?", ["Less than 2", "2-4", "5+"]).selected_options == ["5+"]


def test_salary_lpa_buckets(eng):
    assert ask(eng, "Expected CTC", ["5-10 LPA", "10-15 LPA", "15-20 LPA", "20-30 LPA", "30+ LPA"]).selected_options == ["20-30 LPA"]


def test_current_ctc_lpa_buckets(eng):
    assert ask(eng, "Current CTC", ["Less than 5 LPA", "5-10 LPA", "10-20 LPA"]).selected_options == ["5-10 LPA"]


def test_salary_usd_buckets(eng):
    opts = ["$60,000-$89,999", "$90,000-$119,999", "$120,000-$149,999", "$150,000+"]
    a = ask(eng, "What are your salary expectations?", opts)
    assert a.selected_options in (["$60,000-$89,999"], ["$90,000-$119,999"])


def test_start_date_buckets(eng):
    assert ask(eng, "When could you start?", ["Immediately", "Within 2 weeks", "Within 1 month", "2-3 months"]).selected_options == ["Within 1 month"]


# ---- multi-select ---------------------------------------------------------------------------

def test_employment_type_multi(eng):
    a = ask(eng, "Which employment types are you open to?", ["Full-time", "Part-time", "Contract", "Internship", "Freelance"], multi=True)
    assert a.selected_options == ["Full-time", "Contract", "Freelance"]
    assert a.answer == "Full-time; Contract; Freelance"


def test_skills_multi(eng):
    a = ask(eng, "Which of the following skills do you have?", ["Python", "Java", "PyTorch", "Docker", "Rust", "AWS"], multi=True)
    assert a.selected_options == ["Python", "PyTorch", "Docker", "AWS"]


def test_work_setting_multi(eng):
    a = ask(eng, "Which work settings are you open to?", ["Remote", "Hybrid", "On-site"], multi=True)
    assert a.selected_options == ["Remote"]


def test_languages_multi(eng):
    a = ask(eng, "Which languages do you speak?", ["English", "Hindi", "French", "German"], multi=True)
    assert a.selected_options == ["English", "Hindi"]


# ---- essays and unknowns ------------------------------------------------------------------------

def test_essay_offline_is_flagged(eng):
    a = ask(eng, "Why do you want to work at our company?")
    assert a.needs_review and a.answer == ""


def test_about_yourself_offline_uses_summary(eng):
    a = ask(eng, "Tell us about yourself")
    assert "Data Scientist" in a.answer and a.needs_review


def test_unknown_question_is_flagged(eng):
    a = ask(eng, "What is your favourite colour?")
    assert a.needs_review and a.answer == ""


# ---- batch and json --------------------------------------------------------------------------

def test_answer_many_keeps_order_and_ids(eng):
    qs = [Question("Email", id="a"), Question("Gender", ["Male", "Female"], id="b"), Question("Notice period", id="c")]
    out = eng.answer_many(qs)
    assert [a.id for a in out] == ["a", "b", "c"]
    d = out[1].to_dict()
    assert d["selected_options"] == ["Male"] and d["needs_review"] is False


# ---- matching unit tests ----------------------------------------------------------------------

def test_parse_range():
    assert matching.parse_range("$120,000-$149,999", "usd") == (120000.0, 149999.0)
    assert matching.parse_range("20-30 LPA", "inr") == (2000000.0, 3000000.0)
    assert matching.parse_range("Less than 1 year", "years") == (0.0, 1.0)
    assert matching.parse_range("10+ years", "years")[0] == 10.0
    assert matching.parse_range("2 months", "days") == (60.0, 60.0)
    assert matching.parse_range("Immediate", "days") == (0.0, 0.0)
    assert matching.parse_range("Other", "days") is None


def test_polarity():
    assert matching.polarity("Yes") is True
    assert matching.polarity("No") is False
    assert matching.polarity("No military service") is False
    assert matching.polarity("I am not a protected veteran") is False
    assert matching.polarity("I identify as a protected veteran") is True
    assert matching.polarity("Decline to answer") is None


def test_select_prefers_numeric_then_boolean_then_text():
    f = Fact(text="1 month", number=30, unit="days", boolean=True)
    assert matching.select(f, ["15 days", "30 days"])[0] == "30 days"
    assert matching.select(f, ["Yes", "No"])[0] == "Yes"
    assert matching.select(Fact(text="Remote", keywords=["remote"]), ["Office", "Remote work"])[0] == "Remote work"


# ---- jev path with a fake client -----------------------------------------------------------------

class FakeJev:
    """Picks the option whose text contains 'yes'/'no' per a fixed table, or the first option."""

    def __init__(self, prefer: dict[str, str] | None = None):
        self.prefer = prefer or {}
        self.calls = 0

    def system_one(self, state, questions, model=None):
        if "form_fields" not in state:  # the category / sub-category classifiers: low-confidence first label
            out = {}
            for name, q in questions.items():
                labels = list(q.criteria)
                pick = "other" if "other" in labels else labels[0]
                out[name] = SimpleNamespace(choice=pick, confidence=0.3, probabilities={lbl: 0.0 for lbl in labels})
            return SimpleNamespace(model="jev-fake", choices=out)
        self.calls += 1
        answers = {}
        for name, q in questions.items():
            if getattr(q, "type", "") == "choice":
                field = state["form_fields"][name]
                want = self.prefer.get(field["question"])
                labels = list(q.criteria)
                pick = next((lbl for lbl in labels if q.criteria[lbl] == want), labels[0])
                probs = {lbl: (0.9 if lbl == pick else 0.1 / max(len(labels) - 1, 1)) for lbl in labels}
                answers[name] = SimpleNamespace(type="choice", choice=pick, confidence=0.9, probabilities=probs)
            else:
                base = name.rsplit("_o", 1)[0]
                field = state["form_fields"][base]
                opt = field["options"][int(name.rsplit("_o", 1)[1])]
                answers[name] = SimpleNamespace(type="noul", noul=0.9 if opt in self.prefer.get(field["question"], "") else 0.1)
        choices = {k: v for k, v in answers.items() if v.type == "choice"}
        nouls = {k: v for k, v in answers.items() if v.type == "noul"}
        return SimpleNamespace(model="jev-fake", choices=choices, nouls=nouls)


def test_jev_agreement_raises_confidence():
    fake = FakeJev({"Are you willing to relocate?": "No"})
    e = Engine(use_jev="auto", use_llm="never", jev_client=fake)
    a = ask(e, "Are you willing to relocate?", ["Yes", "No"])
    assert a.selected_options == ["No"] and a.source == "jev" and a.confidence > 0.9 and not a.needs_review
    assert a.probabilities["No"] == 0.9


def test_jev_agreement_keeps_the_review_flag_for_unknown_tools():
    fake = FakeJev({"Do you have experience with COBOL?": "No"})
    e = Engine(use_jev="auto", use_llm="never", jev_client=fake)
    a = ask(e, "Do you have experience with COBOL?", ["Yes", "No"])
    assert a.selected_options == ["No"] and a.needs_review


def test_skill_in_profile_is_yes(eng):
    a = ask(eng, "Do you have experience with Kubernetes?", ["Yes", "No"])
    assert a.selected_options == ["Yes"] and not a.needs_review


def test_worked_with_multi_uses_profile_skills(eng):
    a = ask(eng, "Which of the following have you worked with?", ["Docker", "Kubernetes", "Scala", "AWS"], multi=True)
    assert a.selected_options == ["Docker", "Kubernetes", "AWS"]


def test_eur_salary_is_flagged():
    e = Engine(use_jev="never", use_llm="never")
    a = ask(e, "Expected annual salary (EUR)", context="ML Engineer, Acme, Berlin, Germany")
    assert "USD" in a.answer and a.needs_review


def test_jev_disagreement_is_flagged_and_rule_wins():
    fake = FakeJev({"Are you willing to relocate?": "Yes"})
    e = Engine(use_jev="auto", use_llm="never", jev_client=fake)
    a = ask(e, "Are you willing to relocate?", ["Yes", "No"])
    assert a.selected_options == ["No"] and a.needs_review and "jev picked" in a.reasoning


def test_jev_answers_when_no_rule_matches():
    fake = FakeJev({"Pick your favourite colour": "Blue"})
    e = Engine(use_jev="auto", use_llm="never", jev_client=fake)
    a = ask(e, "Pick your favourite colour", ["Red", "Blue"])
    assert a.selected_options == ["Blue"] and a.source == "jev"


def test_jev_multi_select():
    fake = FakeJev({"Which employment types are you open to?": "Full-time Contract Freelance"})
    e = Engine(use_jev="auto", use_llm="never", jev_client=fake)
    a = ask(e, "Which employment types are you open to?", ["Full-time", "Part-time", "Contract", "Freelance"], multi=True)
    assert a.selected_options == ["Full-time", "Contract", "Freelance"] and a.source == "jev"


def test_jev_batches_many_questions_in_one_call():
    fake = FakeJev()
    e = Engine(use_jev="auto", use_llm="never", jev_client=fake)
    e.answer_many([Question(f"Question {i}", ["A", "B"]) for i in range(10)])
    assert fake.calls == 1
