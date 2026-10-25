# jobanswer - answer job-application questions from `profile/job_profile.json`

Give it a form question (free text, single-choice or multi-choice) and it returns the
answer the profile says to give, plus the exact option string(s) to click.

```
python answer.py "Are you willing to relocate?" -o Yes -o No
Q: Are you willing to relocate?
A: No
   (rule:relocate, confidence 0.87)
```

## How it answers

| question kind | who answers | who checks |
|---|---|---|
| single-choice, multi-choice, yes/no | **jev** (TypeSafe decision model) | rule engine |
| free text (name, phone, notice period, CTC...) | **rule engine** | - |
| essays ("why do you want to work here") | **Claude** (optional) | - |

1. **jev** (`jobanswer/jev.py`) - the whole `profile/job_profile.json` is sent as the model's
   *state* together with a short answering policy; every option question becomes a
   `Choice` (single-select) or one `Noul` per option (multi-select, ticked at >= 50%).
   You get a probability for every option. Many questions go in one API call.
   Needs `TYPESAFE_API_KEY` in `.env`.
2. **Rule engine** (`jobanswer/rules.py`) - deterministic, offline. Covers identity,
   contact, address, work authorization / visa, EEO self-identification, employment
   checks (relatives, non-compete, referral...), work preferences (remote / relocation /
   onsite-in-NCR), salary buckets in INR or USD, notice period, education, skills,
   languages. For option questions it cross-checks jev: agreement raises confidence,
   disagreement flags the answer for review and shows both answers. Without a jev key
   it answers option questions itself.
3. **Option mapper** (`jobanswer/matching.py`) - turns a rule's intended answer into the
   form's own option strings: yes/no polarity ("No military service" counts as No),
   numeric buckets ("$120,000-$149,999", "3-5 years", "20-30 LPA"), preference
   phrases, fuzzy text. "Decline to answer"-style options are avoided.
4. **Claude layer** (`jobanswer/llm.py`, optional) - essays and free-text questions no
   rule covers. Needs `ANTHROPIC_API_KEY` in `.env`. Uses `claude-opus-5-5` with
   structured JSON output, the profile cached in the system prompt, and the
   server-side refusal fallback.

Anything the system is not sure about is marked `[REVIEW]` (`needs_review: true`).

## Usage

```bash
pip install -r requirements.txt

# single question, free text
python answer.py "What is your notice period?"

# single-choice
python answer.py "Highest level of education" -o "High School" -o "Bachelor's Degree" -o "Master's Degree"
python answer.py "Expected CTC" --options "5-10 LPA; 10-15 LPA; 20-30 LPA; 30+ LPA"

# multi-choice
python answer.py "Which employment types are you open to?" -o Full-time -o Part-time -o Contract -o Freelance --multi

# JSON in / JSON out (for automation)
python answer.py --json '{"question":"Do you require visa sponsorship?","options":["Yes","No"]}' --format json
echo '[{"question":"Phone"},{"question":"Gender","options":["Male","Female"]}]' | python answer.py --stdin --format json

# batch file -> answers file
python answer.py --batch questions.json --out answers.json

# interactive
python answer.py -i

# flags
--explain           show reasoning (option probabilities are always shown)
--rules-only        no API calls at all
--jev never         skip jev (rules answer option questions)
--jev-model <id>    jev model (default jev-latest)
--llm never         skip Claude
--llm always        ask Claude for every free-text question (rules become hints)
--model <id>        Claude model (default claude-opus-5-5)
--profile <path>    alternative job_profile.json (default profile/job_profile.json)
-c "<job context>"  e.g. "Senior ML Engineer, Acme, Berlin" - helps salary / authorization answers
```

Batch file format: a JSON list of `{"id"?, "question", "options"?, "multi"?, "type"?, "context"?}`.
`type` accepts the ATS field types: `text`, `textarea`, `select`/`single`, `multiselect`/`checkbox`/`multi`, `boolean`.

## As a library

```python
from jobanswer import answer_question, Engine, Question

a = answer_question("Are you authorized to work in the UK?", ["Yes", "No"])
a.answer, a.selected_options, a.confidence, a.needs_review, a.reasoning

engine = Engine(use_jev="never", use_llm="never")   # offline, rules only
for a in engine.answer_many([Question("Notice period"), Question("Gender", ["Male", "Female"])]):
    print(a.to_dict())
```

## Answer object

| field | meaning |
|---|---|
| `answer` | text to type, or the chosen option(s) joined by `; ` |
| `selected_options` | exact option strings to select (empty for free text) |
| `confidence` | 0-1 |
| `source` | `jev`, `rule`, `llm` or `none` |
| `probabilities` | option -> probability (jev answers) |
| `model` | model that answered, e.g. `jev-1.13.0` |
| `rule` | which rule fired or cross-checked |
| `reasoning` | why |
| `needs_review` | true when you should look before submitting |

