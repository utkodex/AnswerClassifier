"""category_classifier - jev classifies a job-application question into a category.

    >>> from category_classifier import classify
    >>> classify("What is your name").category
    'personal'
"""
from .categories import CATEGORIES, LABELS
from .classifier import CategoryClassifier, Classification, classify, classify_many

__all__ = ["CATEGORIES", "LABELS", "CategoryClassifier", "Classification", "classify", "classify_many"]
