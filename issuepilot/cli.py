from __future__ import annotations

import argparse

from .agent import RepositoryAgent
from .tools import RepositoryTools


def main() -> None:
    parser = argparse.ArgumentParser(description="Locate code in a repository")
    parser.add_argument("repository", help="Repository directory")
    parser.add_argument("question", help="Natural-language code-location question")
    args = parser.parse_args()
    print(RepositoryAgent(RepositoryTools(args.repository)).answer(args.question))


if __name__ == "__main__":
    main()

