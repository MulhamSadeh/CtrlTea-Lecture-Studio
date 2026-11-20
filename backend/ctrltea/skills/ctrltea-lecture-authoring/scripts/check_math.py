"""Check explicit rational linear combinations without evaluating code or LaTeX."""
import argparse
from fractions import Fraction
import json
from pathlib import Path


def rational(value):
    if type(value) not in (int, str):
        raise ValueError("Use integers or quoted rational numbers.")
    return Fraction(value)


def verify(case):
    weights = case["weights"]
    rows = case["rows"]
    expected = case["expected"]
    if not all(isinstance(v, list) and v for v in (weights, rows, expected)):
        raise ValueError("Expected nonempty arrays for weights, rows and expected.")
    if len(weights) != len(rows) or any(
        not isinstance(row, list) or len(row) != len(expected) for row in rows
    ):
        raise ValueError("Row count or width mismatch.")
    factors = list(map(rational, weights))
    actual = [sum(k * rational(v) for k, v in zip(factors, column)) for column in zip(*rows)]
    return {"id": case["id"], "ok": actual == list(map(rational, expected)),
            "actual": [str(v) for v in actual]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checks", type=Path)
    args = parser.parse_args()
    try:
        cases = json.loads(args.checks.read_text(encoding="utf-8"))
        if not isinstance(cases, list) or not cases:
            raise ValueError("Expected a nonempty list of checks.")
        results = [verify(case) for case in cases]
    except (KeyError, ValueError, TypeError, OSError, ArithmeticError) as error:
        parser.exit(2, f"Invalid input: {error}\n")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(case["ok"] for case in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
