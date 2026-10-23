# 0001. Record architecture decisions

- Status: accepted
- Date: 2026-10-23

## Context

This project is a portfolio piece, so every significant design choice must be explainable, including
its alternatives and trade-offs.

Design decisions are easy to forget. Commit messages are too short to hold the reasoning, and they
are hard to find later. Without a written record, the "why" of the project lives only in the
author's memory.

## Decision

We will record each significant architectural decision as a short Architecture Decision Record (ADR):

- One Markdown file per decision in `docs/decisions/`, named `NNNN-short-title.md` with a four-digit,
  sequential number.
- Written in English, following [template.md](template.md).
- Once accepted, an ADR is not rewritten. If a decision changes, a new ADR supersedes it, and the old
  one only gets its status updated to point to the new one.

## Alternatives considered

- **Decisions only in the README**: it would grow long and unstructured, and it only shows the current
  state, not how we got there.
- **Commit messages only**: they are too short for real reasoning and are hard to search later.
- **A wiki**: it is not versioned together with the code, so it drifts away from it.

## Consequences

- Each significant decision costs a few minutes of writing.
- In exchange, there is a searchable history of why the project looks the way it does, which also
  serves as a script for explaining the project.
- Superseded ADRs stay in the repository, so earlier thinking is never lost.
