"""Расчётное ядро - конвейер из 7 стадий.

availability -> balance -> service -> economics -> constraints -> risk -> scenario

Чистый Python, без веб-зависимостей (Правило 2).
Единый Result на выходе (Правило 3).
"""
from .pipeline import evaluate_plan, run_scenario
from .results import Result, YearRow, EconomicsResult, Violation

__all__ = [
    "evaluate_plan",
    "run_scenario",
    "Result",
    "YearRow",
    "EconomicsResult",
    "Violation",
]
