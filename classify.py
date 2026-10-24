#!/usr/bin/env python
"""Launcher: classify a job-application question into a category with jev.

    python classify.py "What is your name"   -> personal

See `python classify.py -h` or src/category_classifier/__main__.py for all options.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from category_classifier.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
