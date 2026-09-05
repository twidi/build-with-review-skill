#!/usr/bin/env python3
"""Validate the mechanical structure of the BWR prompt graph.

This repository-only tool finds broken paths, invalid entry composers,
unexpected runtime files, unreachable files, and unsafe graph cycles.
It cannot decide whether a prompt contains every semantically required read.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skill"
ENTRIES = SKILL / "prompts" / "entries"
ROLES = SKILL / "prompts" / "roles"
WORKFLOWS = SKILL / "prompts" / "workflows"

MAX_DEPTH = 5
MAX_SIZE = 500 * 1024

INVENTORY = re.compile(
    r"^### Runtime inventory\n.*?^```text\n(.*?)^```$", re.MULTILINE | re.DOTALL
)
REFERENCE = re.compile(
    r"<BWR_SKILL>/((?:prompts|scripts)/[A-Za-z0-9_./-]+\.(?:md|py))"
)
INCLUDE = re.compile(r"@@([^\s]+)")


def shown(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def runtime_files() -> set[Path]:
    return {
        path.resolve()
        for path in SKILL.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    }


def documented_files(errors: list[str]) -> set[Path]:
    design = ROOT / "BWR-DESIGN.md"
    if not design.is_file():
        errors.append("Missing BWR-DESIGN.md")
        return set()

    match = INVENTORY.search(design.read_text(encoding="utf-8"))
    if not match:
        errors.append("Missing Runtime inventory tree in BWR-DESIGN.md")
        return set()

    directories: list[str] = []
    files: set[Path] = set()
    for line in match.group(1).splitlines():
        if line == "<BWR_SKILL>/":
            continue

        positions = [line.find(marker) for marker in ("├── ", "└── ")]
        positions = [position for position in positions if position >= 0]
        if not positions:
            continue

        position = min(positions)
        depth = position // 4
        name = line[position + 4 :]
        directories = directories[:depth]
        if name.endswith("/"):
            directories.append(name[:-1])
        else:
            files.add(SKILL.joinpath(*directories, name).resolve())
    return files


def entry_includes(
    files: set[Path], errors: list[str]
) -> tuple[dict[Path, list[Path]], set[Path], set[Path]]:
    entries = {path.resolve() for path in ENTRIES.rglob("*.md")}
    roles = {path.resolve() for path in ROLES.rglob("*.md")}
    includes: dict[Path, list[Path]] = {}

    entry_names = {path.relative_to(ENTRIES) for path in entries}
    role_names = {path.relative_to(ROLES) for path in roles}
    for name in sorted(entry_names - role_names):
        errors.append(f"Entry has no matching Role: {name}")
    for name in sorted(role_names - entry_names):
        errors.append(f"Role has no matching entry: {name}")

    for entry in sorted(entries):
        targets: list[Path] = []
        for number, line in enumerate(
            entry.read_text(encoding="utf-8").splitlines(), 1
        ):
            if not line.strip():
                continue
            match = INCLUDE.fullmatch(line)
            if not match:
                errors.append(
                    f"Non-include content in entry composer: {shown(entry)}:{number}"
                )
                continue

            raw = match.group(1)
            if raw.startswith("/") or "<" in raw or ">" in raw:
                errors.append(
                    f"Non-relative entry include: {shown(entry)}:{number}: {raw}"
                )
                continue

            target = (entry.parent / raw).resolve()
            targets.append(target)
            if target not in files:
                errors.append(
                    f"Broken entry include: {shown(entry)}:{number} -> {shown(target)}"
                )

        includes[entry] = targets
        matching_role = (ROLES / entry.relative_to(ENTRIES)).resolve()
        if matching_role not in targets:
            errors.append(f"Entry does not include its Role: {shown(entry)}")

    return includes, entries, roles


def prompt_references(
    files: set[Path], errors: list[str]
) -> tuple[dict[Path, set[Path]], int]:
    graph: dict[Path, set[Path]] = defaultdict(set)
    occurrences = 0

    for source in sorted(files):
        if source.suffix != ".md":
            continue
        text = source.read_text(encoding="utf-8")

        for match in REFERENCE.finditer(text):
            occurrences += 1
            target = (SKILL / match.group(1)).resolve()
            graph[source].add(target)
            if target not in files:
                errors.append(
                    f"Broken BWR_SKILL reference: {shown(source)} -> {shown(target)}"
                )

        if source.is_relative_to(ENTRIES):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            match = INCLUDE.fullmatch(line)
            if match and "<" not in match.group(1) and ">" not in match.group(1):
                errors.append(
                    f"Active @@ include outside entries/: {shown(source)}:{number}"
                )

    return graph, occurrences


def cyclic_components(
    graph: dict[Path, set[Path]], nodes: set[Path]
) -> list[set[Path]]:
    """Return cyclic strongly connected components."""
    index = 0
    indexes: dict[Path, int] = {}
    low: dict[Path, int] = {}
    stack: list[Path] = []
    active: set[Path] = set()
    result: list[set[Path]] = []

    def visit(node: Path) -> None:
        nonlocal index
        indexes[node] = low[node] = index
        index += 1
        stack.append(node)
        active.add(node)

        for target in graph.get(node, set()) & nodes:
            if target not in indexes:
                visit(target)
                low[node] = min(low[node], low[target])
            elif target in active:
                low[node] = min(low[node], indexes[target])

        if low[node] != indexes[node]:
            return
        component: set[Path] = set()
        while True:
            target = stack.pop()
            active.remove(target)
            component.add(target)
            if target == node:
                break
        if len(component) > 1 or node in graph.get(node, set()):
            result.append(component)

    for node in sorted(nodes):
        if node not in indexes:
            visit(node)
    return result


def reachable(graph: dict[Path, set[Path]], roots: set[Path]) -> set[Path]:
    found: set[Path] = set()
    pending = list(roots)
    while pending:
        node = pending.pop()
        if node in found:
            continue
        found.add(node)
        pending.extend(graph.get(node, set()) - found)
    return found


def expand(
    entry: Path,
    includes: dict[Path, list[Path]],
    errors: list[str],
) -> tuple[int, int]:
    active: set[Path] = set()

    def walk(path: Path, depth: int) -> tuple[int, int]:
        if path in active:
            errors.append(f"Fixed include cycle reaches {shown(path)}")
            return 0, depth
        if depth > MAX_DEPTH:
            errors.append(f"Fixed include depth exceeds {MAX_DEPTH}: {shown(path)}")
            return 0, depth
        if path not in includes:
            return (path.stat().st_size, depth) if path.is_file() else (0, depth)

        active.add(path)
        parts = [walk(target, depth + 1) for target in includes[path]]
        active.remove(path)
        return sum(size for size, _ in parts), max(level for _, level in parts)

    return walk(entry, 1)


def audit(verbose: bool = False) -> int:
    errors: list[str] = []
    files = runtime_files()
    documented = documented_files(errors)

    for path in sorted(documented - files):
        errors.append(f"Documented runtime file is missing: {shown(path)}")
    for path in sorted(files - documented):
        errors.append(f"Undocumented runtime file: {shown(path)}")

    includes, entries, roles = entry_includes(files, errors)
    references, reference_occurrences = prompt_references(files, errors)

    graph = {path: set(references.get(path, set())) for path in files}
    for source, targets in includes.items():
        graph[source].update(targets)

    include_graph = {source: set(targets) for source, targets in includes.items()}
    for component in cyclic_components(include_graph, files):
        errors.append(
            "Fixed include cycle: "
            + ", ".join(shown(path) for path in sorted(component))
        )

    workflow_cycles = cyclic_components(references, files)
    for component in workflow_cycles:
        if any(not path.is_relative_to(WORKFLOWS) for path in component):
            errors.append(
                "On-demand cycle leaves workflows/: "
                + ", ".join(shown(path) for path in sorted(component))
            )

    roots = {(SKILL / "SKILL.md").resolve(), *entries}
    found = reachable(graph, roots)
    for path in sorted(files - found):
        errors.append(f"Runtime file is unreachable: {shown(path)}")

    expansions = {entry: expand(entry, includes, errors) for entry in entries}
    for entry, (size, _) in expansions.items():
        if size > MAX_SIZE:
            errors.append(f"Expanded entry is too large: {shown(entry)} ({size} bytes)")

    if errors:
        print("Prompt graph is invalid.", file=sys.stderr)
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    largest = max(expansions, key=lambda entry: expansions[entry][0])
    deepest = max(expansions, key=lambda entry: expansions[entry][1])
    reference_edges = sum(len(targets) for targets in references.values())

    print("Prompt graph is valid.")
    print(f"Runtime files: {len(files)}")
    print(f"Markdown files: {sum(path.suffix == '.md' for path in files)}")
    print(f"Roles and entry composers: {len(roles)} / {len(entries)}")
    print(f"Fixed include edges: {sum(map(len, includes.values()))}")
    print(
        f"Concrete BWR_SKILL references: {reference_occurrences} occurrences, "
        f"{reference_edges} unique edges"
    )
    print(f"Reachable runtime files: {len(found)}/{len(files)}")
    print(f"Workflow cycle groups: {len(workflow_cycles)}")
    print(f"Maximum fixed include depth: {expansions[deepest][1]}/{MAX_DEPTH}")
    print(
        f"Largest expanded entry: {shown(largest)} "
        f"({expansions[largest][0]}/{MAX_SIZE} bytes)"
    )

    if verbose:
        for number, component in enumerate(workflow_cycles, 1):
            print(f"\nWorkflow cycle group {number}:")
            for path in sorted(component):
                print(f"  {shown(path)}")
        print("\nExpanded entries:")
        for entry in sorted(expansions):
            size, depth = expansions[entry]
            print(f"  {shown(entry)}: {size} bytes, depth {depth}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verbose", action="store_true")
    return audit(parser.parse_args().verbose)


if __name__ == "__main__":
    raise SystemExit(main())
