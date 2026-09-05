#!/usr/bin/env bash

set -eu

bwr_repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
bwr_source="$bwr_repo_dir/skill/"
bwr_agents_dir="$HOME/.agents/skills"
bwr_claude_dir="$HOME/.claude/skills"
bwr_target="$bwr_agents_dir/build-with-review"
bwr_claude_link="$bwr_claude_dir/build-with-review"

if [ -L "$bwr_target" ]; then
    printf 'Cannot install: %s must not be a symlink.\n' "$bwr_target" >&2
    exit 1
fi

if [ -e "$bwr_target" ] && [ ! -d "$bwr_target" ]; then
    printf 'Cannot install: %s exists and is not a directory.\n' \
        "$bwr_target" >&2
    exit 1
fi

if [ -d "$bwr_target" ] && \
   { [ ! -f "$bwr_target/SKILL.md" ] || \
     ! grep -Fxq 'name: build-with-review' "$bwr_target/SKILL.md"; }; then
    printf 'Cannot update: %s is not a Build With Review installation.\n' \
        "$bwr_target" >&2
    exit 1
fi

if [ -e "$bwr_claude_link" ] && [ ! -L "$bwr_claude_link" ]; then
    printf 'Cannot install: %s exists and is not a symlink.\n' \
        "$bwr_claude_link" >&2
    exit 1
fi

mkdir -p "$bwr_target" "$bwr_claude_dir"
rsync -a --delete \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    "$bwr_source" "$bwr_target/"
ln -sfn "$bwr_target" "$bwr_claude_link"

printf 'Build With Review copy: %s\n' "$bwr_target"
printf 'Claude Code link: %s\n' "$bwr_claude_link"
