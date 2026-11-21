from collections.abc import Iterable
from datetime import date
from typing import TypeVar

T = TypeVar("T")


def not_after[T](items: Iterable[T], analysis_date: date, key=lambda item: item.date) -> list[T]:
    return [item for item in items if key(item) <= analysis_date]


def assert_not_after[T](items: Iterable[T], analysis_date: date, key=lambda item: item.date) -> None:
    late = [key(item) for item in items if key(item) > analysis_date]
    if late:
        raise AssertionError(f"dane po dacie analizy: {late[:3]}")
