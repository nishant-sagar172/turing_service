# Fable Prompt Skill (`/fable-prompt`)

A Claude Code skill for unknowns-first prompting and implementation.

## Install in Claude Code

Project-only install:

```bash
mkdir -p .claude/skills
cp -R fable-prompt .claude/skills/fable-prompt
```

Personal install across projects:

```bash
mkdir -p ~/.claude/skills
cp -R fable-prompt ~/.claude/skills/fable-prompt
```

Then start Claude Code and run:

```text
/fable-prompt
```

or:

```text
/fable-prompt Build a new onboarding dashboard and help me discover the unknowns first
```

## Upload to claude.ai

Zip the outer `fable-prompt` folder and upload it as a custom Skill in Claude settings, if your plan supports custom Skills.

## Recommended use

Use `/fable-prompt` at the start of ambiguous work. The skill will interview you one question at a time, do a blind-spot pass, brainstorm/prototype where useful, create an implementation plan, implement only after approval, keep notes, and produce a final explainer plus quiz.
