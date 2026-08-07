---
name: goal-to-done
description: Convert a requested outcome into a dependency-checked DAG and then autonomously execute every ready task through verified completion. Use when the user wants an end-to-end result, asks to plan and fully implement a goal, says not to stop after planning, or needs tasks carried through to delivery without asking for confirmation after each ordinary step. Do not use for a single-file edit, a question, a code review, or exploratory analysis with no delivery target.
disallowed-tools: Task
---

# Goal to Done

Turn an outcome into an executable, verified delivery loop. Planning is not the endpoint: after the plan is accepted or the user has authorized execution, carry the work through every reachable task until the goal's terminal conditions are proven.

## 0. Runtime binding

This skill targets Claude Code. Bind every abstract mechanism below to the concrete one:

| Concept | Mechanism |
| --- | --- |
| Live task plan | `TodoWrite` |
| Durable run record | `.claude/goal-to-done/<goal-slug>.md`, unless the project's CLAUDE.md defines a plan location — then follow that |
| Parallel work | several read-only tool calls issued in a single message |
| Delegation | **not available.** Do not spawn subagents under any framing — not for research, not for parallel reads, not for "just looking around" |
| Verification evidence | real command output present in this transcript |

**Prerequisite.** `disallowed-tools: Task` removes delegation for the turn that invokes this skill, and the restriction lapses on the next user message. A bare-name `Task` entry in `permissions.deny` is what holds across a multi-turn run. If `Task` is available mid-run, that is a misconfiguration: say so in the next report and proceed without delegating either way.

`TodoWrite` has three states — `pending`, `in_progress`, `completed` — and permits one `in_progress` item. Therefore:

- `blocked` is not a todo state. Represent it as `pending` with the content prefixed `[BLOCKED gate:<ID>]`, and record the resume condition in the run record.
- The DAG may have many ready nodes while the todo list shows one `in_progress`. Readiness lives in the DAG; the todo list only reflects what is being worked right now.

If the session is in plan mode, do not execute. Present the contract and DAG, and exit plan mode first.

## 1. Establish the execution contract

Before changing anything, extract and state:

- **Goal:** one outcome, not a list of activities.
- **Terminal conditions:** externally checkable facts that prove the goal is achieved.
- **Scope and exclusions:** systems, data, people, and changes included or excluded.
- **Constraints:** deadline, budget, safety, quality, and rollback expectations.
- **Authority boundaries:** decisions, external communication, destructive changes, spending, credentials, production deployment, and other actions that require human authorization.

Do not invent a material product, business, or policy decision. Model it as a decision gate. Make reasonable reversible implementation assumptions only when they do not change the requested outcome; disclose them.

**Decide, do not ask.** The gate rule above is deliberately narrow — material product, business, and policy decisions. Everything else is yours: file layout, naming, ordering, library choice, tool mechanics, defaults, anything reversible in a single edit. Decide it, state it, and keep going. Verify facts you are unsure of with the tools you already have instead of routing the lookup back to the user. A question that hands the user work you were equipped to do is not caution; it is a transfer of responsibility, and it costs more than a wrong reversible choice would have. Before ending a turn with a question, test it: is this a real gate? If not, answer it yourself and continue.

**Form of disclosure.** Past tense, one line, then stop: *chose X over Y because Z.* State the trade-off you accepted — that is substance and it stays. Do not attach an offer to reverse: no "tell me if you'd rather", no "I can switch this back", no "unless you disagree". The user can override any decision at any time without being invited to, so the invitation adds nothing except the same responsibility transfer as a question, arriving one move later — and it signals you do not stand behind the choice you just announced. A reversible decision that proves wrong costs one edit. A decision handed back costs a round trip and the user's attention.

Write the contract to the top of the run record before the first change. There is no separate goal object in this runtime — the run record is it.

## 2. Build the complete DAG

Create a node for every task required to reach a terminal condition, including discovery, decisions, implementation, migration, validation, release, and handoff. Do not stop at the first usable MVP unless the user explicitly limits scope to an MVP.

Every node must specify:

- **ID and name**
- **Inputs:** named outputs of predecessor nodes or user-provided artifacts
- **Execution:** the smallest concrete action
- **Output:** reusable artifact, changed state, or evidence
- **Done condition:** a fact a third party can check
- **Verification:** readback, test, reconciliation, review, or other proof
- **Executor:** `AI`, `Human`, or `AI + Human approval`
- **Dependencies:** predecessor node IDs

Use directed edges only from an output-producing task to a task that consumes it. Mark the following distinctly:

