""" 第一版本
定义核心智能体 RepositoryAgent

它接收用户问题，从问题中提取搜索词，在项目代码里搜索，并将匹配到的位置整理成回答。
"""

from __future__ import annotations # 它让 Python暂时不立即解析类型注解

import re

from .tools import RepositoryTools, SearchMatch # 导入搜索工具 RepositoryTools：负责读取文件、搜索代码 SearchMatch：表示一条搜索结果


class RepositoryAgent:
    """M1 agent that chooses read-only tools for code-location questions. 一个用于回答“代码在哪里”这类问题的 M1 智能体，它只使用只读工具。"""

    # 1.初始化
    def __init__(self, tools: RepositoryTools) -> None:
        # 当创建 RepositoryAgent 对象时，必须传入一个 RepositoryTools 对象
        self.tools = tools

    # 2.回答问题方法
    def answer(self, question: str) -> str:
        # 2.1 提取搜索词 把用户问题转换为可以搜索的关键词
        terms = self._search_terms(question)
        # 2.2 创建空列表，用来保存所有搜索结果。
        matches: list[SearchMatch] = []
        # 2.3 逐个搜索关键词
        for term in terms:
            matches.extend(self.tools.search_code(term))

        # 2.4 对搜索结果去重
        # 它使用下面三个字段组成字典的键：文件路径 + 行号 + 代码内容   如果多次搜索得到完全相同的位置，字典中只会保留一份。
        unique = {(match.path, match.line, match.text): match for match in matches}
        # 2.5 排序搜索结果
        # 先按照文件路径 item.path 排序  同一个文件中，再按照行号 item.line 排序
        ranked = sorted(unique.values(), key=lambda item: (item.path, item.line))

        # 2.6 没有找到结果
        if not ranked:
            return "未找到相关代码。已检查文件：" + ", ".join(self.tools.list_files())
        
        # 2.7 整理搜索证据 将搜索结果转换为方便阅读的文本 每一条结果格式类似：
        # - 文件路径:行号 ｜ 代码内容
        evidence = "\n".join(
            f"- {match.path}:{match.line} — {match.text}" for match in ranked[:8]
        )
        return f"找到以下代码依据：\n{evidence}"

    # 3. 静态方法——从问题中提取搜索词。 @staticmethod 表示这个方法不需要访问：当前对象 self 当前类 cls  它只根据传入的 question 进行处理。
    @staticmethod
    def _search_terms(question: str) -> list[str]:
        # 定义中英文关键词映射
        aliases = {
            "登录": ["login", "signin", "sign_in"],
            "注册": ["register", "signup", "sign_up"],
        }
        # 查找中文关键词
        terms = [term for key, values in aliases.items() if key in question for term in values]
        # 如果找到中文映射，直接返回
        if terms:
            return terms
        # 从英文问题中提取单词
        return [token for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", question) if len(token) > 2]

