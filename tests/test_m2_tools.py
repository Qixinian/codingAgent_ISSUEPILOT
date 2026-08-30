from pathlib import Path

import pytest

from issuepilot.m2_tools import CodingTools


def test_write_file_returns_diff_and_rejects_escape(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")
    tools = CodingTools(tmp_path)
    result = tools.write_file("app.py", "value = 2\n")
    assert "+value = 2" in result.diff
    assert not result.created
    with pytest.raises(PermissionError):
        tools.write_file("../outside.py", "secret")


def test_run_tests_reports_success_and_failure(tmp_path: Path) -> None:
    test_file = tmp_path / "test_example.py"
    test_file.write_text("def test_value():\n    assert True\n", encoding="utf-8")
    assert CodingTools(tmp_path).run_tests().passed
    test_file.write_text("def test_value():\n    assert False\n", encoding="utf-8")
    result = CodingTools(tmp_path).run_tests()
    assert result.exit_code == 1
    assert "failed" in result.stdout


def test_run_tests_times_out(tmp_path: Path) -> None:
    (tmp_path / "test_slow.py").write_text(
        "import time\n\ndef test_slow():\n    time.sleep(2)\n",
        encoding="utf-8",
    )
    result = CodingTools(tmp_path).run_tests(timeout=0.05)
    assert result.timed_out
    assert result.exit_code is None

