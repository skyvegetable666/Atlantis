import argparse
import json

from .bootstrap import build
from .contracts import RunConfig
from .server import serve


def main() -> None:
    parser = argparse.ArgumentParser(description="Atlantis local agent laboratory")
    parser.add_argument("--db", default=".atlantis/city.db")
    parser.add_argument("--env", default=".env")
    commands = parser.add_subparsers(dest="command", required=True)
    web = commands.add_parser("serve", help="Open the local observation server")
    web.add_argument("--port", type=int, default=8765)
    run = commands.add_parser("run", help="Run a bounded experiment")
    run.add_argument("--mode", choices=("demo", "live"), default="demo")
    run.add_argument("--agents", type=int, choices=(1, 2), default=2)
    run.add_argument("--max-calls", type=int, default=32)
    run.add_argument("--chat", choices=("none", "public", "private"), default="private")
    commands.add_parser("list", help="List persisted experiments")
    inspect = commands.add_parser("inspect", help="Export one experiment as JSON")
    inspect.add_argument("run_id")
    args = parser.parse_args()
    if args.command == "serve":
        serve(args.db, args.port, args.env)
        return
    city, controller, capabilities = build(args.db, args.env)
    try:
        if args.command == "list":
            print(json.dumps(city.list_runs(), indent=2))
        elif args.command == "inspect":
            print(json.dumps(city.snapshot(args.run_id), indent=2, ensure_ascii=False))
        else:
            if args.mode not in controller.runtimes:
                parser.error("Live mode requires the model gateway settings in .env or environment variables.")
            run_id = controller.create_run(RunConfig(execution_mode=args.mode, agent_count=args.agents, max_calls=args.max_calls, chat_mode=args.chat))
            city.set_status(run_id, "running")
            print(f"Experiment {run_id} ({args.mode})", flush=True)
            while True:
                state = controller.advance(run_id)
                if state["status"] != "running":
                    break
            print(json.dumps({
                "id": run_id, "status": state["status"], "calls": state["budget"],
                "scores": state["scores"], "messages": len(state["messages"]),
                "real_cost_unconfirmed_calls": sum(u["cost_micros"] is None for u in state["usage"]),
            }, indent=2))
            if state["status"] != "completed":
                raise SystemExit(1)
    finally:
        city.storage.close()


if __name__ == "__main__":
    main()
