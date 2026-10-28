# jobanswer API - contract for form fillers

Send the fields of a job-application form, get back what to type or which options to click.

```
Base URL   http://127.0.0.1:8765        (python api.py; port via JOBANSWER_PORT)
Docs       GET /docs   (Swagger UI)      GET /openapi.json
Auth       none by default. If the server sets JOBANSWER_API_KEY, send header  X-API-Key: <key>
Content    JSON in, JSON out (UTF-8)
```

## Endpoints

| method | path | use |
|---|---|---|
| GET | `/health` | liveness; shows whether jev / Claude are on |
| POST | `/answer` | one field |
| POST | `/answers` | **one whole form** (preferred: all option fields go to jev in one call) |

## Request

Send every field of the form in page order. One object per field:

| field | type | required | meaning |
|---|---|---|---|
| `question` | string | yes | the label / question text exactly as shown (`text` or `label` are accepted aliases) |
| `options` | string[] | for choice fields | the exact option strings (dropdown entries, radio labels, checkbox labels) |
| `multi` | bool | no | `true` when several options may be selected (checkbox groups, multi-selects) |
| `type` | string | no | `text`, `textarea`, `select`, `radio`, `dropdown`, `multiselect`, `checkbox`, `boolean` |
| `id` | string/int | no | your own field id; echoed back unchanged |
| `context` | string | no | job context for this field; overrides the batch `context` |

Batch body (`POST /answers`):

```json
{
  "context": "Senior ML Engineer, Acme Corp, Berlin, Germany",
  "rules_only": false,
  "questions": [
    {"id": "f1", "question": "First name", "type": "text"},
    {"id": "f2", "question": "Email", "type": "text"},
    {"id": "f3", "question": "Are you willing to relocate?", "options": ["Yes", "No"], "type": "radio"},
    {"id": "f4", "question": "Expected salary", "options": ["$60,000-$89,999", "$90,000-$119,999", "$120,000+"], "type": "select"},
    {"id": "f5", "question": "Which employment types are you open to?", "options": ["Full-time", "Part-time", "Contract", "Internship"], "multi": true},
    {"id": "f6", "question": "Why do you want to work at Acme?", "type": "textarea"},
    {"id": "f7", "question": "Will you now or in the future require sponsorship?", "type": "boolean"}
  ]
}
```

Rules of thumb:

- **Always send `options` for choice fields.** The answer is matched against your strings, so the
  returned `value` / `values` can be clicked as-is.
- **Send `context`** (title, company, city, country). It decides currency, work-authorization and
  relocation answers.
- `type: "boolean"` with no options is treated as a Yes/No choice.
- `rules_only: true` answers offline (no jev, no Claude). Use it for a fast first pass or when the
  server has no API keys.

## Response

`POST /answers` returns:

```json
{
  "answers": [ ...one object per question, same order... ],
  "count": 7,
  "review_count": 1,
  "engine": "rules + jev jev-latest + claude off"
}
```

Each answer object:

| field | type | meaning |
|---|---|---|
| `id` | string/null | your id, echoed |
| `question` | string | the question, echoed |
| `action` | `type` \| `select` \| `check` \| `skip` | **what to do** (see below) |
| `value` | string | text to type, or the option to select (for `check`: options joined by `; `) |
| `values` | string[] | exact option strings to select; empty for text fields |
| `confidence` | 0-1 | how sure the engine is |
| `needs_review` | bool | `true` = a human should look before submitting |
| `source` | string | `rule` (offline rule), `profile` (jev classified, profile answered), `jev`, `llm` (Claude wrote it), `none` |
| `rule` | string | which profile field answered, e.g. `compensation.expected_ctc` |
| `reasoning` | string | why |
| `probabilities` | object | option -> probability when jev answered |
| `category`, `subcategory` | string | the classifier labels |

### `action` - what the form filler should do

| action | do this |
|---|---|
| `type` | put `value` into the text field / textarea |
| `select` | choose the single option `value` (also `values[0]`) in the dropdown / radio group |
| `check` | tick every option in `values`; untick the rest |
| `skip` | nothing to fill. Leave it, or show `reasoning` to the user. Typical: file uploads, essays when Claude is off, questions the profile does not cover |

