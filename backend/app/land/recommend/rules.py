from __future__ import annotations

import string
from functools import lru_cache
from typing import Any

import yaml

from app.land.models import GeoFeature, Level, Recommendation
from app.land.settings import data_dir

MONTHS = [
    "styczeń",
    "luty",
    "marzec",
    "kwiecień",
    "maj",
    "czerwiec",
    "lipiec",
    "sierpień",
    "wrzesień",
    "październik",
    "listopad",
    "grudzień",
]


@lru_cache(maxsize=1)
def load_rules() -> list[dict]:
    with open(data_dir() / "rules.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["rules"]


def _check(condition: dict, context: dict[str, Any]) -> bool:
    field, op = condition["field"], condition["op"]
    value = context.get(field)
    target = condition.get("value")
    if op == "exists":
        return value not in (None, "", [])
    if op == "is_true":
        return value is True
    if op == "is_false":
        return value is False
    if value is None:
        return False
    if op == "eq":
        return value == target
    if op == "ne":
        return value != target
    if op == "in":
        return value in target
    if op == "lt":
        return value < target
    if op == "le":
        return value <= target
    if op == "gt":
        return value > target
    if op == "ge":
        return value >= target
    raise ValueError(f"unknown operator {op}")


def matches(rule: dict, context: dict[str, Any]) -> bool:
    when = rule.get("when", {})
    if "all" in when and not all(_check(c, context) for c in when["all"]):
        return False
    if "any" in when and not any(_check(c, context) for c in when["any"]):
        return False
    return True


class _Formatter(string.Formatter):
    def get_value(self, key, args, kwargs):
        value = kwargs.get(key)
        if value is None:
            return "?"
        if isinstance(value, float):
            return f"{value:.0f}" if abs(value) >= 10 else f"{value:.1f}"
        return value


_formatter = _Formatter()


def render(text: str, context: dict[str, Any]) -> str:
    return " ".join(_formatter.format(text, **context).split())


def apply(
    context: dict[str, Any], category: str, locations: dict[str, GeoFeature], confidence: Level
) -> list[Recommendation]:
    out = []
    for rule in load_rules():
        if rule["category"] != category or not matches(rule, context):
            continue
        out.append(
            Recommendation(
                key=rule["key"],
                category=category,
                priority=int(rule["priority"]),
                title=rule["title"],
                action=render(rule["action"], context),
                rationale=render(rule["rationale"], context),
                cause_keys=list(rule.get("causes", [])),
                evidence=list(rule.get("evidence", [])),
                ecoscheme=rule.get("ecoscheme"),
                location=locations.get(rule.get("location", "")),
                confidence=confidence,
            )
        )
    return sorted(out, key=lambda r: r.priority)


def months_label(months: list[int]) -> str | None:
    if not months:
        return None
    months = sorted(set(months))
    if len(months) >= 3 and months == list(range(months[0], months[-1] + 1)):
        return f"{MONTHS[months[0] - 1]}–{MONTHS[months[-1] - 1]}"
    return ", ".join(MONTHS[m - 1] for m in months)
