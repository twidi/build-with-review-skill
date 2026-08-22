#!/usr/bin/env python3
"""Normalize explicit construction work-unit identities."""

import re

LOT_RE = re.compile(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?")


def normalize_work_unit(value):
    if not isinstance(value, dict):
        raise TypeError("the work unit is not an object")
    kind = value.get("kind")
    if kind == "lot":
        if set(value) != {"kind", "lot"} or not isinstance(value.get("lot"), str):
            raise ValueError("the ordinary work unit has an invalid shape")
        if not LOT_RE.fullmatch(value["lot"]):
            raise ValueError("the ordinary work unit has an invalid lot")
        return {"kind": "lot", "lot": value["lot"]}
    if kind == "correction":
        if set(value) != {"kind", "built", "round"}:
            raise ValueError("the correction work unit has an invalid shape")
        built = value.get("built")
        round_number = value.get("round")
        if not isinstance(built, str) or not LOT_RE.fullmatch(built):
            raise ValueError("the correction work unit has an invalid built unit")
        if isinstance(round_number, bool) or not isinstance(round_number, int) or round_number < 1:
            raise ValueError("the correction work unit has an invalid round")
        return {"kind": "correction", "built": built, "round": round_number}
    raise ValueError("the work unit has an unknown kind")


def readable_work_unit(value):
    unit = normalize_work_unit(value)
    if unit["kind"] == "lot":
        return unit["lot"]
    return f"{unit['built']} correction round {unit['round']}"


def work_unit_key(value):
    unit = normalize_work_unit(value)
    if unit["kind"] == "lot":
        return f"lot:{unit['lot']}"
    return f"correction:{unit['built']}:{unit['round']}"
