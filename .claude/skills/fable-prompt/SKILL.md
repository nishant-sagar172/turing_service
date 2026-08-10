---
name: fable-prompt
description: Run an unknowns-first Fable workflow: blind-spot pass, brainstorm/prototype, interview, plan, implement with notes, explain, and quiz.
argument-hint: "[rough goal | discover | brainstorm | prototype | plan | implement | review | quiz]"
disable-model-invocation: true
---

# Fable Prompt Skill

Use this skill when the user invokes `/fable-prompt` to turn a rough idea into a clarified plan and, when appropriate, an implementation.

The core operating principle: the prompt is only the map; the real work is the territory. Your job is to reduce the gap between the user's map and the real territory by discovering known knowns, known unknowns, unknown knowns, and unknown unknowns before, during, and after implementation.

## Invocation behavior

The user may invoke this as:

- `/fable-prompt` — start from scratch and interview the user step by step.
- `/fable-prompt <rough task>` — use the task as the initial known known and begin the workflow.
- `/fable-prompt discover` — run intake, blind-spot pass, unknowns board, and interview only.
- `/fable-prompt brainstorm` — run intake, blind-spot pass, and solution brainstorming.
- `/fable-prompt prototype` — run intake, blind-spot pass, and create quick prototypes or mockups before implementation.
- `/fable-prompt plan` — produce or refine an implementation plan from the current context.
- `/fable-prompt implement` — implement an approved plan, or ask for the missing plan/approval.
- `/fable-prompt review` — produce an explainer, risk review, and quiz after implementation.

If `$ARGUMENTS` is empty, vague, or simply `prompt`, start with the Discovery Interview. Treat `prompt` as an alias for the default `/fable-prompt` workflow, not as a separate command name.

## Non-negotiable behavior

1. Do not dump all questions at once.
2. Ask one high-leverage question at a time, then wait for the user's answer.
3. Prioritize questions where the answer would change architecture, user experience, data model, scope, safety, cost, or implementation strategy.
4. Skip questions that are irrelevant, already answered, or unlikely to affect the plan.
5. Do not implement until there is either an approved plan or an explicit instruction to proceed without further approval.
6. If you encounter an unknown during implementation, choose the conservative option, log it, and continue only if the choice is reversible and low-risk. Otherwise, stop and ask.
7. Maintain a visible Unknowns Board during discovery and planning.
8. Prefer prototypes, references, and concrete examples whenever the user appears to have “I’ll know it when I see it” preferences.

## Phase 0 — Start the session

Begin by creating a compact working summary in the conversation:

```md
## Fable Session
Goal: [unknown or user-provided]
Current starting point: [unknown]
Known knowns: []
Known unknowns: []
Unknown knowns to surface: []
Unknown unknowns to investigate: []
References: []
Implementation status: Not started
```

Then ask the first missing high-leverage question. Usually start with:

> What are we trying to create or change, and what would make the result feel successful?

If the user already gave a clear task, instead ask:

> What is your current starting point: what do you already know, what are you unsure about, and how familiar are you with this codebase/domain?

## Phase 1 — Discovery Interview

Ask one question at a time. Choose from this bank based on the current context.

### Goal and success

- What are we building, fixing, or deciding?
- What does “done” look like?
- What would make this feel excellent rather than merely functional?
- Is the priority speed, quality, creativity, safety, performance, polish, or learning?

### User starting point

- What do you already know about the problem?
- What are you aware you have not figured out yet?
- Are you new to this codebase/domain, or do you already know the patterns?
- Are there parts where you want me to teach you before building?

### Territory and constraints

- Where should I look first: files, folders, docs, tickets, designs, examples, or URLs?
- What must not change or break?
- What dependencies, frameworks, conventions, or product constraints matter?
- Are there performance, security, accessibility, privacy, legal, or cost constraints?

### Unknown knowns and taste

- Is this a “you’ll know it when you see it” problem?
- Would prototypes, mockups, or multiple options help before implementation?
- Do you have a reference implementation, website, component, screenshot, repo, video, or document I should study?
- What should the output feel like: premium, minimal, playful, cinematic, enterprise, fast, calm, dense, etc.?

### Implementation strategy

- Should I do a blind-spot pass across the repo/docs before proposing a plan?
- Should I brainstorm several approaches before choosing one?
- What level of autonomy do you want: ask before every major decision, or proceed with conservative choices and log deviations?
- How should we verify success: tests, screenshots, local run, demo, review checklist, metrics, or manual QA?

## Phase 2 — Blind Spot Pass

When the user approves or the task clearly requires it, perform a blind-spot pass.

For code tasks:

1. Inspect relevant files, directories, README, tests, package/config files, and existing patterns.
2. Identify hidden constraints, risky assumptions, prior art, edge cases, conventions, and likely failure modes.
3. Report findings using this structure:

```md
## Blind Spot Pass
What I inspected:
- ...

Likely unknown unknowns:
- ...

Risks and constraints:
- ...

Questions that would change the plan:
1. ...

Recommended next step:
- Brainstorm / Prototype / Plan / Ask one more question
```

For non-code tasks, inspect the provided material and domain context in the same way.

## Phase 3 — Brainstorm or Prototype

Use this phase when the solution space is unclear or the user has unknown knowns.

### Brainstorm mode

Generate 5–10 approaches from cheapest to most ambitious. For each approach include:

- What it is
- Why it might work
- Tradeoffs
- Risk level
- When to choose it

End by recommending 1–3 options and asking the user which resonates.

### Prototype mode

When the user needs to react visually or experientially:

1. Create the smallest useful prototype before touching production code.
2. Use fake data if needed.
3. Make options meaningfully different, not minor variants.
4. Ask the user which direction feels closest and what to change.

For web/product/UI work, prefer a single HTML prototype when practical.

## Phase 4 — Implementation Plan

Before implementation, produce a plan that leads with decisions the user is likely to care about.

Use this structure:

```md
## Implementation Plan

### Goal
...

### Key decisions for you to approve
1. Data model / interfaces: ...
2. User-facing behavior: ...
3. UX flow / copy / visuals: ...
4. Edge cases: ...
5. Verification plan: ...

### Proposed steps
1. ...
2. ...
3. ...

### What I will not change
- ...

### Risks
- ...

### Approval gate
Reply `implement` to proceed, or tell me what to change.
```

Bury mechanical refactoring details near the bottom unless they carry risk.

## Phase 5 — Implementation

Only enter this phase when the user explicitly approves the plan or directly instructs implementation.

Before changing files, create or update `implementation-notes.md` unless the project already has a better temporary notes location. Use the template in `templates/implementation-notes.md`.

During implementation:

1. Follow the approved plan.
2. Keep changes scoped.
3. Prefer reversible, conservative choices.
4. Log deviations under `Deviations`.
5. Log open questions under `Open Questions`.
6. Add or update tests when appropriate.
7. Run the smallest meaningful verification loop.
8. If a high-risk unknown appears, stop and ask the user before proceeding.

## Phase 6 — Post-implementation Explainer and Quiz

After implementation, produce a reviewer-friendly report. Use the template in `templates/explainer-and-quiz.md`.

Include:

- What changed
- Why it changed
- Files touched
- Key decisions
- Deviations from the plan
- How to verify
- Known limitations
- Follow-up recommendations
- A short quiz to confirm the user understands the change before merging or publishing

The quiz should test the actual behavior and tradeoffs, not trivia.

## Final response style

Be concise but useful. Maintain momentum. Whenever possible, end with one clear next question or one clear next action.
