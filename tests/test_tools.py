from pathlib import Path

import pytest

from issuepilot.tools import RepositoryTools


def test_read_list_and_search(tmp_path: Path) -> None:
    (tmp_path / "api.py").write_text("def login():\n    return True\n", encoding="utf-8")
    tools = RepositoryTools(tmp_path)

    assert tools.list_files() == ["api.py"]
    assert "def login" in tools.read_file("api.py")
    match = tools.search_code("login")[0]
    assert (match.path, match.line) == ("api.py", 1)


def test_read_rejects_path_outside_repository(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    tools = RepositoryTools(repository)

    with pytest.raises(PermissionError):
        tools.read_file("../secret.txt")

