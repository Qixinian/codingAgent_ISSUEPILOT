from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the IssuePilot M3.1 API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--database", default="issuepilot.db")
    parser.add_argument(
        "--model-provider",
        choices=("spark-ultra", "ollama"),
        default=os.getenv("ISSUEPILOT_MODEL_PROVIDER", "spark-ultra"),
    )
    parser.add_argument("--model", help="Model name, for example qwen3:0.6b")
    args = parser.parse_args()
    try:
        import uvicorn
    except ImportError as error:
        raise RuntimeError("Install M3 dependencies with: pip install -r requirements-m3.txt") from error
    from .m3.api import create_app
    from .m3.service import create_agent_factory

    app = create_app(
        args.database,
        args.workspace,
        create_agent_factory(args.model_provider, args.model),
    )
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
