# Build With Review

Build With Review (BWR) is a TwiCC skill for large product features.

It turns a product request into a reviewed Spec, ordered Lot Plans, tested code, and Product Review. Separate sessions write, review, verify, and fix the work.

## Workflow

1. Write and review the Spec.
2. Divide the approved Spec into ordered Lots.
3. Review each Lot Plan.
4. Build each Task through Design, implementation, independent checks, and the complete Gate.
5. Run Product Review on the built Lot.
6. Correct bounded findings or create a Sub-lot for structural work.
7. Deliver the Lot, then continue with the next Lot.

Human product decisions can update the Spec through an Amendment.

## Documentation

- [PHILOSOPHY.md](PHILOSOPHY.md) defines the product philosophy.
- [OPERATING-PHILOSOPHY.md](OPERATING-PHILOSOPHY.md) defines the operating principles.
- [BWR-DESIGN.md](BWR-DESIGN.md) defines the complete workflow and its contracts.
- [PROMPT-DESIGN.md](PROMPT-DESIGN.md) defines the prompt architecture and loading rules.
- [skill/SKILL.md](skill/SKILL.md) is the installed skill entrypoint.
- [install.sh](install.sh) installs or updates the local skill.
- [tests/validate_prompt_graph.py](tests/validate_prompt_graph.py) validates the prompt graph and entrypoints.

The [`skill/`](skill/) directory is the complete deployable package. The [`tests/`](tests/) directory and root files support development and validation. Do not install the repository root as the skill.

## Requirements

- TwiCC with session orchestration and recursive `@@` prompt inclusion.
- Bash and `rsync` for manual installation.
- Python 3 for the watchdog.
- Codex, Claude Code, or both.

## Manual installation

Clone the repository, then run the installer from its root:

```bash
git clone https://github.com/twidi/build-with-review-skill.git
cd build-with-review-skill
./install.sh
```

The script installs or updates the canonical copy in `~/.agents/skills`. It removes installed files that no longer exist in [`skill/`](skill/). Do not edit the installed copy.

Claude Code discovers the symlink in `~/.claude/skills`. The script creates or corrects that symlink without replacing a real file or directory.

Invoke the skill with `$build-with-review` in Codex or `/build-with-review` in Claude Code.

## Repository validation

```bash
python3 tests/validate_prompt_graph.py
python3 -m unittest discover -s tests -v
```
