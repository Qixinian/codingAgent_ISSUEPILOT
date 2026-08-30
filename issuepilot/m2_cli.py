from __future__ import annotations

import argparse

from .m2_agent import CodingAgent
from .m2_model import OpenAICompatibleModel
from .m2_tools import CodingTools


def main() -> None:
    parser = argparse.ArgumentParser(description="IssuePilot M2 coding agent")
    parser.add_argument("repository")
    parser.add_argument("task")
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--model")
    args = parser.parse_args()
    result = CodingAgent(
        CodingTools(args.repository),
        OpenAICompatibleModel(args.model),
        args.max_steps,
    ).run(args.task)
    print(result.content)
    print(f"steps={result.steps}, completed={result.completed}")


if __name__ == "__main__":
    main()