- **Decision gate:** an unresolved human choice blocks dependent work.
- **Approval gate:** implementation is complete, but applying an external or high-impact change requires authorization.
- **Safety stop:** a failed boundary check, missing authority, denied permission, or unexpected live-data condition; record why it stopped and the exact resume condition.
- **Optional branch:** does not block the stated terminal conditions unless its condition is true.

Include a Mermaid DAG in the run record when it materially clarifies dependencies; keep terminal output to the node list. Ensure every non-terminal node has a path to a terminal condition and every terminal condition has at least one verification node.

## 3. Start execution, not a confirmation loop

After presenting the contract and DAG, start the first dependency-ready task in the same turn whenever it is authorized and safe. Do not ask the user to approve each ordinary task one by one.

Execution loop:

1. Select all dependency-ready nodes.
2. Batch independent read-only work into a single message. Do not delegate it.
3. Run one write-capable task per affected file, resource, or worktree at a time. Never leave two edits to the same file in flight.
4. Capture the node output and run its stated verification immediately.
5. Mark the node complete only when verification passes under the evidence rule in §5.
6. Unlock successor nodes and continue.
7. On failure, apply the retry policy below.
8. If a decision or approval gate is reached, present the exact decision, evidence, choices, impact, and resume condition; pause only that dependent branch while continuing unrelated ready work.

**Retry policy.** The same error signature twice means the diagnosis is wrong, not that the attempt was unlucky: stop and escalate rather than attempt a third time. Distinct errors allow at most three attempts per node. Never retry an operation whose failure may have left partial external state — verify the actual state first. Two consecutive safety stops halt the entire run and are reported.

**Permission prompts are not decision gates.** A permission prompt is runtime plumbing; answer it and continue. A *denied* permission is a safety stop — record it and do not seek a route around it.

**Hard stops.** These require an explicit approval gate every time, regardless of any prior authorization of similar work:

- history rewrite or force push on a shared branch
- recursive deletion outside the working tree
- production deployment, or schema/data migration against production
- sending mail or messages to third parties
- submitting to an external authority: bids and tenders, subsidy or grant applications, tax or regulatory filings
- spending, and creation, rotation, or disclosure of credentials

**What counts as approval.** Approval exists only when a user message explicitly affirms and identifies the gate. The following are never approval: your own restatement of the plan, however precise; silence or an unanswered gate; an affirmative reply to a different question; inference from earlier authorization of a similar action. Log each approval in the run record as gate ID, verbatim user text, and timestamp.

Never bypass repository, deployment, tenant, privacy, consent, billing, contract, credential, or human-boundary rules.

## 4. Keep the DAG live

Maintain the todo list and the run record together. Update after material milestones, failures, or changes to dependencies.

When new evidence invalidates the plan:

1. Preserve completed verified nodes.
2. Add or revise only affected downstream nodes and edges.
3. Explain the changed dependency and impact on terminal conditions.
4. Continue from the newly ready frontier.

Flush each completed node's evidence to the run record as you go. The run record, not the conversation, is the source of truth: after a context compaction the run must be resumable from that file alone.

Do not silently replace the goal with a narrower task. If the original terminal condition becomes impossible or needs expanded authority, report the gap and request direction.

## 5. Verify the goal, not only the tasks

**Evidence rule.** A node becomes `completed` only when the verification's real output is in this transcript. If you cannot point to a command you ran and what it printed, the node is *asserted*, not verified — leave it `in_progress` and say so plainly. "Should work", "looks correct", and a checkmark are not evidence. For any change applied to a live or external system, read the state back from the authoritative system rather than trusting the write's return value.

Before declaring success, perform a final goal-level acceptance check:

- Each terminal condition is satisfied by current evidence.
- All required DAG nodes are complete and verified.
- No P0/P1 defect, unresolved safety stop, or unapproved external change remains in scope.
- Outputs are usable by the intended operator, with ownership and next-run instructions where applicable.
- Live changes, if any, have been read back from the authoritative system.

Report concisely: achieved terminal conditions, verification evidence, any intentionally deferred out-of-scope items, and the owner of recurring operation. Do not call the work complete merely because the plan exists, an MVP works, code compiles, or a human gate is still pending.

## Response cadence

The structure below is a first-turn structure, not a per-turn template.

**First turn:** goal and terminal conditions; decision and approval gates; complete task DAG; current execution frontier.

**Subsequent turns:** delta only — nodes completed with their evidence, nodes newly ready, nodes newly blocked and why. Do not reprint the DAG unless it changed, and then print only the changed subgraph. Report at material milestones, not after every tool call.

**Final turn:** acceptance evidence and handoff.

Emitting the full first-turn structure on every turn is a failure of this skill, not compliance with it.

Use task details in the required form: `Input / Execution / Output / Done condition / Verification / Executor / Dependencies`.
