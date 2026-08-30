from pathlib import Path

from issuepilot.agent import RepositoryAgent
from issuepilot.tools import RepositoryTools


def test_agent_locates_login_endpoint(tmp_path: Path) -> None:
    (tmp_path / "routes.py").write_text(
        '@app.post("/login")\ndef login():\n    pass\n', encoding="utf-8"
    )

    answer = RepositoryAgent(RepositoryTools(tmp_path)).answer("登录接口定义在哪里？")

    assert "routes.py:1" in answer
    assert '@app.post("/login")' in answer

