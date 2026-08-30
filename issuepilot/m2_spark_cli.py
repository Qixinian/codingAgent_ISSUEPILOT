from __future__ import annotations

import argparse

from .m2_agent import CodingAgent
from .m2_tools import CodingTools
from .spark_lite import SparkLiteModel


def main() -> None:
    parser = argparse.ArgumentParser(description="IssuePilot M2 with Spark Lite JSON tool selection")
    parser.add_argument("repository")
    parser.add_argument("task")
    parser.add_argument("--max-steps", type=int, default=12)
    args = parser.parse_args()
    result = CodingAgent(CodingTools(args.repository), SparkLiteModel(), args.max_steps).run(args.task)
    print(result.content)
    print(f"steps={result.steps}, completed={result.completed}")


if __name__ == "__main__":
    main()

