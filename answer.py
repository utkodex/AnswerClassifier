#!/usr/bin/env python
"""Answer job-application questions from job_profile.json.

Examples
  python answer.py "Are you willing to relocate?" -o Yes -o No
  python answer.py "Which employment types are you open to?" -o Full-time -o Part-time -o Contract -o Internship --multi
  python answer.py "What is your notice period?"
  python answer.py --json '{"question": "Do you require visa sponsorship?", "options": ["Yes", "No"]}'
  python answer.py --batch questions.json --out answers.json
  python answer.py -i                       # interactive prompt
  echo '{"question": "..."}' | python answer.py --stdin

Batch file format: a JSON list of {"id"?, "question", "options"?, "multi"?, "type"?, "context"?}.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jobanswer import Engine, Question  # noqa: E402


def q_from_dict(d: dict) -> Question:
    return Question(
        text=d.get("question") or d.get("text") or d.get("label") or "",
        options=d.get("options") or [],
        multi=bool(d.get("multi") or d.get("type") in ("multi", "multiselect", "checkbox")),
        qtype=_norm_type(d.get("type")),
        id=d.get("id"),
        context=d.get("context"),
    )


def _norm_type(t):
    if not t:
        return None
    t = str(t).lower()
    return {"select": "single", "radio": "single", "dropdown": "single", "multiselect": "multi", "checkbox": "multi",
            "textarea": "textarea", "text": "text", "boolean": "boolean", "yesno": "boolean"}.get(t, t)


def render(ans, explain: bool) -> str:
    flag = " [REVIEW]" if ans.needs_review else ""
    head = f"Q: {ans.question}\nA: {ans.answer or '(no answer)'}{flag}"
    if ans.selected_options and len(ans.selected_options) > 1:
        head += "\n   selected: " + " | ".join(ans.selected_options)
    meta = f"   ({ans.source}{':' + ans.rule if ans.rule else ''}, confidence {ans.confidence:.2f})"
    if ans.probabilities:
        meta += "\n   " + "  ".join(f"{k} {v * 100:.0f}%" for k, v in ans.probabilities.items())
    if explain and ans.reasoning:
        meta += f"\n   why: {ans.reasoning}"
    return head + "\n" + meta


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question", nargs="?", help="the form question")
    ap.add_argument("-o", "--option", action="append", default=[], help="an option (repeat for each)")
    ap.add_argument("--options", help="options as one string separated by ';' or '|'")
    ap.add_argument("-m", "--multi", action="store_true", help="multi-select: several options may be chosen")
    ap.add_argument("-t", "--type", help="text|textarea|single|multi|boolean (inferred if omitted)")
    ap.add_argument("-c", "--context", help="job context, e.g. 'Senior ML Engineer at Acme, Berlin'")
    ap.add_argument("--json", help="one question as a JSON object")
    ap.add_argument("--stdin", action="store_true", help="read one JSON object or a JSON list from stdin")
    ap.add_argument("--batch", help="JSON file with a list of questions")
    ap.add_argument("--out", help="write answers (JSON list) to this file")
    ap.add_argument("-i", "--interactive", action="store_true", help="interactive loop")
    ap.add_argument("--format", choices=["text", "json"], default="text")
    ap.add_argument("--explain", action="store_true", help="show the reasoning")
    ap.add_argument("--jev", choices=["auto", "never"], default="auto",
                    help="auto: jev answers every option question when TYPESAFE_API_KEY exists; never: rules only")
    ap.add_argument("--jev-model", help="jev model id (default jev-latest)")
    ap.add_argument("--llm", choices=["auto", "always", "never"], default="auto",
                    help="auto: use Claude for free text when rules are unsure; always: ask Claude for everything; never: no Claude")
    ap.add_argument("--model", help="Claude model id (default claude-opus-5-5)")
    ap.add_argument("--profile", help="path to job_profile.json")
    ap.add_argument("--rules-only", action="store_true", help="shortcut for --jev never --llm never")
    args = ap.parse_args(argv)
    if args.rules_only:
        args.jev, args.llm = "never", "never"

    engine = Engine(profile_path=args.profile, use_jev=args.jev, use_llm=args.llm, model=args.model, jev_model=args.jev_model)

    questions: list[Question] = []
    if args.batch:
        data = json.loads(Path(args.batch).read_text(encoding="utf-8"))
        questions = [q_from_dict(d) for d in (data if isinstance(data, list) else [data])]
    elif args.stdin:
        data = json.load(sys.stdin)
        questions = [q_from_dict(d) for d in (data if isinstance(data, list) else [data])]
    elif args.json:
        questions = [q_from_dict(json.loads(args.json))]
    elif args.question:
        opts = list(args.option)
        if args.options:
            sep = "|" if "|" in args.options else ";"
            opts += [o.strip() for o in args.options.split(sep) if o.strip()]
        questions = [Question(text=args.question, options=opts, multi=args.multi, qtype=_norm_type(args.type), context=args.context)]
    elif not args.interactive:
        ap.print_help()
        return 2

    if args.interactive:
        print(f"jobanswer interactive  ({engine.status()})")
        print("Enter a question. Then options one per line (blank line to finish). Prefix an option line with '*' for multi-select. Ctrl+C to quit.\n")
        try:
            while True:
                qtext = input("Q> ").strip()
                if not qtext:
                    continue
                opts, multi = [], False
                while True:
                    line = input("  option> ").strip()
                    if not line:
                        break
                    if line.startswith("*"):
                        multi, line = True, line[1:].strip()
                    opts.append(line)
                ans = engine.answer(Question(text=qtext, options=opts, multi=multi))
                print(render(ans, True) + "\n")
        except (KeyboardInterrupt, EOFError):
            print()
            return 0

    answers = engine.answer_many(questions)
    if args.out:
        Path(args.out).write_text(json.dumps([a.to_dict() for a in answers], indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {len(answers)} answers to {args.out}")
    if args.format == "json":
        print(json.dumps([a.to_dict() for a in answers] if len(answers) > 1 else answers[0].to_dict(), indent=2, ensure_ascii=False))
    elif not args.out or len(answers) == 1:
        for a in answers:
            print(render(a, args.explain))
            print()
    review = [a for a in answers if a.needs_review]
    if review and len(answers) > 1:
        print(f"{len(review)} of {len(answers)} answers need review", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
