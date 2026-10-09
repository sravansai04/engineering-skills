"""`tasktrack list`: show tasks in a table."""
from cli import output
from cli.store import load_tasks

COLUMNS = ["id", "title", "status", "due"]


def add_parser(subparsers):
    p = subparsers.add_parser("list", help="List tasks")
    p.add_argument("--status", help="Only show tasks with this status")
    p.set_defaults(func=run)


def run(args):
    rows = load_tasks()
    if args.status:
        rows = [r for r in rows if r["status"] == args.status]
    print(output.render_table(rows, COLUMNS))
