"""`tasktrack show ID`: print one task."""
from cli import output
from cli.store import load_tasks

COLUMNS = ["id", "title", "status", "due"]


def add_parser(subparsers):
    p = subparsers.add_parser("show", help="Show one task")
    p.add_argument("id", type=int)
    p.add_argument("--json", action="store_true", help="Print the task as JSON")
    p.set_defaults(func=run)


def run(args):
    match = [r for r in load_tasks() if r["id"] == args.id]
    if not match:
        print(f"no task with id {args.id}")
        return 1
    row = {c: match[0].get(c) for c in COLUMNS}
    if args.json:
        print(output.to_json(row))
    else:
        print(output.render_table([row], COLUMNS))
    return 0
