"""
IssuePilot M2 中真正操作代码仓库的工具层

它向 CodingAgent 提供五类能力：

列出仓库文件
读取文件
搜索代码
创建或覆盖文件
运行 Pytest 测试

同时，它通过 _resolve() 限制所有文件操作只能发生在指定仓库中。

整体关系如下：
模型提出工具调用
        ↓
CodingAgent._execute()
        ↓
CodingTools
  ├─ list_files()
  ├─ read_file()
  ├─ search_code()
  ├─ write_file()
  └─ run_tests()
        ↓
返回结构化结果
"""

from __future__ import annotations

import difflib # 比较修改前后的文本差异。
import subprocess # 用于启动外部子进程
import sys 
from dataclasses import dataclass
from pathlib import Path

# 文件写入结果
@dataclass(frozen=True)
class WriteResult:
    path: str # 被写入文件的相对路径
    created: bool # 是否创建了新文件
    diff: str # 修改前后差异

# 测试结果
@dataclass(frozen=True)
class TestResult:
    exit_code: int | None # Pytest进程退出码 0：测试通过 非0：测试失败或运行出错 None：测试超时，没有正常退出码
    stdout: str # 标准输出
    stderr: str # 错误输出
    timed_out: bool # 是否因为超时而终止

    # 用于快速判断测试是否真正通过 满足两个条件才返回 True：退出码等于0 没有超时
    @property # 使用时可result.passed 不用写 result.passed()
    def passed(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

# 工具类
class CodingTools:
    """Bounded repository tools for the M2 coding agent. 为 M2 编程智能体提供限制在指定仓库中的工具。"""

    # 初始化仓库根目录 创建工具对象时必须指定仓库路径
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve(strict=True)
        # 检查是否为目录
        if not self.root.is_dir():
            raise NotADirectoryError(self.root)

    # 安全解析仓库路径
    def _resolve(self, relative_path: str | Path) -> Path:
        candidate = (self.root / relative_path).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise PermissionError(f"Path is outside repository: {relative_path}")
        return candidate

    # 列出仓库文件
    def list_files(self) -> list[str]:
        return sorted(
            path.relative_to(self.root).as_posix()
            for path in self.root.rglob("*")
            if path.is_file() and ".git" not in path.parts
        )

    # 读取文件
    def read_file(self, relative_path: str | Path) -> str:
        return self._resolve(relative_path).read_text(encoding="utf-8")

    # 搜索代码
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

    # 创建或覆盖文件 然后返回修改差异
    def write_file(
        self, 
        relative_path: str | Path, 
        content: str
    ) -> WriteResult:
        # 1. 解析安全路径 确保目标位于仓库内部。
        path = self._resolve(relative_path) 
        # 阻止把目录当文件覆盖
        if path.exists() and not path.is_file():
            raise IsADirectoryError(relative_path)
        # 记录是否已经存在 如果写入前文件存在：
        existed = path.exists()
        # 读取旧内容 如果文件存在，就读取修改前的完整内容。 如果是新文件，则将旧内容设为空字符串： 旧内容用于后面生成 diff。
        old = path.read_text(encoding="utf-8") if existed else ""
        # 创建父目录 parents=True：允许递归创建多级目录 exist_ok=True：如果父目录已经存在，不报错。
        path.parent.mkdir(parents=True, exist_ok=True)
        # 写入新内容
        path.write_text(content, encoding="utf-8")
        # 生成统一差异
        diff = "".join(
            difflib.unified_diff( # difflib.unified_diff() ：比较旧内容与新内容，并生成统一 diff。
                old.splitlines(keepends=True), # 拆分旧内容
                content.splitlines(keepends=True), # 拆分新内容 keepends=True 表示保留每行末尾的换行符，有利于生成正确的 diff。
                fromfile=f"a/{Path(relative_path).as_posix()}", # 旧文件显示
                tofile=f"b/{Path(relative_path).as_posix()}", # 新文件显示
            )
        )
        # 返回写入结果
        return WriteResult(Path(relative_path).as_posix(), not existed, diff)

    # 运行测试
    def run_tests(
        self, 
        timeout: float = 60.0 # 默认超时时间为60秒。
    ) -> TestResult:
        try:
            # 启动 Pytest
            process = subprocess.run(
                [sys.executable, "-m", "pytest", "-q"],
                cwd=self.root, # 设置子进程的工作目录为仓库根目录。
                capture_output=True, # 捕获标准输出和错误输出，不直接让它们实时显示在终端中。
                text=True, # 表示以字符串形式处理输出，而不是字节。
                encoding="utf-8", # 用 UTF-8解码测试输出。
                errors="replace", # 如果输出中存在无法按照 UTF-8解码的字节，就用替代字符代替，而不是让程序报错。
                timeout=timeout, # 限制测试最长运行时间。
                check=False, # 即使 Pytest退出码不是0，也不抛出 CalledProcessError。
            )
            """
            为什么截断？

            测试输出可能非常长。如果全部发送给模型：

            消耗大量上下文
            增加请求成本
            可能超过模型上下文限制
            重要的最终错误通常位于输出末尾

            因此这里只保留最后12,000个字符。
            """
            return TestResult(
                process.returncode, # Pytest退出码。
                process.stdout[-12_000:], # 只保留标准输出最后12,000个字符。
                process.stderr[-12_000:], # 只保留错误输出最后12,000个字符。
                False # 表示测试正常结束，没有超时。
            )
        # 处理测试超时
        except subprocess.TimeoutExpired as error:
            return TestResult(
                None,
                _text(error.stdout),
                _text(error.stderr),
                True
            )

# 统一处理超时输出 
def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")[-12_000:]
    return value[-12_000:]
