"""Exact arithmetic checks for the optional, provider-independent packet tool."""
import json
import subprocess
import sys

import pytest

from ctrltea.authoring import SKILL_DIR


def check(tmp_path, case):
    path = tmp_path / "checks.json"
    path.write_text(json.dumps([dict(id="example", **case)]))
    return subprocess.run(
        [sys.executable, str(SKILL_DIR / "scripts/check_math.py"), str(path)],
        capture_output=True, text=True,
    )


@pytest.mark.parametrize("weights,rows,expected", [
    (["1/3"], [[3, 2, 0, 1, 12]], [1, "2/3", 0, "1/3", 4]),
    ([1, 6], [[-6, -5, 0, 0, 0], [1, "2/3", 0, "1/3", 4]], [0, -1, 0, 2, 24]),
    ([1, -1], [[1, 1, 1, 0, 5], [1, "2/3", 0, "1/3", 4]], [0, "1/3", 1, "-1/3", 1]),
    ([2, 3], [[1, 3, 6], [1, 2, 5]], [5, 12, 27]),
])
def test_checked_row_or_matrix_product(tmp_path, weights, rows, expected):
    r = check(tmp_path, dict(weights=weights, rows=rows, expected=expected))
    assert r.returncode == 0 and json.loads(r.stdout)[0]["ok"]


def test_wrong_sign_is_not_a_pass(tmp_path):
    r = check(tmp_path, dict(weights=[-1], rows=[["1/3"]], expected=["1/3"]))
    assert r.returncode == 1
    assert json.loads(r.stdout) == [{"id":"example","ok":False,"actual":["-1/3"]}]


@pytest.mark.parametrize("rows", [[[1, 2]], [["1/0"]], [[True]], [[0.5]], [["x+2"]]])
def test_reject_unsupported_data(tmp_path, rows):
    assert check(tmp_path, dict(weights=[1], rows=rows, expected=[1])).returncode == 2


def test_reference_example_batch():
    from pathlib import Path
    path = Path(__file__).parent / "fixtures/aq03_math_cases.json"
    result = subprocess.run(
        [sys.executable, str(SKILL_DIR / "scripts/check_math.py"), str(path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert all(item["ok"] for item in json.loads(result.stdout))
