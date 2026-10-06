# Agent Workflow

## Rules

- Preserve existing functionality.
- Do not make unrelated changes.
- Inspect actual code before deciding.
- Do not install dependencies unless explicitly requested.
- Do not delete files unless explicitly requested.
- Execute only the requested task.
- Prefer targeted inspection over exhaustive repository reading.
- Write detailed results to the requested report file.
- Keep chat response concise.

## Execution

When given a task:

1. Identify the minimum files needed.
2. Inspect entry points and dependencies.
3. Trace relevant callers/imports.
4. Perform the requested work.
5. Validate the result.
6. Write detailed findings to the specified report.
7. Return only a concise summary.