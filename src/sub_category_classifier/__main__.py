"""CLI for sub_category_classifier.

Examples
  python subclassify.py personal "What is your name"            -> full_name
  python subclassify.py contact "Mobile number" --explain
  python subclassify.py --json '{"category": "compensation", "question": "Expected CTC"}'
  python subclassify.py --batch items.json --out subcategories.json
  echo '[{"category":"address","question":"ZIP"}]' | python subclassify.py --stdin --format json
  python subclassify.py --list                 # all categories and their sub-categories
  python subclassify.py --list personal        # one category
  python subclassify.py personal "What is your name" --explain --debug   # print jev request/response
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .classifier import SubCategoryClassifier, SubClassification, dumps
from .subcategories import SUBCATEGORIES, resolve_category


def render(c: SubClassification, explain: bool) -> str:
    flag = " [REVIEW]" if c.needs_review else ""
    if not explain:
        return f"{c.subcategory}{flag}"
    line = f"Q: {c.question}\nC: {c.path}{flag}  (confidence {c.confidence:.2f}, {c.model})"
    line += "\n   " + "  ".join(f"{k} {v * 100:.0f}%" for k, v in c.top(4))
    return line


def _enable_debug(raw: bool) -> None:
    import logging

    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="[%(name)s %(levelname)s] %(message)s")
    logging.getLogger("typesafe_sdk").setLevel(logging.DEBUG if raw else logging.INFO)
    for noisy in ("httpx", "httpx2", "httpcore", "httpcore2"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _trace_client(clf: SubCategoryClassifier) -> None:
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
    ap = argparse.ArgumentParser(prog="subclassify", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("category", nargs="?", help="the category (e.g. personal, contact, eeo)")
    ap.add_argument("question", nargs="?", help="the form question")
    ap.add_argument("-o", "--option", action="append", default=[], help="an option of the field (repeat for each)")
    ap.add_argument("-c", "--context", help="job context, e.g. 'Senior ML Engineer at Acme'")
    ap.add_argument("--json", help="one item as a JSON object {category, question, options?, context?, id?}")
    ap.add_argument("--stdin", action="store_true", help="read a JSON object or list of objects from stdin")
    ap.add_argument("--batch", help="JSON file with a list of {category, question} objects")
    ap.add_argument("--out", help="write results (JSON list) to this file")
    ap.add_argument("--format", choices=["text", "json"], default="text")
    ap.add_argument("--explain", action="store_true", help="show confidence and top sub-categories")
    ap.add_argument("--model", help="jev model id (default jev-latest)")
    ap.add_argument("--list", nargs="?", const="*", metavar="CATEGORY", help="print sub-categories and exit")
    ap.add_argument("--debug", action="store_true", help="pretty-print everything sent to jev and the raw response")
    ap.add_argument("--raw", action="store_true", help="with --debug: also show the SDK's wire log")
    args = ap.parse_args(argv)

    if args.debug:
        _enable_debug(args.raw)

    if args.list:
        cats = list(SUBCATEGORIES) if args.list == "*" else [resolve_category(args.list)]
        for cat in cats:
            print(cat)
            for k, v in SUBCATEGORIES[cat].items():
                print(f"  {k:26s} {v}")
        return 0

    items: list = []
    if args.batch:
        data = json.loads(Path(args.batch).read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else [data]
    elif args.stdin:
        data = json.load(sys.stdin)
        items = data if isinstance(data, list) else [data]
    elif args.json:
        items = [json.loads(args.json)]
    elif args.category and args.question:
        items = [{"category": args.category, "question": args.question, "options": args.option, "context": args.context}]
    else:
        ap.print_help()
        return 2

    clf = SubCategoryClassifier(model=args.model)
    if args.debug:
        _trace_client(clf)

    results = clf.classify_many(items)
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
