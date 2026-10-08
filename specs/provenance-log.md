# AI provenance in commit messages

Status: approved by Aarno Aukia, 2026-10-08, with the changes of that day.

## Purpose

econoCI is built with a generative AI assistant and might apply for NLnet
funding. NLnet's policy on generative AI, version 1.1
(<https://nlnet.nl/foundation/policies/generativeAI/>, read 2026-10-08), says
about project development:

> Generated content should be marked as such. When adding (partially)
> generated code, make sure the provenance is clear for each such
> contribution. Specify which model was used, (including version), and how it
> was used. Provide the used prompts/interactions and resulting output, or a
> summary thereof.

Its example is git: distinguish the commits that add generated code and put
the model and prompts in the commit message, with the commit itself as the
output. It also asks that the information sits where it is easily found, not
on a third-party platform that needs a login or may disappear.

This specification meets that with a block in each AI-assisted commit message.
No conversation transcript is published.

## The block

Every commit that contains AI-assisted content has this block in its message
body, after the usual description and before the trailers:

```
AI-assisted: Claude Code, model <model id>
Prompts: <summary of the prompts that shaped this commit>
Output: <what the model produced in this commit>
Human: <what the person decided, changed or verified>
```

- `AI-assisted` names the tool and the model id as the session reports it, for
  example `claude-opus-5-5`. If several models produced output, all are
  listed.
- `Prompts` summarizes the prompts that shaped this commit: the request behind
  it, and the decisions and corrections that are visible in its diff. It is
  not a record of the conversation. A direction that was tried and dropped
  left no trace in the diff and is left out. A prompt belongs to the commit
  where its effect lands. The field is a few lines long; short instructions
  that shaped the result are quoted.
- `Output` says which parts of the commit the model drafted. The diff is the
  output itself.
- `Human` records what the person did beyond asking: a proposal rejected, a
  mistake corrected, a result read or tested. It states what is true when the
  commit is made and never claims a review that has not happened yet. Review
  is recorded at the merge (see "From a branch to main").
- Each field may run over several lines. Continuation lines are indented by
  two spaces.
- The block is plain committed text. It names no customer, customer project or
  person other than contributors, and contains no tokens.

The `Co-Authored-By:` trailer stays. It is what marks a commit as AI-assisted.

A commit covers one unit of work the person asked for. Work that follows from
a single instruction is not split into commits that have no prompt of their
own.

## Writing and approving the block

1. Before committing, the assistant stages the changes, collects the prompts
   since the last commit (see the helper below) and reads the staged diff. The
   helper's output is the list of candidates. The assistant drafts `Prompts`
   from the candidates that shaped the staged diff, and `Output` from the
   diff.
2. The assistant shows the full commit message, block included, to the person
   in the conversation, together with the summary of the staged diff
   (`git diff --cached --stat`). It names every change in the diff that no
   prompt asked for, and lists the prompts it left out of the block. Left-out
   prompts are shown to the person and are not committed. Then it waits.
3. The person approves it or changes it. The assistant commits only after an
   explicit approval, with the message exactly as approved.

This is a comparison of the prompts with the diff, not a code review. The
diff shows what changed, not who typed it, so the `Human` field depends on the
person's correction at this step.

A commit made by the person alone, with no AI-assisted content, has neither
the trailer nor the block.

## Helper: prompts since the last commit

The assistant's memory of a conversation is not a reliable source: a session
can be cleared or compacted, and work between two commits can span several
sessions. The summary is therefore drafted from the transcripts Claude Code
keeps locally.

`tools/prompts_since_commit.py`:

- reads the local Claude Code transcripts for this repository;
- prints, in time order, every prompt the person typed and every answer the
  person gave to a question from the assistant, with its timestamp and the
  model id in use, from the author date of `HEAD` onward. The author date
  is used because an amend or a rebase moves the committer date past prompts
  that belong to the next commit;
- prints to the terminal only. It writes no file and nothing it prints is
  committed as is;
- leaves out text injected by the harness (system reminders, skill bodies,
  hook context), tool output, and the assistant's replies;
- stops with an error naming any transcript record type it does not know. The
  transcript format is internal to Claude Code and can change;
- standard library only, no network calls, no language model.

It lives under `tools/`, outside `src/econoci/`: it is project tooling, not
part of the product.

## Checks

`tools/check_commit_messages.py <revision range>` fails when a commit in the
range has a `Co-Authored-By:` trailer naming an AI model and lacks the block
or any of its four fields. A `nox` session runs it over every commit after
`8076110`, the initial commit, which predates this specification.

It checks that the block is present and complete. It cannot check that the
summary is true. The person's approval is the control for that.

`tools/check_review_trailers.py <revision range>` fails when an AI-assisted
commit reached `main` without a recorded review (next section). A `nox`
session runs it over `8076110..main`. It checks `main` and not the current
branch, because commits on a branch are not reviewed yet.

## From a branch to main

The approved message has to arrive on `main` unchanged, and the review has to
be on record in the repository.

- Branches are merged with a merge commit. It keeps every commit message, so
  each block reaches `main` as approved, and `git log` on `main` shows it.
- The person reviews the code before the merge, usually in the pull request.
  The review is recorded in the merge commit message with the trailer
  `Reviewed-by: <name> <email>`, naming the person who reviewed. The merge
  commit is the one point in the history that lies after the review.
- The merge commit is the person's commit. It has no `Co-Authored-By:` trailer
  and no block.
- The assistant merges only when the person tells it to. That instruction
  means the person has reviewed the branch, and the assistant adds the trailer
  naming that person. It never adds the trailer in any other situation.
- An AI-assisted commit that reaches `main` without a merge commit (a rebase
  merge, a squash merge, a commit made directly on `main`) carries the
  `Reviewed-by:` trailer itself. A squash is allowed only when its commit
  message also carries the blocks of the squashed commits, merged into one
  block.
- The rule the review check enforces: on the first-parent history of `main`, a
  merge commit that brings in at least one AI-assisted commit has a
  `Reviewed-by:` trailer, and an AI-assisted commit that is not brought in by
  a merge commit has one itself. A trailer that names an AI model does not
  count.
- The pull request description is not a provenance record. It lives on the
  platform, not in the repository.

## Repository text

- `README.md`, section "Use of generative AI": the sentence about
  `Co-Authored-By:` is extended to say that each AI-assisted commit message
  summarizes the prompts and names the model.
- `CLAUDE.md`, working rules: the rule "Mark AI-assisted commits" is extended
  with the block and the approval step, and a rule on merging states the
  merge commit, the `Reviewed-by:` trailer and when the assistant adds it.

## Tests

Written first. Transcripts and commit messages in `tests/` are synthetic.

Helper:

- typed prompts and question answers after the cut-off are printed in order
  with timestamps; earlier ones are not;
- prompts from several sessions are merged in time order;
- harness-injected text, tool output and assistant replies do not appear;
- an unknown record type is an error that names it.

Check:

- AI trailer with a complete block passes;
- AI trailer with no block, or with a field missing, fails and names the
  commit and the field;
- a commit with no AI trailer passes without a block;
- multi-line fields are accepted.

Review check, each case built as a small git history:

- a merge commit with the trailer that brings in AI-assisted commits passes;
- the same merge commit without the trailer fails and names it;
- a merge commit that brings in no AI-assisted commit passes without one;
- an AI-assisted commit directly on the first-parent line fails without the
  trailer and passes with it;
- a trailer that names an AI model does not count;
- commits of a merged branch are not themselves required to carry it.

This introduces the repository's first `pyproject.toml` and `noxfile.py`
(`uv`, `nox`, `ruff`), with sessions for tests, lint and the check.

## Not included

- Publishing conversation transcripts, in full or redacted.
- A `commit-msg` git hook. The check runs through `nox`, and later in CI.
- The disclosure for the grant application. The proposal form asks, when
  generative AI was used in writing the proposal, for the model, what it was
  used for, and the prompts and output pasted (up to 8000 characters) or
  uploaded as a file. That goes to NLnet with the proposal and is prepared
  from the local transcripts, not kept in this repository.
- Generative AI used outside Claude Code.

## Known risks

- The summary is written by the model about its own conversation, and the
  model selects which prompts it covers. Nothing compares it with the
  transcript except the person's review of the message and of the left-out
  prompts.
- `Reviewed-by:` is an assertion. Nothing proves that the review happened or
  how careful it was. It makes one named person accountable in the history.
- Claude Code deletes old transcripts after a retention period. Questions from
  NLnet about a commit, and the proposal disclosure, can be answered from the
  transcripts only while they still exist. Keeping a private copy is the
  person's responsibility and outside this specification.
