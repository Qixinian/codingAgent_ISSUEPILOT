from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SearchMatch:
    path: str
    line: int
    text: str


class RepositoryTools:
    """Read-only tools restricted to one repository root."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise NotADirectoryError(self.root)

    def _resolve(self, relative_path: str | Path) -> Path:
        candidate = (self.root / relative_path).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise PermissionError(f"Path is outside repository: {relative_path}")
        return candidate

    def list_files(self) -> list[str]:
        return sorted(
            path.relative_to(self.root).as_posix()
            for path in self.root.rglob("*")
            if path.is_file() and ".git" not in path.parts
        )

    def read_file(self, relative_path: str | Path) -> str:
        return self._resolve(relative_path).read_text(encoding="utf-8")

    def search_code(self, query: str) -> list[SearchMatch]:
        if not query:
            raise ValueError("query must not be empty")

        matches: list[SearchMatch] = []
        needle = query.casefold()
        for relative_path in self.list_files():
            path = self._resolve(relative_path)
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for line_number, line in enumerate(lines, start=1):
                if needle in line.casefold():
                    matches.append(SearchMatch(relative_path, line_number, line.strip()))
        return matches

