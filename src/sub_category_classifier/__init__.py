"""sub_category_classifier - given a category, jev picks the sub-category (profile field).

    >>> from sub_category_classifier import classify
    >>> classify("personal", "What is your name").subcategory
    'full_name'
"""
from .classifier import SubCategoryClassifier, SubClassification, classify, classify_many
from .subcategories import SUBCATEGORIES, resolve_category

__all__ = ["SUBCATEGORIES", "SubCategoryClassifier", "SubClassification", "classify", "classify_many", "resolve_category"]
