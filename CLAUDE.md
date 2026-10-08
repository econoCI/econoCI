# CLAUDE.md

Guidance for Claude Code in this repository.

## What this is

econoCI finds wasted CI runner time and proposes changes, for GitLab first,
then Forgejo and GitHub. The purpose: CI that is faster, cheaper and wastes
fewer resources, to the benefit of developers, society and the environment.
Read `docs/design-mvp.md` first. Apache-2.0.

## Working rules

- **Specification first.** Work on a feature or rule only when a
  file under `specs/` describes it. If none exists, ask for one; do not write
  it yourself.
- **Write the failing test first**, watch it fail, then implement.
- **Synthetic test data only.** Never commit fetched job data, tokens, or
  anything naming a customer, a customer project or a person.
- **Rules are deterministic plain functions.** No language model at run time,
  no network calls except to the CI platform's API.
- **Rules use the root trigger**, not the actor alone.
- **Mark AI-assisted commits** with the co-author line.

## Stack

Python, `uv`, `nox` with the uv backend, `ruff`. The collector uses the
standard library only so it runs anywhere a customer has Python 3.11.

## Layout

The product goes under `src/econoci/` as the design describes.
