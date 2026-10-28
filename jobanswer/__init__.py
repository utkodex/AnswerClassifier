"""jobanswer - answer job-application form questions from profile/job_profile.json.

    from jobanswer import answer_question, Engine, Question

    answer_question("Are you willing to relocate?", ["Yes", "No"]).selected_options   # ['No']
    answer_question("What is your notice period?").answer                             # '1 month'
"""
from .engine import Engine, answer_question
from .models import Answer, Fact, Question
from .profile import Profile

__all__ = ["Answer", "Engine", "Fact", "Profile", "Question", "answer_question"]
