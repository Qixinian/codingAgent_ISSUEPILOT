from __future__ import annotations

import difflib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WriteResult:
    path: str
    created: bool
    diff: str


@dataclass(frozen=True)
class TestResult:
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class CodingTools:
    """Bounded repository tools for the M2 coding agent."""

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

    def search_code(self, query: str) -> list[dict[str, object]]:
        if not query:
            raise ValueError("query must not be empty")
        matches: list[dict[str, object]] = []
        for relative_path in self.list_files():
            try:
                lines = self._resolve(relative_path).read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for number, line in enumerate(lines, 1):
                if query.casefold() in line.casefold():
                    matches.append({"path": relative_path, "line": number, "text": line.strip()})
        return matches

    def write_file(self, relative_path: str | Path, content: str) -> WriteResult:
        path = self._resolve(relative_path)
        if path.exists() and not path.is_file():
            raise IsADirectoryError(relative_path)
        existed = path.exists()
        old = path.read_text(encoding="utf-8") if existed else ""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        diff = "".join(
            difflib.unified_diff(
                old.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=f"a/{Path(relative_path).as_posix()}",
                tofile=f"b/{Path(relative_path).as_posix()}",
            )
        )
        return WriteResult(Path(relative_path).as_posix(), not existed, diff)

    def run_tests(self, timeout: float = 60.0) -> TestResult:
        try:
            process = subprocess.run(
                [sys.executable, "-m", "pytest", "-q"],
                cwd=self.root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
            return TestResult(process.returncode, process.stdout[-12_000:], process.stderr[-12_000:], False)
        except subprocess.TimeoutExpired as error:
            return TestResult(None, _text(error.stdout), _text(error.stderr), True)


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace")[-12_000:] if isinstance(value, bytes) else value[-12_000:]

