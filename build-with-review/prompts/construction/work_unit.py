#!/usr/bin/env python3
"""Normalize and resolve explicit construction work-unit identities."""

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
WORKSPACE = HERE.parent.parent
REPO = WORKSPACE.parent.parent.parent.resolve()
COMMON = HERE.parent / "common"
sys.path.insert(0, str(COMMON))
import progress  # noqa: E402
from correction_round import parse_artifact  # noqa: E402

LOT_RE = re.compile(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?")


def normalize_work_unit(value):
    if not isinstance(value, dict):
        raise TypeError("the work unit is not an object")
    kind = value.get("kind")
    if kind == "lot":
        if set(value) != {"kind", "lot"} or not isinstance(value.get("lot"), str):
            raise ValueError("the ordinary work unit has an invalid shape")
        if not LOT_RE.fullmatch(value["lot"]):
            raise ValueError("the ordinary work unit has an invalid lot")
        return {"kind": "lot", "lot": value["lot"]}
    if kind == "correction":
        if set(value) != {"kind", "built", "round"}:
            raise ValueError("the correction work unit has an invalid shape")
        built = value.get("built")
        round_number = value.get("round")
        if not isinstance(built, str) or not LOT_RE.fullmatch(built):
            raise ValueError("the correction work unit has an invalid built unit")
        if isinstance(round_number, bool) or not isinstance(round_number, int) or round_number < 1:
            raise ValueError("the correction work unit has an invalid round")
        return {"kind": "correction", "built": built, "round": round_number}
    raise ValueError("the work unit has an unknown kind")


def readable_work_unit(value):
    unit = normalize_work_unit(value)
    if unit["kind"] == "lot":
        return unit["lot"]
    return f"{unit['built']} correction round {unit['round']}"


def work_unit_key(value):
    unit = normalize_work_unit(value)
    if unit["kind"] == "lot":
        return f"lot:{unit['lot']}"
    return f"correction:{unit['built']}:{unit['round']}"


def git_output(*args):
    result = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def correction_opening(entries, built, round_number):
    matches = [
        (index, entry) for index, entry in enumerate(entries)
        if entry.get("kind") == "correction.round.opened"
        and progress.note_data(entry).get("built") == built
        and progress.note_data(entry).get("round") == round_number
    ]
    if len(matches) != 1:
        raise ValueError("the Correction Round has no one exact opening")
    index, entry = matches[0]
    normalized = progress.normalize_correction_round_opening(
        entries[:index], progress.note_data(entry),
        "the resolved Correction Round opening", historical=True,
    )
    terminal_kinds = {
        "correction.round.built", "correction.round.resolved", "correction.round.escalated",
    }
    if any(
        later.get("kind") in terminal_kinds
        and progress.note_data(later).get("built") == built
        and progress.note_data(later).get("round") == round_number
        for later in entries[index + 1:]
    ):
        raise ValueError("the Correction Round is already terminal")
    return index, normalized


def resolve_correction(built, round_number, task=None):
    unit = normalize_work_unit({"kind": "correction", "built": built, "round": round_number})
    entries = progress.journal_entries()
    opening_index, opening = correction_opening(entries, built, round_number)
    authority_proof = progress.journal_line_proof(opening_index)
    authority_sha256 = hashlib.sha256(
        json.dumps(opening, sort_keys=True, separators=(",", ":")).encode(),
    ).hexdigest()
    artifact_relative = pathlib.PurePosixPath("corrections", built, f"round-{round_number}.md")
    artifact = parse_artifact(
        WORKSPACE / artifact_relative, expected_built=built, expected_round=round_number,
    )
    if artifact["state"] != "active" \
            or artifact["controller_sha256"] != opening["controller_sha256"] \
            or artifact["manifest_sha256"] != opening["manifest_sha256"] \
            or len(artifact["tasks"]) != opening["tasks"]:
        raise ValueError("the current Correction Round artifact changes its opening authority")
    selected = None
    if task is not None:
        if isinstance(task, bool) or not isinstance(task, int) or task < 1 \
                or task > len(artifact["tasks"]):
            raise ValueError("the Correction Round task does not exist")
        selected = artifact["tasks"][task - 1]
    ref_root = f"refs/bwr/{WORKSPACE.name}/{built}/correction-{round_number}"
    head = git_output("rev-parse", "HEAD")
    tree = git_output("rev-parse", "HEAD^{tree}")
    tree_authority = {"rewind": None, "commit": head, "tree": tree, "gate": None}
    execution_authority = {
        "schema": 1,
        "contract_authority": authority_sha256,
        "tree_authority": tree_authority,
    }
    return {
        "schema": 1,
        "unit": unit,
        "readable": readable_work_unit(unit),
        "authority": {
            "kind": "correction.round.opened",
            "proof": authority_proof,
            "sha256": authority_sha256,
        },
        "execution_authority_sha256": hashlib.sha256(
            json.dumps(execution_authority, sort_keys=True, separators=(",", ":")).encode(),
        ).hexdigest(),
        "tree_authority": tree_authority,
        "workspace_document": str(artifact_relative),
        "repository_document": str(artifact_relative),
        "report_root": f"reports/construction/{built}/correction-{round_number}",
        "ref_root": ref_root,
        "task_manifest_sha256": artifact["manifest_sha256"],
        "task_count": len(artifact["tasks"]),
        "controller_sha256": artifact["controller_sha256"],
        "artifact_sha256": artifact["artifact_sha256"],
        "task": selected,
        "source_findings": {
            "path": artifact["source_findings_path"],
            "sha256": artifact["source_findings_sha256"],
            "ids": artifact["source_findings"],
        },
        "original_plan_context": {
            "built": built,
            "parent_position": artifact["parent_position"],
            "source_reviewed_commit": artifact["identity"]["source_reviewed_commit"],
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("resolve-correction",))
    parser.add_argument("built")
    parser.add_argument("round", type=int)
    parser.add_argument("task", type=int, nargs="?")
    args = parser.parse_args()
    try:
        resolved = resolve_correction(args.built, args.round, args.task)
    except (OSError, ValueError) as exc:
        print(f"**work unit ERROR** · {exc}", file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(resolved, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
