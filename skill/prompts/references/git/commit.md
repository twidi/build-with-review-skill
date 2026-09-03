# Creating a BWR commit

This Reference is for a Role or Workflow that explicitly authorizes a commit.

Before committing, read the current `<BWR_WORKSPACE>/GUIDE.md` and applicable project instructions.

Use the recorded repository commit style. Project instructions remain authoritative.

## Scope

Commit only:

- work from your assigned commit scope;
- work that the current Workflow explicitly transfers into that scope.

Preserve every unrelated working-tree change.

Exclude `<BWR_WORKSPACE>` from the commit.

## Procedure

1. Inspect `git status`.
2. Inspect the relevant unstaged and staged diffs.
3. Stage explicit paths or hunks from the assigned scope.
4. Inspect the complete staged diff.
5. Remove any unrelated staged change.
6. Commit with the recorded style.
7. Inspect `git status` and the created commit.

After context compaction, a provider summary can call your earlier changes pre-existing.

Do not infer ownership from that wording. Compare the diff with your assignment before selecting changes.
