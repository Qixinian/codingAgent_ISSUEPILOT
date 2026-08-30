""" 第一版本
让用户可以在终端中输入“项目路径”和“问题”，然后由 RepositoryAgent 搜索代码并打印答案。
"""

from __future__ import annotations

import argparse

from .agent import RepositoryAgent
from .tools import RepositoryTools


def main() -> None:
    # 1. 创建参数解析器
    parser = argparse.ArgumentParser(description="Locate code in a repository")
    # 2.添加仓库路径参数
    parser.add_argument("repository", help="Repository directory")
    # 3. 添加问题参数
    parser.add_argument("question", help="Natural-language code-location question")
    # 4. 解析参数
    args = parser.parse_args()
    # 5. 创建工具、智能体并回答
    print(RepositoryAgent(RepositoryTools(args.repository)).answer(args.question))


if __name__ == "__main__":
    main()

