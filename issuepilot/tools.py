"""
它负责真正访问代码仓库，提供三个只读功能：
- 列出仓库中的所有文件
- 读取指定文件
- 在所有文本文件中搜索代码

它还负责安全限制：不允许读取仓库目录以外的文件。

整体关系是：

RepositoryAgent
      ↓ 调用
RepositoryTools
      ↓
列出文件、读取文件、搜索代码
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# SearchMatch 搜索结果类
@dataclass(frozen=True) # @dataclass 会自动生成初始化方法。 frozen=True 表示对象创建后不能修改
class SearchMatch:
    path: str # 匹配代码所在的文件路径
    line: int # 匹配代码所在的行号
    text: str # 匹配到的代码内容

# 限制在单个仓库根目录内使用的只读工具。
class RepositoryTools:
    """Read-only tools restricted to one repository root."""

    # 初始化仓库目录
    def __init__(self, root: str | Path) -> None:
        # Path:把普通字符串转换为 Path 路径对象，方便后续进行路径拼接、读取和检查。 resolve:1.转换为绝对路径 2.解析路径中的 . 和 .. 3.检查路径是否真实存在
        self.root = Path(root).resolve(strict=True) # strict=True 路径不存在则报错
        # 检查是否为文件夹
        if not self.root.is_dir():
            raise NotADirectoryError(self.root)

    # 安全解析路径 这个方法负责把相对路径转换为绝对路径，同时防止访问仓库之外的文件。
    def _resolve(self, relative_path: str | Path) -> Path:
        # 把“仓库根目录”和“相对路径”拼接起来，再转换成规范的绝对路径，最后保存到变量 candidate 中。
        candidate = (self.root / relative_path).resolve()
        # 防止目录穿越  它判断最终路径是否属于当前仓库。
        if candidate != self.root and self.root not in candidate.parents:
            raise PermissionError(f"Path is outside repository: {relative_path}")
        return candidate

    # 列出仓库文件
    def list_files(self) -> list[str]:
        # 返回仓库中的所有文件路径。
        return sorted(
            path.relative_to(self.root).as_posix() # 转换成相对路径
            for path in self.root.rglob("*")  # 递归查找仓库内容 它既可能找到文件，也可能找到文件夹。
            if path.is_file() and ".git" not in path.parts # 只保留文件
        )

    # 读取文件  读取指定文件的全部文本。
    def read_file(self, relative_path: str | Path) -> str:
        return self._resolve(relative_path).read_text(encoding="utf-8")

    # 搜索代码
    def search_code(self, query: str) -> list[SearchMatch]:
        if not query:
            raise ValueError("query must not be empty")
        
        matches: list[SearchMatch] = [] # 创建空列表，用来存放所有匹配结果。
        needle = query.casefold() # 将关键词统一为小写
        for relative_path in self.list_files(): # 遍历所有文件
            path = self._resolve(relative_path) # 获取文件绝对路径
            try:
                lines = path.read_text(encoding="utf-8").splitlines() # 按行读取文本
            except UnicodeDecodeError: # 仓库中可能存在：图片\压缩包\编译文件\非 UTF-8 文本  这些文件不能作为 UTF-8 文本读取。
                continue # 如果读取失败，程序则跳过当前文件，继续检查下一个，不会让整个搜索程序崩溃。
            for line_number, line in enumerate(lines, start=1): # 带行号遍历 start=1 表示行号从1开始，更符合编辑器显示习惯。
                if needle in line.casefold(): # 判断当前行是否包含关键词
                    matches.append(SearchMatch(relative_path, line_number, line.strip())) # 保存匹配结果
        return matches

