"""The category set and the description jev sees for each one.

Each label maps to a short description. jev reads these as the criteria of a single
`Choice` question, so the wording here *is* the classifier: adjust it to move the
boundary between categories.
"""
from __future__ import annotations

CATEGORIES: dict[str, str] = {
    "personal": (
        "Identity of the applicant: first/last/full name, preferred name, pronouns, "
        "date of birth, age, nationality, marital status."
    ),
    "contact": (
        "Ways to reach the applicant: email, confirm email, phone / mobile number, "
        "LinkedIn, GitHub, portfolio, personal website, social media handles."
    ),
    "address": (
        "Where the applicant lives: street address, city, state/province, postal / zip code, "
        "country of residence, primary residence, location during an internship."
    ),
    "work_authorization": (
        "Legal right to work: authorized to work in a country, visa or sponsorship needs, "
        "citizenship / permanent residency status, work permit, security clearance."
    ),
    "eeo": (
        "Equal-opportunity / diversity self-identification: gender, race, ethnicity, veteran or "
        "military status, disability status, sexual orientation, transgender experience."
    ),
    "employment_check": (
        "Background and conflict-of-interest checks: relatives employed at the company, previously "
        "worked or applied here, non-compete agreements, background check consent, criminal history, "
        "drug screening, age over 18."
    ),
    "work_preference": (
        "How and where the applicant wants to work: remote / hybrid / onsite, willingness to relocate, "
        "willingness to travel, preferred locations, employment types (full-time, contract, internship), "
        "shift or schedule preferences."
    ),
    "compensation": (
        "Money: current salary / CTC, expected or desired salary, base salary range, hourly rate, "
        "equity or bonus expectations."
    ),
    "availability": (
        "Timing: notice period, earliest start date, desired start date, availability for interviews, "
        "hours per week available, internship duration dates."
    ),
    "education": (
        "Academic background: degree, major / minor, university or school, enrollment status, "
        "GPA, graduation date, certifications, currently enrolled in a Master's or PhD."
    ),
    "experience": (
        "Work history: years of experience, current or most recent employer, job title, "
        "previous roles, management experience, industry experience."
    ),
    "skills": (
        "Technical and professional abilities: programming languages, tools, frameworks, "
        "spoken-language proficiency, proficiency level ratings, specific competencies."
    ),
    "source": (
        "How the applicant found the job: how did you hear about us, referral name, "
        "job board or event, recruiter or employee referral, 'if other please specify'."
    ),
    "motivation": (
        "Open-ended essays about fit and interest: why this company / role, what you hope to gain, "
        "cover letter text, career goals, describe a project, tell us about yourself."
    ),
    "consent": (
        "Agreements and acknowledgements: privacy policy, terms, confidentiality agreement, "
        "data processing consent, certification that answers are true, communication opt-in."
    ),
    "document": (
        "File uploads and attachments: resume / CV, cover letter file, transcript, portfolio file, "
        "writing sample, photo."
    ),
}

LABELS: tuple[str, ...] = tuple(CATEGORIES)
