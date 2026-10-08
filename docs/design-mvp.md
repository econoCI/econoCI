# econoCI: MVP design

## Goal

A tool that reads an organization's CI history, finds work that costs runner
time for no benefit, and says what to change and how much it saves. It runs on
premises with no language model at run time, supports GitLab first, then
Forgejo and GitHub, and is published as open source.

Its purpose is to optimize CI pipelines and the infrastructure they run on:
CI that is faster, cheaper and wastes fewer resources. Developers wait less,
and less compute and energy is spent for nothing, which benefits society and
the environment.

## Non-goals for the MVP

- Opening merge requests. The MVP reports; it does not write.
- Enforcement.
- A hosted service, dashboards, accounts.
- GitHub and Forgejo adapters. The data model allows them; only GitLab ships.
- Any change to how jobs are scheduled. That is the runner's job.

## Modes

| Mode | Does | Needs | In the MVP |
| --- | --- | --- | --- |
| Report | Reads run history and CI files, ranks findings by minutes saved | Read-only token | Yes |
| Propose | Opens one merge request per finding, per repository opt-in | Write to branches and CI files | No, next |
| Enforce | Applies an organization's cost policy unless a repository opts out | Platform policy features, or the runner | No, later |

## How it works

1. **Collect.** For GitLab: jobs and merge requests for a period, with the
   root trigger of child pipelines resolved, names replaced by keyed hashes on
   request, and the CI configuration files.
2. **Normalize** into one platform-neutral model (below).
3. **Run rules.** Each rule is a plain function over the model.
4. **Report.** One Markdown or HTML file and one JSON file: findings sorted by
   estimated minutes saved per month, each with its evidence.

## Data model

Platform-neutral, so adapters only translate into it.

| Entity | Fields |
| --- | --- |
| Run (pipeline, workflow run) | id, repository, ref kind (default, branch, merge request, tag), trigger, root trigger, actor kind (person, bot), created, finished, parent run |
| Job | id, run, name, stage, runner label or tags, created, started, finished, status, allowed to fail, attempt |
| Change request (merge or pull request) | id, repository, source ref, author kind, merger kind, auto-merge, created, merged |
| Config | repository, path, parsed CI file at the default branch |

Trigger values are normalized: `push`, `change_request`, `schedule`, `manual`,
`upstream`, `api`, `other`. Lesson from the baseline (2026-10-05): the actor
alone misleads on both GitLab and GitHub, because bots relay people and child
pipelines hide their origin. Rules use the root trigger.

## Rule interface

```python
class Rule(Protocol):
    id: str            # stable, for example "schedule-overlap"
    safety: Safety     # ADVISORY, NEEDS_REVIEW, SAFE
    def findings(self, data: Dataset) -> Iterable[Finding]: ...

@dataclass(frozen=True)
class Finding:
    rule: str
    repository: str
    summary: str               # one sentence, plain words
    minutes_saved_month: float # estimated from the measured period
    evidence: dict             # the numbers behind the estimate
    suggestion: str            # what to change, in words
    patch: str | None = None   # filled from the Propose mode on
```

Rules are deterministic and have unit tests built from small synthetic
datasets. A rule states what it measured; it does not guess intent.

## First rules

All five come from findings on one self-hosted GitLab instance (30 days to
2026-10-05).

| Rule | Detects | Saving estimate | Measured example |
| --- | --- | --- | --- |
| `schedule-overlap` | A scheduled pipeline whose typical duration exceeds its interval | Runner time above one run at a time | Renovate: every 20 minutes, 41 minutes long, about 2,000 job-hours a month |
| `trigger-burst` | Many pipelines created within a minute by one upstream trigger | None in minutes; peak concurrency, reported separately | 195 jobs in 21 repositories at 09:33 on weekdays |
| `ignored-failures` | A job that fails repeatedly and is neither retried nor fixed | Its full runner time | 50 failures, 4 retries in one fan-out |
| `timeout-hit` | Jobs ending at the configured timeout | Time between typical duration and timeout | 99 runs of one job cut off at 60 minutes |
| `startup-dominated` | Jobs shorter than a threshold, several per pipeline | Per-job start overhead if merged | Median job 34 seconds |

Next candidates, each to be added only with a measured example: superseded
runs not cancelled, missing path filters, duplicate push and merge request
triggers, dependency updates not grouped, change requests merged before a job
finished (a job nobody waits for).

## Peak and delay section of the report

Besides the rules, every report states, from the same data:

- average and peak concurrent jobs, and the share of a peak-sized fleet in use;
- the share of runner time by root trigger and actor kind;
- how soon people act after a pipeline finishes (the ground-truth check).

This part shows how much runner capacity the load needs, and with consent it
is the telemetry worth keeping.

## Knowledge sources

Rules may be derived from published material on CI optimization (vendor
guides, platform documentation, engineering blogs, papers). Language models can
help read that material and draft rule candidates and test cases while the
tool is being built. Each rule records its source in a comment and is written
as our own code. Nothing from a customer is sent to a model.

## Privacy and telemetry

- Runs entirely where the customer runs it. No network calls except to the CI
  platform's API.
- Pseudonymized export is a separate, explicit command. The key stays local.
- Telemetry is opt-in and consists of the aggregate section only:
  shares, percentiles, counts. No names, no CI file contents.

## License

- Renovate, the closest model, is under the GNU Affero General Public License
  version 3 (its `license` file on GitHub, opened 2026-10-05).
- Choice to make: AGPL-3.0 keeps competitors from folding the rules into a
  hosted product without publishing changes, and still allows any company to
  run it internally. Apache-2.0 maximizes adoption and allows exactly that
  folding. Recommendation at the time: AGPL-3.0, the same as Renovate.
- **Decided 2026-10-08: Apache-2.0.**

## Repository layout (proposed)

```
src/<package>/collect/    adapters: gitlab.py first
src/<package>/model.py    the data model
src/<package>/rules/      one module per rule
src/<package>/report.py   Markdown, HTML, JSON
tests/                    synthetic datasets per rule
```

Python, `uv`, `nox`, `ruff`, as in this repository. Tests first.

## Milestones

1. Model and GitLab adapter. Report with the peak and trigger section only.
2. The five rules with tests. Run on the instance the findings came from and
   compare with the manual findings.
3. Run on additional GitLab instances (Aarno runs it). Adjust.
4. Publish. Propose mode for the two safest rules.

## Open questions

- Thresholds for each rule; they need a second data set.
