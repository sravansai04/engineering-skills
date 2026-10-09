import argparse

from cli import list as list_cmd
from cli import show


def main(argv=None):
    parser = argparse.ArgumentParser(prog="tasktrack")
    sub = parser.add_subparsers(required=True)
    list_cmd.add_parser(sub)
    show.add_parser(sub)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