## Changing the answers

Edit `profile/job_profile.json`; the rules read from it (names, salary rules, notice period,
acceptable onsite cities, EEO answers, default "No"s). To add a new question family add a
`@rule` function in `jobanswer/rules.py` and a case in `tests/test_rules.py`.

```bash
python -m pytest -q
```

## category_classifier - which category is this question? (jev)

`src/category_classifier` asks **jev** which category a form question belongs to. The
question text is the model's *state* and the 16 category descriptions in
`src/category_classifier/categories.py` are the criteria of one `Choice` question, so you
get a probability for every category. Many questions go in one API call (20 per request).

```
python classify.py "What is your name"
personal

python classify.py "Are you willing to relocate?" --explain
Q: Are you willing to relocate?
C: work_preference  (confidence 1.00, jev-1.13.0)
   work_preference 100%  personal 0%  contact 0%  address 0%
```

Categories: `personal`, `contact`, `address`, `work_authorization`, `eeo`, `employment_check`,
`work_preference`, `compensation`, `availability`, `education`, `experience`, `skills`,
`source`, `motivation`, `consent`, `document` (`python classify.py --list-categories`).
Edit the descriptions in `categories.py` to move a boundary or add a category.

```bash
python classify.py --json '{"question":"Expected CTC","options":["5-10 LPA","10-15 LPA"]}' --format json
echo '["Phone number", "Gender"]' | python classify.py --stdin
python classify.py --batch questions.json --out categories.json
python classify.py -i                      # interactive
python classify.py "What is your name" --explain --debug        # print the jev request + raw response (stderr)
python classify.py "What is your name" --explain --debug --raw  # also the SDK wire log (key redacted)
--model <id>                               # jev model (default jev-latest, or CATEGORY_CLASSIFIER_MODEL)
```

As a library (add `src` to `sys.path` or `PYTHONPATH`):

```python
from category_classifier import classify, CategoryClassifier

classify("What is your name").category            # 'personal'
clf = CategoryClassifier()
for c in clf.classify_many(["Email", "Notice period", {"question": "Gender", "options": ["Male", "Female"]}]):
    c.category, c.confidence, c.probabilities, c.needs_review   # needs_review when confidence < 0.5
```

Tests: `python -m pytest -q tests/test_category_classifier.py` (offline with a fake jev; the
live test runs when `TYPESAFE_API_KEY` is in the environment).

## sub_category_classifier - which field inside the category? (jev)

Give it the category and the question; jev picks the sub-category, which is the field key
used in `job_profile.json` (so `personal` + "What is your name" -> `full_name`).
The sub-categories and their descriptions live in `src/sub_category_classifier/subcategories.py`;
every category also has `other` for fields that fit none of the keys (flagged `[REVIEW]`).

```
python subclassify.py personal "What is your name"
full_name

python subclassify.py contact "Mobile number" --explain
Q: Mobile number
C: contact.phone  (confidence 1.00, jev-1.13.0)
   phone 100%  email 0%  confirm_email 0%  phone_country_code 0%
```

```bash
python subclassify.py --list                     # all categories and sub-categories
python subclassify.py --list personal            # one category
python subclassify.py --json '{"category":"compensation","question":"Expected CTC"}' --format json
python subclassify.py --batch items.json --out subcategories.json   # items: [{"category":..,"question":..}, ...]
python subclassify.py personal "What is your name" --explain --debug   # print the jev request + raw response
--model <id>      # jev model (default jev-latest, or SUB_CATEGORY_CLASSIFIER_MODEL)
```

Category names from `job_profile.json` (`eeo_self_identification`, `work_preferences`,
`professional`, `employment_history_checks`) are accepted as aliases. Chain the two classifiers:

```python
from category_classifier import classify as category
from sub_category_classifier import classify as subcategory

q = "What is your name"
cat = category(q).category                   # 'personal'
sub = subcategory(cat, q)                    # SubClassification
sub.subcategory, sub.path                    # 'full_name', 'personal.full_name'
```

Tests: `python -m pytest -q tests/test_sub_category_classifier.py`.

## Layout

```
answer.py / classify.py / subclassify.py   launchers (run from the repo root)
src/                                       category_classifier, sub_category_classifier packages
tests/                                     pytest suite (offline with a fake jev)
profile/                                   job_profile.json, job_profile.md, resume PDF
MyDocs/                                    generated HTML reports (git-ignored)
experiments/                               jev-test (image input), TTS-tests (git-ignored)
```
