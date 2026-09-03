# Workflow execution

## Fixed instruction files

Use this instruction for a fixed file:

```text
Read once; reread as needed: <file>
```

Read the file before first use. Later, reread it only when its exact content is no longer clear.

## Active Workflow

Reading a Workflow prepares its execution. Reading does not execute the Workflow.

`Execute` means follow the active Workflow until one stated Exit applies.

Execute one Workflow at a time.

Leave the active Workflow only through a stated Exit.

## Workflow transition

When an Exit names another Workflow:

1. Use `Read once; reread as needed:` for that Workflow.
2. Execute that Workflow.