Example answers:

```json
{"id": "f1", "question": "First name", "action": "type", "value": "Utkarsh", "values": [], "confidence": 0.9, "needs_review": false, "source": "rule", "rule": "personal.first_name", "reasoning": "", "probabilities": {}, "model": "", "category": "personal", "subcategory": "first_name"}

{"id": "f3", "question": "Are you willing to relocate?", "action": "select", "value": "No", "values": ["No"], "confidence": 0.99, "needs_review": false, "source": "jev", "rule": "work_preference.willing_to_relocate", "reasoning": "rule and jev agree (no polarity). relocates only to Delhi NCR or Lucknow; otherwise remote", "probabilities": {"Yes": 0.03, "No": 0.97}, "model": "jev-1.13.0", "category": "work_preference", "subcategory": "willing_to_relocate"}

{"id": "f5", "question": "Which employment types are you open to?", "action": "check", "value": "Full-time; Contract", "values": ["Full-time", "Contract"], "confidence": 0.9, "needs_review": false, "source": "rule", "rule": "work_preference.employment_type", "reasoning": "ticked every option that is in the profile.", "probabilities": {}, "model": "", "category": "work_preference", "subcategory": "employment_type"}

{"id": "f6", "question": "Why do you want to work at Acme?", "action": "skip", "value": "", "values": [], "confidence": 0.0, "needs_review": true, "source": "none", "rule": "motivation.why_this_company", "reasoning": "essay question; set ANTHROPIC_API_KEY to let Claude write it", "probabilities": {}, "model": "", "category": "motivation", "subcategory": "why_this_company"}
```

### Handling `needs_review`

Fill the field anyway when `action` is not `skip`, but mark it for the user. `needs_review` is set when:
the rule and jev disagree (both answers are in `reasoning`), the confidence is below 0.5, the
question names a country or tool the profile does not cover, or the answer is an essay the
profile could only approximate.

## Errors

| status | meaning |
|---|---|
| 401 | `JOBANSWER_API_KEY` is set on the server and the `X-API-Key` header is missing or wrong |
| 422 | malformed body: missing `question`, empty `questions`, wrong types. The `detail` field says which |
| 500 | engine failure; the server log has the traceback |

jev or Claude outages do not fail the request: the engine falls back to rules and the answers
carry `source: "rule"`.

## Examples

curl:

```bash
curl -s http://127.0.0.1:8765/answer -H "Content-Type: application/json" \
  -d '{"question":"What is your notice period?"}'

curl -s http://127.0.0.1:8765/answers -H "Content-Type: application/json" -d @form.json
```

Python:

```python
import requests

form = {
    "context": "Data Scientist, Acme, Noida",
    "questions": [
        {"id": "q1", "question": "Phone", "type": "text"},
        {"id": "q2", "question": "Highest level of education", "options": ["High School", "Bachelor's", "Master's", "PhD"]},
    ],
}
r = requests.post("http://127.0.0.1:8765/answers", json=form, timeout=60)
for a in r.json()["answers"]:
    if a["action"] == "type":
        fill_text(a["id"], a["value"])
    elif a["action"] == "select":
        select_option(a["id"], a["value"])
    elif a["action"] == "check":
        check_options(a["id"], a["values"])
    else:
        log_skip(a["id"], a["reasoning"])
```

JavaScript (browser extension / Playwright):

```js
const res = await fetch("http://127.0.0.1:8765/answers", {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({context, questions: fields.map(f => ({
    id: f.id, question: f.label, options: f.options ?? [], multi: f.multi ?? false, type: f.type,
  }))}),
});
const {answers} = await res.json();
```

## Running the server

```bash
pip install -r requirements.txt
python api.py                                  # 127.0.0.1:8765
JOBANSWER_PORT=9000 python api.py
JOBANSWER_API_KEY=change-me python api.py      # requires X-API-Key on /answer and /answers
```

Keys for jev (`TYPESAFE_API_KEY`) and Claude (`ANTHROPIC_API_KEY`) are read from `.env` in the repo
root. Without them the engine runs rules only; `/health` shows which are on.
