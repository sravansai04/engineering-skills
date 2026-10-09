import argparse

from cli import export
from cli import list as list_cmd


def main(argv=None):
    parser = argparse.ArgumentParser(prog="tasktrack")
    sub = parser.add_subparsers(required=True)
    list_cmd.add_parser(sub)
    export.add_parser(sub)
    args = parser.parse_args(argv)
    args.func(args)
