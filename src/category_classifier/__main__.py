"""CLI for category_classifier.

Examples
  python classify.py "What is your name"                      -> personal
  python classify.py "Are you willing to relocate?" --explain
  python classify.py --json '{"question": "Expected CTC", "options": ["5-10 LPA", "10-15 LPA"]}'
  python classify.py --batch questions.json --out categories.json
  echo '["Phone number", "Gender"]' | python classify.py --stdin --format json
  python classify.py -i
  python classify.py --list-categories
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .categories import CATEGORIES
from .classifier import CategoryClassifier, Classification, dumps


def render(c: Classification, explain: bool) -> str:
    flag = " [REVIEW]" if c.needs_review else ""
    if not explain:
        return f"{c.category}{flag}"
    line = f"Q: {c.question}\nC: {c.category}{flag}  (confidence {c.confidence:.2f}, {c.model})"
    line += "\n   " + "  ".join(f"{k} {v * 100:.0f}%" for k, v in c.top(4))
    return line


def _enable_debug(raw: bool) -> None:
    import logging

    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="[%(name)s %(levelname)s] %(message)s")
    logging.getLogger("typesafe_sdk").setLevel(logging.DEBUG if raw else logging.INFO)
    for noisy in ("httpx", "httpx2", "httpcore", "httpcore2"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _trace_client(clf: CategoryClassifier) -> None:
    """Wrap the client so every jev call prints its state, questions and raw answer as JSON."""
    inner = clf.client.system_one

    def traced(state, questions, **kw):
        print("=" * 30 + " jev REQUEST " + "=" * 30, file=sys.stderr)
        print(f"model: {kw.get('model') or clf.model}", file=sys.stderr)
        print("state:", file=sys.stderr)
        print(json.dumps(state, indent=2, ensure_ascii=False), file=sys.stderr)
        print("questions:", file=sys.stderr)
        qs = {k: (v.model_dump() if hasattr(v, "model_dump") else v) for k, v in questions.items()}
        print(json.dumps(qs, indent=2, ensure_ascii=False), file=sys.stderr)
        res = inner(state, questions, **kw)
        print("=" * 30 + " jev RESPONSE " + "=" * 29, file=sys.stderr)
        body = res.model_dump() if hasattr(res, "model_dump") else res
        print(json.dumps(body, indent=2, ensure_ascii=False, default=str), file=sys.stderr)
        print("=" * 73, file=sys.stderr)
        return res

    clf.client.system_one = traced


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="classify", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question", nargs="?", help="the form question")
    ap.add_argument("-o", "--option", action="append", default=[], help="an option of the field (repeat for each); helps jev")
    ap.add_argument("-c", "--context", help="job context, e.g. 'Senior ML Engineer at Acme'")
    ap.add_argument("--json", help="one question as a JSON object {question, options?, context?, id?}")
    ap.add_argument("--stdin", action="store_true", help="read a JSON string, object or list from stdin")
    ap.add_argument("--batch", help="JSON file with a list of questions (strings or objects)")
    ap.add_argument("--out", help="write results (JSON list) to this file")
    ap.add_argument("-i", "--interactive", action="store_true", help="interactive loop")
    ap.add_argument("--format", choices=["text", "json"], default="text")
    ap.add_argument("--explain", action="store_true", help="show confidence and top categories")
    ap.add_argument("--model", help="jev model id (default jev-latest)")
    ap.add_argument("--list-categories", action="store_true", help="print the categories and exit")
    ap.add_argument("--debug", action="store_true",
                    help="pretty-print everything sent to jev (state + questions) and the raw response")
    ap.add_argument("--raw", action="store_true", help="with --debug: also show the SDK's wire log (headers, raw bytes)")
    args = ap.parse_args(argv)

    if args.debug:
        _enable_debug(args.raw)

    if args.list_categories:
        for k, v in CATEGORIES.items():
            print(f"{k:20s} {v}")
        return 0

    questions: list = []
    if args.batch:
        data = json.loads(Path(args.batch).read_text(encoding="utf-8"))
        questions = data if isinstance(data, list) else [data]
    elif args.stdin:
        data = json.load(sys.stdin)
        questions = data if isinstance(data, list) else [data]
    elif args.json:
        questions = [json.loads(args.json)]
    elif args.question:
        questions = [{"question": args.question, "options": args.option, "context": args.context}]
    elif not args.interactive:
        ap.print_help()
        return 2

    clf = CategoryClassifier(model=args.model)
    if args.debug:
        _trace_client(clf)

    if args.interactive:
        print(f"category_classifier interactive ({clf.model}). Ctrl+C to quit.")
        try:
            while True:
                q = input("Q> ").strip()
                if q:
                    print(render(clf.classify(q), True) + "\n")
        except (KeyboardInterrupt, EOFError):
            print()
            return 0

    results = clf.classify_many(questions)
    if args.out:
        Path(args.out).write_text(json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {len(results)} results to {args.out}")
    if args.format == "json":
        print(dumps(results))
    elif not args.out or len(results) == 1:
        for r in results:
            print(render(r, args.explain or len(results) > 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
