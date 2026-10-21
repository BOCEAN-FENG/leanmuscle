#!/usr/bin/env python3
"""Compare two dated 7-day weight windows; never prescribe diet or modify files.

Input: {"observations": [{"date": "YYYY-MM-DD", "weight": 70, "unit": "kg"}]}
Units: kg, jin (confirmed mainland Chinese 0.5 kg), lb (international pound).
Example: python3 weight_trend.py --as-of 2026-10-18 --input measurements.json
"""

import argparse
import json
import math
import re
import sys
from datetime import date, timedelta
from pathlib import Path

FACTORS = {"kg": 1.0, "jin": 0.5, "lb": 0.45359237}
MIN_DAYS = 3


def parse_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Dates must use YYYY-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid calendar date: {value}") from exc


def normalize(payload, as_of):
    if not isinstance(payload, dict) or not isinstance(payload.get("observations"), list):
        raise ValueError("Input must contain an observations array.")
    records, seen = [], set()
    for index, row in enumerate(payload["observations"]):
        if not isinstance(row, dict):
            raise ValueError(f"Observation {index} must be an object.")
        when = parse_date(row.get("date"))
        if when > as_of:
            raise ValueError(f"Future observation relative to as-of date: {when}")
        if when in seen:
            raise ValueError(f"Duplicate date {when}; select the confirmed comparable reading first.")
        seen.add(when)
        value, unit = row.get("weight"), row.get("unit")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Observation {index}: weight must be a JSON number.")
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"Observation {index}: weight must be finite and positive.")
        if not isinstance(unit, str) or unit not in FACTORS:
            raise ValueError(f"Observation {index}: explicit unit must be kg, jin, or lb.")
        kg = value * FACTORS[unit]
        # Catch implausible units/typos without pretending to assess health.
        if not math.isfinite(kg) or not 1 <= kg <= 1000:
            raise ValueError(f"Observation {index}: check the entered value and unit.")
        records.append((when, kg))
    return sorted(records)


def window(records, start, end):
    selected = [(day, kg) for day, kg in records if start <= day <= end]
    count = len(selected)
    mean = math.fsum(kg for _, kg in selected) / count if count else None
    return {
        "start": str(start),
        "end": str(end),
        "days_recorded": count,
        "dates": [str(day) for day, _ in selected],
        "sample_mean_kg": round(mean, 3) if mean is not None else None,
        "sufficient_for_comparison": count >= MIN_DAYS,
    }, mean


def analyze(payload, as_of):
    as_of = parse_date(as_of)
    records = normalize(payload, as_of)
    previous, previous_mean = window(records, as_of - timedelta(days=13), as_of - timedelta(days=7))
    current, current_mean = window(records, as_of - timedelta(days=6), as_of)
    sufficient = previous["sufficient_for_comparison"] and current["sufficient_for_comparison"]
    comparison = None
    if sufficient:
        delta = current_mean - previous_mean
        comparison = {
            "mean_difference_kg": round(delta, 3),
            "mean_difference_percent": round(delta / previous_mean * 100, 3),
        }
    return {
        "as_of": str(as_of),
        "status": "comparable_windows" if sufficient else "insufficient_data",
        "minimum_days_per_window": MIN_DAYS,
        "previous_window": previous,
        "current_window": current,
        "comparison": comparison,
        "older_observations_excluded": sum(day < as_of - timedelta(days=13) for day, _ in records),
        "note": "Descriptive sample means only; verify measurement conditions and recovery before interpreting.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", required=True, help="User-local YYYY-MM-DD; do not infer from server timezone.")
    parser.add_argument("--input", default="-", help="JSON file path, or - for standard input.")
    args = parser.parse_args()
    try:
        raw = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
        result = analyze(json.loads(raw), args.as_of)
    except (ValueError, TypeError, OverflowError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
