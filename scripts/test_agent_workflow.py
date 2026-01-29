import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))


def _require_env(var_name: str) -> str:
    value = os.getenv(var_name)
    if not value or value == "your-anthropic-api-key-here":
        raise RuntimeError(f"Missing required environment variable: {var_name}")
    return value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Procast agent workflow tests.")
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable LLM caching for this run",
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    load_dotenv(ROOT_DIR / ".env")

    _require_env("DATABASE_URL_READONLY")
    _require_env("ANTHROPIC_API_KEY")

    # Disable DSPy global cache if --no-cache is used
    disable_cache_env = os.getenv("PROCAST_DISABLE_LLM_CACHE", "").lower() in {"1", "true", "yes"}
    if args.no_cache or disable_cache_env:
        import dspy
        from dspy.clients import configure_cache
        configure_cache(enable_disk_cache=False, enable_memory_cache=False)
        print("DSPy global cache DISABLED for this run")

    from src.db.connection import DatabaseManager
    from src.mcp.tools import DatabaseTools
    from src.agent.graph import ProcastAgent

    await DatabaseManager.initialize(use_readonly=True)
    try:
        health = await DatabaseManager.health_check()
        print(f"Database Health: {health}")

        async with DatabaseManager.get_readonly_session() as session:
            tools = DatabaseTools(session)

            summary_result = await tools.get_db_summary()
            summary = summary_result.data[0]["summary"]
            print("Database Summary (first 300 chars):")
            print(summary[:300] + "...")

            result = await tools.execute_query(
                'SELECT COUNT(*) as project_count FROM "Projects" WHERE "IsDisabled" = false'
            )
            print(f'Active Projects: {result.data[0]["project_count"]}')

        agent = ProcastAgent()
        await agent.initialize()
        print("Agent initialized successfully")

        questions = [
            "What is the total budget across all active projects?",
            (
                "Give me a comprehensive overview of revenue vs expenses across all projects. "
                "Show total revenue, total expenses, and net profit/loss."
            ),
        ]

        # use_cache=False also passed to ensure LM-level cache is disabled
        use_cache = None if not (args.no_cache or disable_cache_env) else False

        for question in questions:
            result = await agent.query(
                question=question,
                user_id="test-user",
                use_cache=use_cache,
            )
            response = result.get("response")
            sql_query = result.get("sql_query")
            confidence = result.get("confidence")

            if not response:
                raise RuntimeError("Agent response is empty.")
            if not sql_query:
                raise RuntimeError("Agent SQL query is empty.")
            if confidence is None:
                raise RuntimeError("Agent confidence is missing.")

            print("\n=== Agent Response ===")
            print(f"Question: {question}")
            print(f"\nResponse:\n{response}")
            print(f"\nConfidence: {confidence}")
            print(f"\nSQL Query:\n{sql_query}")
            print(f'\nDomains used: {result.get("metadata", {}).get("selected_domains")}')
    finally:
        await DatabaseManager.close()
        print("Database connection closed")


if __name__ == "__main__":
    asyncio.run(main())
