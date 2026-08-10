---
name: flow-builder-visualizer
description: Visualize plans, existing code, workflows, freeform descriptions, or existing diagrams as Mermaid, and save them to disk. Project-agnostic. Use for "visualize", "diagram this", "draw the flow", "map out", "architecture diagram", "sequence diagram", "flowchart", "ER diagram".
---

Draw a Mermaid diagram, show it inline, then save it to a file — never leave it as disposable chat output.

## Source & scope
Identify what's being drawn: existing code, a plan/spec from this conversation, a freeform description, or an existing diagram/image to reproduce. If the scope is ambiguous (which flow, not "the whole app"), ask first.

## Accuracy
- Code: trace real call chains (Grep/Read, or an Explore agent for unfamiliar code) — don't infer from names. Tag key nodes with `file:line`. Only include what's relevant to the asked flow.
- Plan/description: only what was actually discussed/described — don't invent steps.
- Existing diagram/image: reproduce faithfully first, note any changes after.
- Never add a node/edge you can't ground in the source.

## Diagram type
sequenceDiagram (call order) · flowchart (branching/logic) · stateDiagram-v2 (states) · erDiagram (data model) · flowchart+subgraphs (architecture). Pick the narrowest one that answers the question — prefer several small diagrams over one giant one.

## Render
Always inline as a ` ```mermaid ` block first. Suggest an Artifact only if it's too large/dense for inline, or the user wants it shareable.

## Persist
Check for an existing convention first (`**/*.mmd`, `**/diagrams/**`, mermaid blocks under `docs/**`) and match it. Otherwise create `docs/diagrams/<kebab-case-name>.md`: title, one-line context (source, date), then the diagram. Keep `docs/diagrams/INDEX.md` as a flat list: `- [Title](file.md) — description`.

Before writing a new file, check the index for the same flow already diagrammed — update in place instead of duplicating. If a diagram is derived from code that has since changed, say so rather than trusting the stale file.
