from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DemoQuestion:
    task_id: int
    label: str
    question: str


COMMUNITY_43_QUESTIONS = (
    DemoQuestion(
        task_id=959,
        label="Join repair",
        question=(
            "What are the Pearson correlation coefficients between the number of students "
            "who took the SHSAT and the percentage of Asian, Black/Hispanic, and White "
            "students for Grade 8 in 2016, using SHSAT registration and tester data that "
            "includes grade level information?"
        ),
    ),
    DemoQuestion(
        task_id=960,
        label="Coverage repair",
        question=(
            "Which burger has the highest calorie count among Shake Shack, McDonald's, and "
            "Burger King, and what is that count? Also, identify the lowest calorie burger "
            "from Shake Shack."
        ),
    ),
    DemoQuestion(
        task_id=176,
        label="Direct answer",
        question="What is the minimum ratio of students taking the test to those registered?",
    ),
    DemoQuestion(
        task_id=179,
        label="Honest data gap",
        question=(
            "What are the average attendance rates for Pre-Kindergarten, Grade 5, and Grade 9?"
        ),
    ),
)

COMMUNITY_52_QUESTIONS = (
    DemoQuestion(
        task_id=590,
        label="Yearly skewness",
        question=(
            "After calculating the yearly averages from the unemployment data, what "
            "percentage of the numeric attributes are negatively skewed?"
        ),
    ),
    DemoQuestion(
        task_id=591,
        label="Wage skewness",
        question=(
            "What percentage of the numeric attributes (excluding the year column) are "
            "positively skewed and what percentage are negatively skewed?"
        ),
    ),
)


def demo_questions_for_environment(
    environment_id: str,
    planner_mode: str = "registry",
) -> tuple[DemoQuestion, ...]:
    if planner_mode != "registry":
        return ()
    if environment_id == "coda-community-52":
        return COMMUNITY_52_QUESTIONS
    return COMMUNITY_43_QUESTIONS
