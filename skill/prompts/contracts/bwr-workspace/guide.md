# BWR Guide Contract

`GUIDE.md` contains the current run-specific Git guidance and approved Gate plan.

It uses this information structure:

```text
# BWR Guide

## Git

- Commit style: <short description>
- Language: <language>
- Scope rules: <rules or none>
- Project instructions: <paths>

## Gate

### Included commands

- <command> — <purpose>

### Excluded commands

- <command> — <reason>

### Execution groups

#### Group <number>

- <command>
```

Execution groups run in numerical order.

Commands inside one group can run in parallel. The next group waits for the complete previous group.

Every included command appears in exactly one execution group.

Every excluded command keeps its explicit exclusion reason.

Repository-specific details can add headings when the same information remains clear.
