#!/usr/bin/env python3
"""
ManusClaw — MCP Agent entry point.

Usage:
    python run_mcp.py --connection sse --server-url http://localhost:8000 --prompt "task"
    python run_mcp.py --connection stdio --prompt "task"
    python run_mcp.py --interactive
"""
import argparse
import asyncio

from app.agent.mcp import MCPAgent
from app.logger import logger


async def run(args: argparse.Namespace) -> None:
    agent = MCPAgent(server_url=args.server_url, connection=args.connection)
    if args.interactive:
        print("SHS Code MCP Agent — interactive mode. Type 'exit' to quit.")
        while True:
            try:
                prompt = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if prompt.lower() in ("exit", "quit", "q"):
                break
            if not prompt:
                continue
            result = await agent.run(prompt)
            print(result)
            # SHS Code FIX: reset state so the second prompt doesn't raise
            # "Agent not idle" (BaseAgent.run contract) and crash the CLI.
            from app.schema import AgentState
            agent.state = AgentState.IDLE
            agent._step_count = 0
    else:
        prompt = args.prompt or input("Enter task: ").strip()
        result = await agent.run(prompt)
        print(result)


def main() -> None:
    parser = argparse.ArgumentParser(description="SHS Code MCP Agent")
    parser.add_argument("--connection", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--server-url", default=None)
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--prompt", default=None)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
