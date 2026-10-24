#!/usr/bin/env python
"""Launcher: given a category and a question, jev picks the sub-category (profile field).

    python subclassify.py personal "What is your name"   -> full_name

See `python subclassify.py -h` or src/sub_category_classifier/__main__.py for all options.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from sub_category_classifier.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
