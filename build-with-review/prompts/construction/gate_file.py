#!/usr/bin/env python3
"""Parse the human-validated gate file into its executable command list."""
import pathlib
import sys


class GateFileError(ValueError):
    """The gate file does not satisfy its closed line grammar."""


def commands_from_text(text):
    lines = text.splitlines()
    if not lines:
        raise GateFileError("gate.md contains no line")

    commands = []
    seen = set()
    for number, line in enumerate(lines, 1):
        if not line.strip():
            raise GateFileError(f"gate.md line {number} is blank")
        if line.lstrip().startswith("#"):
            continue
        if line in seen:
            raise GateFileError(f"gate.md repeats this command: {line}")
        seen.add(line)
        commands.append(line)

    if not commands:
        raise GateFileError("gate.md contains no executable command")
    return commands


def read_gate_commands(path):
    return commands_from_text(path.read_text(encoding="utf-8"))


def main():
    if len(sys.argv) != 2:
        print("usage: gate_file.py <gate path>", file=sys.stderr)
        raise SystemExit(64)
    try:
        commands = read_gate_commands(pathlib.Path(sys.argv[1]))
    except (OSError, UnicodeError, GateFileError) as exc:
        print(f"**gate file ERROR** · {exc}", file=sys.stderr)
        raise SystemExit(1)
    print(len(commands))


if __name__ == "__main__":
    main()
