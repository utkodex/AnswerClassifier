"""Sub-categories per category, with the description jev sees for each one.

`SUBCATEGORIES[category]` maps a sub-category label (the profile field key) to a short
description. jev reads these as the criteria of one `Choice` question, so the wording here
*is* the classifier. Every category also has `other` for fields that fit none of the keys.

The labels follow the keys in job_profile.json so a classified question can be answered
by a direct lookup, e.g. ("personal", "What is your name") -> "full_name".
"""
from __future__ import annotations

SUBCATEGORIES: dict[str, dict[str, str]] = {
    "personal": {
        "full_name": "Full name / complete name / name as on documents / legal name.",
        "first_name": "First name / given name / forename.",
        "last_name": "Last name / surname / family name.",
        "preferred_name": "Preferred name, nickname, name you would like to be called.",
        "pronouns": "Pronouns (he/him, she/her, they/them).",
        "date_of_birth": "Date of birth, birthday, age.",
        "gender": "Gender / sex asked as a personal detail (not in an EEO survey).",
        "nationality": "Nationality.",
        "citizenship": "Country of citizenship, citizen of which country.",
        "marital_status": "Marital status.",
        "other": "A personal detail that matches none of the above.",
    },
    "contact": {
        "email": "Email address / primary email.",
        "confirm_email": "Confirm or re-enter the email address.",
        "phone": "Phone / mobile / contact number.",
        "phone_country_code": "Phone country code / dialling code.",
        "linkedin": "LinkedIn profile URL.",
        "github": "GitHub profile URL.",
        "portfolio": "Portfolio, personal website, blog or other social profile link.",
        "other": "A contact detail that matches none of the above.",
    },
    "address": {
        "line1": "Street address / address line 1.",
        "line2": "Address line 2 / apartment / suite / landmark.",
        "city": "City / town.",
        "state": "State / province / region.",
        "postal_code": "Postal code / ZIP / PIN code.",
        "country": "Country of residence / country you live in.",
        "full_single_line": "Complete address in a single field.",
        "timezone": "Time zone of the applicant.",
        "other": "An address detail that matches none of the above.",
    },
    "work_authorization": {
        "country_of_residence": "Country you are currently based in / currently reside in.",
        "authorized_to_work": "Are you legally authorized / eligible to work in a given country?",
        "requires_sponsorship": "Do you need visa sponsorship now or in the future?",
        "current_visa_status": "Current visa / immigration / permanent residency status.",
        "passport": "Passport holder / which passport do you hold.",
        "security_clearance": "Security clearance held or eligibility for one.",
        "other": "A work-authorization question that matches none of the above.",
    },
    "eeo": {
        "gender": "Gender identity in an equal-opportunity survey.",
        "veteran_status": "Veteran status / are you a veteran.",
        "protected_veteran": "Protected veteran classification (US form).",
        "military_service": "Military service history.",
        "disability_status": "Disability status / do you have a disability.",
        "race_ethnicity": "Race / ethnicity / ethnic origin.",
        "religion": "Religion or belief.",
        "sexual_orientation": "Sexual orientation.",
        "transgender_experience": "Are you a person of transgender experience.",
        "other": "An EEO / diversity question that matches none of the above.",
    },
    "employment_check": {
        "age_over_18": "Are you 18 years of age or older / legal working age.",
        "previously_worked_here": "Have you previously worked for or been employed by this company.",
        "previously_applied": "Have you previously applied to this company.",
        "relatives_at_company": "Relatives / family / friends employed at the company.",
        "non_compete": "Non-compete, non-solicit or restrictive agreement with a current or former employer.",
        "government_procurement": "Involvement in government procurement or contract awards involving this company.",
        "referral": "Were you referred by an employee / who referred you.",
        "background_check_consent": "Consent to a background check or verification.",
        "criminal_history": "Criminal record / convictions.",
        "drug_screening": "Willingness to take a drug test.",
        "other": "A background or conflict-of-interest question that matches none of the above.",
    },
    "work_preference": {
        "work_arrangement": "Remote / hybrid / onsite preference, preferred work arrangement.",
        "willing_to_relocate": "Willingness to relocate.",
        "preferred_location": "Preferred work location / office / city.",
        "willing_to_travel": "Willingness to travel, travel percentage.",
        "employment_type": "Employment type: full-time, part-time, contract, internship.",
        "open_to_international": "Open to international roles / working abroad.",
        "schedule": "Shift, working hours, time-zone or schedule preference.",
        "other": "A work-preference question that matches none of the above.",
    },
    "compensation": {
        "current_ctc": "Current salary / current CTC / current compensation.",
        "expected_ctc": "Expected salary / expected CTC / desired compensation / salary expectations.",
        "currency": "Currency of the salary figures.",
        "salary_negotiable": "Is the salary negotiable.",
        "other": "A compensation question that matches none of the above.",
    },
    "availability": {
        "notice_period": "Notice period at current employer.",
        "earliest_start_date": "Earliest start date / when can you start / date available.",
        "available_immediately": "Can you join immediately.",
        "other": "An availability question that matches none of the above.",
    },
    "education": {
        "degree": "Degree / qualification obtained (B.Tech, MSc, PhD).",
        "field_of_study": "Field of study / major / specialisation.",
        "institution": "School, college or university name.",
        "start_year": "Education start date / year.",
        "graduation_year": "Graduation / completion year or date.",
        "grade": "GPA / grade / percentage / CGPA.",
        "highest_education_level": "Highest level of education completed.",
        "other": "An education question that matches none of the above.",
    },
    "experience": {
        "current_title": "Current job title / designation.",
        "current_company": "Current employer / company.",
        "currently_employed": "Are you currently employed.",
        "years_of_experience": "Total years of experience.",
        "seniority_level": "Seniority / career level.",
        "summary": "Professional summary / work history overview.",
        "job_title": "Title of a past position in work history.",
        "employer": "Employer / company name of a past position.",
        "employment_dates": "Start / end dates of a position.",
        "responsibilities": "Responsibilities / achievements in a position.",
        "other": "An experience question that matches none of the above.",
    },
    "skills": {
        "programming_languages": "List the programming languages you know.",
        "ml_deep_learning": "Machine learning / deep learning skills.",
        "generative_ai": "Generative AI / LLM experience.",
        "llm_frameworks_apis": "LLM frameworks and APIs (LangChain, OpenAI API, etc.).",
        "data_vector_stores": "Databases, data tools and vector stores.",
        "mlops_cloud": "MLOps, DevOps and cloud platforms (AWS, GCP, Azure, Docker).",
        "agentic_coding_tools": "AI coding assistants and agent tools.",
        "languages_spoken": "Spoken / written human languages and proficiency.",
        "skill_list": "General list of skills / key skills / technical skills.",
        "specific_skill_experience": "Yes/no or years question about ONE named tool, language or technology, e.g. 'Do you have experience with Python?'.",
        "other": "A skills question that matches none of the above.",
    },
    "source": {
        "how_did_you_hear": "How did you hear about this job / source of application.",
        "referred_by": "Name of the employee who referred you.",
        "other": "A source question that matches none of the above.",
    },
    "motivation": {
        "why_this_company": "Why do you want to work at this company.",
        "why_this_role": "Why are you interested in this role / why are you a good fit.",
        "cover_letter": "Cover letter text / message to the hiring manager.",
        "career_goals": "Career goals / where do you see yourself.",
        "about_yourself": "Tell us about yourself / anything else you want to share.",
        "other": "A motivation or free-text question that matches none of the above.",
    },
    "consent": {
        "terms_agreement": "Agree to terms and conditions.",
        "privacy_policy": "Accept the privacy policy / data processing notice.",
        "data_retention": "Consent to keep the data for future opportunities / talent pool.",
        "contact_consent": "Consent to be contacted by email, SMS or phone.",
        "certification_true": "Certify that the information provided is true and complete.",
        "other": "A consent question that matches none of the above.",
    },
    "document": {
        "resume": "Resume / CV upload.",
        "cover_letter_file": "Cover letter file upload.",
        "portfolio_file": "Portfolio / work samples upload.",
        "transcript": "Transcript / mark sheet upload.",
        "certificate": "Certificates / licences upload.",
        "photo": "Photo / headshot upload.",
        "other": "A document upload that matches none of the above.",
    },
}

# Accept the section names used in job_profile.json too.
CATEGORY_ALIASES: dict[str, str] = {
    "eeo_self_identification": "eeo",
    "work_preferences": "work_preference",
    "professional": "experience",
    "employment_history_checks": "employment_check",
    "documents": "document",
}


def resolve_category(name: str) -> str:
    """Normalise a category name ('EEO ', 'work_preferences') to a key of SUBCATEGORIES."""
    key = name.strip().lower().replace("-", "_").replace(" ", "_")
    key = CATEGORY_ALIASES.get(key, key)
    if key not in SUBCATEGORIES:
        raise KeyError(f"unknown category {name!r}; known: {', '.join(SUBCATEGORIES)}")
    return key
