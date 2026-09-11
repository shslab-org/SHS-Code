#!/usr/bin/env python3
"""
SHS Code — PlanningFlow entry point.
Decomposes the goal into steps and runs each with an appropriate agent.

Usage:
    python run_flow.py "Analyse this CSV and generate a bar chart"
"""
import asyncio

from app.config import Config
from app.flow.planning import PlanningFlow
from app.logger import logger


async def main(goal: str) -> None:
    cfg = Config.get()
    flow = PlanningFlow(timeout=cfg.runflow.timeout)
    logger.info(f"[PlanningFlow] Goal: {goal}")
    result = await flow.run(goal)
    print("\n" + "=" * 60)
    print("FLOW RESULT:")
    print("=" * 60)
    print(result)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="SHS Code — PlanningFlow entry point.",
        prog="run_flow.py",
    )
    parser.add_argument("goal", nargs="*", help="Goal text for the PlanningFlow agent")
    args = parser.parse_args()
    if args.goal:
        goal = " ".join(args.goal)
    else:
        try:
            goal = input("Enter goal: ").strip()
        except EOFError:
            goal = ""
        if not goal:
            goal = "Write a hello world Python script and save it to workspace/hello.py"
    asyncio.run(main(goal))
