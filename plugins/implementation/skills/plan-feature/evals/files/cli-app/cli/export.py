"""`tasktrack export`: print tasks for another tool to consume."""
from cli import output
from cli.store import load_tasks

COLUMNS = ["id", "title", "status", "due"]


def add_parser(subparsers):
    p = subparsers.add_parser("export", help="Export tasks")
    p.add_argument("--format", choices=sorted(output.RENDERERS), default="json")
    p.set_defaults(func=run)


def run(args):
    rows = load_tasks()
    print(output.RENDERERS[args.format](rows, COLUMNS))
