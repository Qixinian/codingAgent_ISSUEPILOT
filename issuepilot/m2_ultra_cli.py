from __future__ import annotations

import argparse

from .m2_agent import CodingAgent
from .m2_tools import CodingTools
from .spark_ultra import SparkUltraModel


def main() -> None:
    parser = argparse.ArgumentParser(description="IssuePilot M2 with Spark Ultra native Function Calling")
    parser.add_argument("repository")
    parser.add_argument("task")
    parser.add_argument("--max-steps", type=int, default=12)
    args = parser.parse_args()
    result = CodingAgent(CodingTools(args.repository), SparkUltraModel(), args.max_steps).run(args.task)
    print(result.content)
    print(f"steps={result.steps}, completed={result.completed}")
    for event in result.trace:
        print(f"step {event['step']}: {event['tool']}")


if __name__ == "__main__":
    main()

