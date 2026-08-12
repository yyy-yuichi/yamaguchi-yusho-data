# Work 1 repository boundary

These instructions apply to this repository and every path below it.

## Absolute separation rule

- This repository is Work 1. Work 2 belongs to another chat and another repository.
- Never discover, list, search, read, hash, copy, edit, execute in, stage, commit, push, or otherwise access Work 2 from a Work 1 task.
- Do not enumerate parent or sibling directories to find other works. Do not accept a sibling repository as an input, even for comparison.
- Comparison may use only a short, human-provided score or summary. It must not use a path, URL, checkout, artifact, or file owned by Work 2.
- Never delegate a Work 1 subtask to an agent with instructions to inspect another repository.

## Deny-by-default filesystem and Git scope

- The only allowed worktree is the repository root containing this file.
- Before any file mutation or Git write, run `python src/check_work_scope.py --repo .` from this repository and require exit code 0.
- For a command that names file targets, pass every target to the guard with repeated `--path` arguments before running the command.
- If the guard rejects the repository, origin, or any path, stop. Do not work around it, change the guard, or inspect the rejected target in the same task.
- Git operations may target only `origin` when it exactly matches the allowlisted Work 1 URL in `work_scope.json`.
- Do not use recursive globs, parent-directory searches, or cross-repository `git -C` commands outside this repository.

## Scope changes

- A request about Work 2 must be redirected to the Work 2 chat without inspecting it here.
- Changing `AGENTS.md`, `work_scope.json`, or `src/check_work_scope.py` is a security-boundary change. It requires explicit user intent, full tests, and independent readback before commit.
- UDC submission, account changes, paid services, deletion, and history rewriting remain separate approval gates.
