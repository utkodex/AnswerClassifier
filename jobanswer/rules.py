"""Deterministic, offline question -> profile-field rules.

Each rule maps a question phrasing to the same `category.subcategory` path the jev
classifiers produce, so `Profile.fact_for` answers both. Order matters: the first match
wins, so specific phrasings come before generic ones.
"""
from __future__ import annotations

import re

from .models import Fact, Question
from .profile import Profile

RULES: list[tuple[str, re.Pattern[str]]] = [
    (path, re.compile(rx, re.I))
    for path, rx in [
        # --- consent / legal ----------------------------------------------------------
        ("employment_check.age_over_18", r"\b18\b.*(older|over|above|age)|at least 18|legal (working )?age|\bover 18\b|\b18\+"),
        ("consent.privacy_policy", r"privacy (policy|notice|statement)|data (processing|protection)|gdpr"),
        ("consent.data_retention", r"(keep|retain|store).*(data|information|profile|cv|resume).*(future|talent|pool|months|years)|talent (pool|community)"),
        ("consent.contact_consent", r"(consent|agree|ok|okay|happy).*(contact|email|sms|text|call|phone)|opt[- ]?in"),
        ("consent.certification_true", r"certify|(information|answers).*(true|accurate|correct|complete)|attest"),
        ("consent.terms_agreement", r"terms (and|&) conditions|terms of (use|service)|\bi agree\b|acknowledge|\bagree to\b"),
        # --- work authorization ----------------------------------------------------------
        ("work_authorization.export_control", r"export control|sanction|\b(cuba|iran|north korea|syria)\b"),
        ("work_authorization.requires_sponsorship", r"sponsor"),
        ("work_authorization.authorized_to_work", r"(authori[sz]ed|eligible|permitted|legally able|right|allowed) to work|work authori[sz]ation|work permit|eligib(le|ility) (for|to) employment|legally (work|employ)"),
        ("work_authorization.current_visa_status", r"visa (status|type)|immigration status|work visa|permanent resident|green card|\bh-?1b\b"),
        ("work_authorization.security_clearance", r"security clearance|\bclearance\b"),
        ("work_authorization.passport", r"passport"),
        ("work_authorization.citizenship_country", r"citizen|nationality|national of"),
        ("work_authorization.country_of_residence", r"country (of|you) (reside|residence|live|currently)|where (do you|are you) (currently )?(live|reside|based)|based in|country of (current )?residence"),
        # --- EEO ------------------------------------------------------------------------
        ("eeo.transgender_experience", r"transgender"),
        ("eeo.protected_veteran", r"protected veteran"),
        ("eeo.veteran_status", r"veteran"),
        ("eeo.military_service", r"military|armed forces"),
        ("eeo.disability_status", r"disabilit|disabled|impairment"),
        ("eeo.accommodation", r"accommodation|adjustments|support (is )?needed|assistance (during|with) (the )?(application|interview)"),
        ("eeo.race_ethnicity", r"\brace\b|ethnic|racial"),
        ("eeo.sexual_orientation", r"sexual orientation|orientation"),
        ("eeo.religion", r"religion|religious|faith|belief"),
        ("personal.pronouns", r"pronoun"),
        ("personal.gender", r"\bgender\b|\bsex\b|identify as"),
        # --- employment / conflict checks ---------------------------------------------------
        ("employment_check.relatives_at_company", r"relative|family member|spouse|immediate family|related to (any|an) (employee|anyone)"),
        ("employment_check.non_compete", r"non-?compete|non-?solicit|restrictive (covenant|agreement)|restrict(s|ed)? (you|your ability)"),
        ("employment_check.government_procurement", r"government (official|employee|procurement|contract)|procurement|public official|government agency"),
        ("source.referred_by", r"^(who|name of).*(refer)|referrer'?s? name|referring employee|employee who referred"),
        ("employment_check.referral", r"\breferr(al|ed|er|ing)\b"),
        ("employment_check.previously_worked_here", r"(previously|ever|before|formerly|past).*(worked|employed|been employed|employee)|former employee|worked (for|at|with) (us|this company|the company|our company)|(current|former) employee of"),
        ("employment_check.previously_applied", r"(previously|ever|before).*appl(y|ied)|applied (to|with|for) (us|this company|the company)"),
        ("employment_check.background_check", r"background (check|verification|screening|investigation)"),
        ("employment_check.criminal_history", r"convict|criminal|felony|offen[cs]e|misdemean"),
        ("employment_check.drug_screening", r"drug (test|screen)"),
        # --- source ----------------------------------------------------------------------
        ("source.how_did_you_hear", r"how did you (hear|find|learn|come)|hear about|source of (application|referral|hire)|where did you (find|see|hear|learn)|how were you (referred|introduced)|lead source"),
        # --- compensation -----------------------------------------------------------------
        ("compensation.salary_negotiable", r"negotiable"),
        ("compensation.current_ctc", r"(current|present|existing|last drawn|drawing).{0,25}(ctc|salary|compensation|\bpay\b|package|remuneration)|(ctc|salary|compensation).{0,15}(current|present|drawing)"),
        ("compensation.expected_ctc", r"(expected|desired|target|preferred|anticipated|minimum|required).{0,25}(ctc|salary|compensation|\bpay\b|package|remuneration|rate)|(salary|compensation|pay).{0,15}(expectation|requirement|range|desired|expected)|how much.*(expect|want|looking)|\bctc\b"),
        ("compensation.currency", r"\bcurrency\b"),
        # --- availability -------------------------------------------------------------------
        ("availability.notice_period", r"notice period|\bnotice\b"),
        ("availability.available_immediately", r"immediate(ly)? (join|start|availab)|join(ing)? immediately|immediate joiner"),
        ("availability.earliest_start_date", r"(when|how soon).*(start|join|available|begin)|start(ing)? date|date (you are |you'?re )?available|availab(le|ility) (to|for) (start|join|work)|earliest.*(start|join|date)|joining (date|time)|\bavailability\b"),
        # --- work preferences -----------------------------------------------------------------
        ("work_preference.willing_to_relocate", r"relocat"),
        ("work_preference.willing_to_travel", r"travel"),
        ("work_preference.open_to_international", r"international (role|position|opportunit)|work abroad|outside (of )?india|overseas"),
        ("address.timezone", r"time ?zone"),
        ("work_preference.schedule", r"night shift|\bshift\b|working hours|overlap|rotational|weekend|on-?call"),
        ("work_preference.employment_type", r"employment type|type of employment|job type|work type|(full|part)[- ]?time|contract (role|position|basis)|freelance|internship|permanent|temporary"),
        ("work_preference.work_arrangement", r"remote|hybrid|on-?site|in-?office|in person|work (arrangement|mode|setting|model|style)|work from (home|office)|\bwfh\b|where (do you )?(prefer|want|like) to work|preferred (work )?location|\boffice\b|which location|location (do you |would you )?prefer"),
        # --- experience -----------------------------------------------------------------------
        ("experience.currently_employed", r"currently (employed|working|work)|presently (employed|working)|employment status|are you (working|employed)"),
        ("experience.current_company", r"(current|present|most recent|last|latest).{0,12}(company|employer|organi[sz]ation|firm)|^(company|employer)( name)?$|where do you (currently )?work|name of (your )?(current )?(employer|company)"),
        ("experience.current_title", r"(current|present|most recent|last|latest).{0,12}(title|designation|position|role|job)|job title|^(title|designation|position|role)$"),
        ("experience.seniority_level", r"seniority|career level|experience level|level of experience|which level"),
        ("experience.years_of_experience", r"(total|overall|relevant|professional|work|industry)?\s*(years?|yrs).{0,15}(experience|exp\b)|experience.{0,15}(years?|yrs)|how (many years|long).{0,30}(work|experience|industry)|total experience|\byoe\b"),
        ("experience.summary", r"professional summary|work history|career summary|\bheadline\b|about your (experience|background)|\bsummary\b"),
        # --- skills -------------------------------------------------------------------------
        ("skills.languages_spoken", r"languages? (do )?you (speak|know)|spoken|fluent|fluency|native language|english (proficiency|level|skills?)|proficiency in (english|hindi)|speak (english|hindi)|language proficiency"),
        ("skills.programming_languages", r"programming language|coding language|languages? (do )?you (code|program)"),
        ("skills.skill_list", r"(key|technical|top|core|relevant|primary) skills|^skills?$|list.*(skills|technologies)|tech(nology)? stack|tools (and|&) technologies|which (of the following )?(skills|tools|technologies)"),
        ("skills.specific_skill_experience", r"(experience|familiar|proficien|worked|knowledge|hands-?on|comfortable|expertise|exposure|background).{0,20}\b(with|in|of|using)\b|have you (used|built|deployed|worked)|do you know"),
        # --- education ----------------------------------------------------------------------
        ("education.currently_enrolled", r"currently (a )?student|enrolled|are you (a )?student|still studying|pursuing"),
        ("education.highest_education_level", r"highest (level of |degree of )?(education|degree|qualification)|education(al)? level|level of education|degree level|highest qualification"),
        ("education.graduation_year", r"graduat|completion (year|date)|year of (passing|completion)|passing year|passed out"),
        ("education.start_year", r"(education|degree|course|university|college).{0,20}start|start (year|date).{0,20}(education|degree|course|university|college)"),
        ("education.grade", r"\bgpa\b|cgpa|\bgrade\b|percentage|\bmarks\b|\bscore\b"),
        ("education.field_of_study", r"\bmajor\b|field of study|speciali[sz]ation|discipline|\bstream\b|area of study"),
        ("education.institution", r"university|college|school|institut|alma mater"),
        ("education.degree", r"\bdegree\b|qualification"),
        # --- personal / contact -------------------------------------------------------------
        ("personal.first_name", r"first name|given name|forename"),
        ("personal.last_name", r"last name|surname|family name"),
        ("personal.preferred_name", r"preferred name|nickname|like to be called|go by"),
        ("personal.full_name", r"\bname\b"),
        ("personal.date_of_birth", r"date of birth|birth ?date|\bdob\b|birthday|\bage\b|how old"),
        ("contact.confirm_email", r"(confirm|re-?enter|verify|repeat).{0,10}e-?mail"),
        ("contact.email", r"e-?mail"),
        ("contact.phone", r"(phone|mobile|number).{0,15}(with|including|incl\.?).{0,10}(country|dial)"),
        ("contact.phone_country_code", r"(country|dial(ing)?) code"),
        ("contact.phone", r"phone|mobile|contact (number|no)|telephone|\bcell\b|whatsapp"),
        ("contact.linkedin", r"linkedin"),
        ("contact.github", r"github|git ?hub"),
        ("contact.portfolio", r"portfolio|personal (website|site)|website|\bblog\b|\burl\b"),
        ("contact.social_profile", r"twitter|facebook|instagram|\bx\b.*(handle|profile)|medium|stack ?overflow|social"),
        # --- address --------------------------------------------------------------------------
        ("address.postal_code", r"\bzip\b|postal|pin ?code|postcode"),
        ("address.line2", r"address line ?2|apartment|suite|landmark"),
        ("address.line1", r"address line ?1|street"),
        ("address.full_single_line", r"(full|complete|mailing|postal|home|current|permanent|residential) address|^address$"),
        ("address.city_state", r"city\W{0,3}(and|,|/|&)\W{0,3}(state|province|region|country)|^current location$|where (you )?will (you )?be located|location \(city"),
        ("address.city", r"\bcity\b|\btown\b|current location|where are you (located|based)|^location$"),
        ("address.state", r"\bstate\b|province|\bregion\b"),
        ("address.country", r"\bcountry\b"),
        # --- motivation / documents (checked after everything specific) --------------------------
        ("document.resume", r"resume|\bcv\b|curriculum"),
        ("document.cover_letter_file", r"cover letter.*(upload|attach|file)|(upload|attach).*cover letter"),
        ("document.other", r"upload|attach"),
        ("motivation.why_this_company", r"why (do you want|would you like|are you interested).*(company|us|here|join)|why (us|this company)|interest(ed)? in (joining|working)"),
        ("motivation.why_this_role", r"why (do you want|are you interested|would you be|are you a good fit).*(role|position|job)|why (this role|this position)|good fit|what (makes you|qualifies you)"),
        ("motivation.cover_letter", r"cover letter|message to (the )?(hiring manager|recruiter)"),
        ("motivation.career_goals", r"career goals?|where do you see yourself|aspiration|five years|5 years"),
        ("motivation.about_yourself", r"tell us about yourself|about yourself|anything else|additional information|comments?$|describe yourself|introduce yourself"),
    ]
]

ESSAY_HINT = re.compile(r"^(why|describe|explain|tell us|what (makes|interests|motivates)|share|elaborate)|in your own words|\bessay\b", re.I)


def match_rule(question: str) -> str | None:
    """Return the `category.subcategory` path of the first rule that matches, or None."""
    for path, rx in RULES:
        if rx.search(question):
            return path
    return None


def apply_rules(profile: Profile, q: Question) -> Fact | None:
    """Answer `q` from the rule table; None when no rule matches or the profile is silent."""
    path = match_rule(q.text)
    if not path:
        return None
    category, subcategory = path.split(".", 1)
    fact = profile.fact_for(category, subcategory, q.text, q.context, q.options)
    if fact is None:
        return None
    fact.rule = path
    if q.kind in ("essay", "text") and ESSAY_HINT.search(q.text) and category == "motivation":
        fact.essay = True
    return fact
