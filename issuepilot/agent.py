from __future__ import annotations

import re

from .tools import RepositoryTools, SearchMatch


class RepositoryAgent:
    """M1 agent that chooses read-only tools for code-location questions."""

    def __init__(self, tools: RepositoryTools) -> None:
        self.tools = tools

    def answer(self, question: str) -> str:
        terms = self._search_terms(question)
        matches: list[SearchMatch] = []
        for term in terms:
            matches.extend(self.tools.search_code(term))

        unique = {(match.path, match.line, match.text): match for match in matches}
        ranked = sorted(unique.values(), key=lambda item: (item.path, item.line))
        if not ranked:
            return "未找到相关代码。已检查文件：" + ", ".join(self.tools.list_files())

        evidence = "\n".join(
            f"- {match.path}:{match.line} — {match.text}" for match in ranked[:8]
        )
        return f"找到以下代码依据：\n{evidence}"

    @staticmethod
    def _search_terms(question: str) -> list[str]:
        aliases = {
            "登录": ["login", "signin", "sign_in"],
            "注册": ["register", "signup", "sign_up"],
        }
        terms = [term for key, values in aliases.items() if key in question for term in values]
        if terms:
            return terms
        return [token for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", question) if len(token) > 2]

