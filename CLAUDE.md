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
- **Mark AI-assisted commits** with the co-author line and the `AI-assisted`
  block from `specs/provenance-log.md`. Run
  `python3 tools/prompts_since_commit.py` and read `git diff --cached`. Draft
  `Prompts` from the prompts that shaped the staged diff, in a few lines, and
  `Output` from the diff. `Human` states what is true now and never claims a
  review that has not happened. Show the full commit message with
  `git diff --cached --stat`, name every change no prompt asked for, list the
  prompts left out of the block, and commit only after explicit approval, with
  the message exactly as approved.
- **One commit per unit of work the person asked for.** Do not split work that
  follows from a single instruction into commits with no prompt of their own.
- **Merge with a merge commit, and only when told to.** A person's merge of a
  pull request is their review and approval and needs no trailer. When told to
  merge, add `Reviewed-by: <name> <email>` naming that person to the merge
  commit message. Never add that trailer in any other situation. An
  AI-assisted commit that reaches `main` without a person's merge commit needs
  the trailer itself, and a squash also needs the blocks of the squashed
  commits.

## Stack

Python, `uv`, `nox` with the uv backend, `ruff`. The collector uses the
standard library only so it runs anywhere a customer has Python 3.11.

## Layout

The product goes under `src/econoci/` as the design describes. Project tooling
that is not part of the product goes under `tools/`.
