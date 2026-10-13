# 0001: Data model and dataset file

Status: approved by Aarno Aukia, 2026-10-13.

## Purpose

econoCI collects CI history once and analyzes it many times. The collector
writes one dataset file; rules and reports read it. A new rule or a changed
threshold then runs against an existing file without asking the CI platform
again.

This specification defines the records in that file, the file format, and the
code that reads and writes it. It follows the data model in
`docs/design-mvp.md` and extends it where noted.

## Principles

- **Raw first.** The file keeps what the platform said, next to what econoCI
  made of it. A normalized value is stored together with the platform's own
  value, so a wrong mapping can be found and corrected from the file.
- **Names as collected.** The file holds repository, ref, job and user names
  as they are on the platform. Replacing them by keyed hashes is a separate
  step that turns one dataset file into another (specification 0004).
- **Platform-neutral.** Nothing in the record layout is specific to GitLab.
  Only GitLab is checked against it in the MVP.
- **Strict reading.** A file that does not match this specification is an
  error that names the line. Nothing is skipped silently.

## The file

- JSON Lines, UTF-8, compressed with gzip. Conventional name:
  `<something>.jsonl.gz`.
- Each line is one JSON object with a `kind` field: `meta`, `run`, `job`,
  `change_request` or `config`.
- The first line is the `meta` record. Exactly one `meta` record exists.
- The writer emits `meta`, then runs, jobs, change requests and configs, each
  group in the order given. Keys are written in the order of the tables
  below. The same dataset always gives the same bytes inside the gzip stream.
- `format` in the `meta` record is the format version. This specification
  defines version `1`. Until the first release of econoCI the format may
  change without a new number. After that, a change needs a new number.

## Common rules for fields

- Ids are strings, unique within their kind.
- Timestamps are ISO 8601 strings with a UTC offset.
- "Nullable" means the key is present with the value `null` when the platform
  gave nothing. "Optional" means the key may be absent.
- A key that this specification does not define is an error.

## Records

### `meta`

| Key | Type | Meaning |
| --- | --- | --- |
| `kind` | `"meta"` | |
| `format` | integer | Format version, `1` |
| `platform` | string | `gitlab` |
| `collector` | string | Name and version of the program that wrote the file |
| `collected_at` | timestamp | When the collection finished |
| `period_start` | timestamp | Start of the collected period |
| `period_end` | timestamp | End of the collected period |
| `pseudonymized` | boolean | `true` when names and ids are keyed hashes |
| `repositories_seen` | integer | Repositories the collector looked at |
| `repositories_with_runs` | integer | Of those, repositories with at least one run in the period |
| `repositories_unreadable` | integer | Of those, repositories the collector could not read |

### `run`

A pipeline or workflow run.

| Key | Type | Meaning |
| --- | --- | --- |
| `kind` | `"run"` | |
| `id` | string | |
| `repository` | string | |
| `ref` | string, nullable | Branch, tag or change request ref |
| `ref_kind` | enum | `default`, `branch`, `change_request`, `tag` |
| `commit` | string, nullable | Commit hash |
| `trigger` | enum | See "Normalized values" |
| `platform_trigger` | string | The platform's own value |
| `status` | enum | See "Normalized values" |
| `platform_status` | string | The platform's own value |
| `actor` | string, nullable | User that started the run |
| `actor_bot` | boolean, nullable | The platform's own bot flag for that user |
| `actor_kind` | enum, optional | `person`, `bot`, `unknown`. See "Person or bot" |
| `root_trigger` | enum, nullable | Trigger of the run at the top of the chain. `null` when the chain could not be resolved |
| `root_platform_trigger` | string, nullable | |
| `root_actor` | string, nullable | |
| `root_actor_bot` | boolean, nullable | |
| `root_actor_kind` | enum, optional | |
| `parent_run` | string, nullable | Id of the run that started this one |
| `change_request` | string, nullable | Id of the change request this run belongs to |
| `created_at` | timestamp | |
| `finished_at` | timestamp, nullable | `null` while the run is not finished |

For a run with no parent, the `root_*` fields repeat the run's own values. The
design asks rules to use the root trigger; with this, a rule reads `root_*`
for every run and needs no special case. The design lists the root trigger
only. The root actor is added here because the prototype needed it to tell a
pipeline relayed by a bot from one a person started.

### `job`

| Key | Type | Meaning |
| --- | --- | --- |
| `kind` | `"job"` | |
| `id` | string | |
| `run` | string | Id of the run. The run must be in the file |
| `name` | string | |
| `stage` | string, nullable | |
| `status` | enum | See "Normalized values" |
| `platform_status` | string | |
| `failure_reason` | enum, nullable | `timeout`, `script`, `runner`, `other`. `null` when the job did not fail |
| `platform_failure_reason` | string, nullable | |
| `allow_failure` | boolean | |
| `attempt` | integer | `1` for the first execution, counting up for retries |
| `created_at` | timestamp | |
| `started_at` | timestamp, nullable | `null` when the job never started |
| `finished_at` | timestamp, nullable | `null` when the job has not finished |
| `queued_seconds` | number, nullable | Queue time as the platform reports it |
| `duration_seconds` | number, nullable | Run time as the platform reports it |
| `runner` | string, nullable | Id of the runner that took the job |
| `runner_type` | string, nullable | The platform's own value |
| `tags` | list of strings | Runner tags or labels the job asked for |

`failure_reason` is not in the design. The `timeout-hit` rule needs it.

### `change_request`

A merge request or pull request.

| Key | Type | Meaning |
| --- | --- | --- |
| `kind` | `"change_request"` | |
| `id` | string | |
| `repository` | string | |
| `source_ref` | string | |
| `state` | enum | `open`, `merged`, `closed` |
| `platform_state` | string | |
| `author` | string, nullable | |
| `author_bot` | boolean, nullable | |
| `author_kind` | enum, optional | |
| `merger` | string, nullable | `null` when not merged |
| `merger_bot` | boolean, nullable | |
| `merger_kind` | enum, optional | |
| `auto_merge` | boolean | Set to merge automatically when checks pass |
| `created_at` | timestamp | |
| `merged_at` | timestamp, nullable | |

### `config`

| Key | Type | Meaning |
| --- | --- | --- |
| `kind` | `"config"` | |
| `repository` | string | |
| `path` | string | Path of the CI file in the repository |
| `ref` | string | The ref it was read from, the default branch |
| `text` | string | The file as written |

The design says "parsed CI file". The file is stored as text instead: the
collector uses the standard library only, which has no YAML parser. Parsing
belongs to the analysis, in the specification of the first rule that needs it.
Includes are not resolved.

## Normalized values

The collector maps the platform's values to these. The mapping for GitLab is
in specification 0002.

A run that another run started always has the trigger `upstream`, whether or
not its parent could be found. The reader relies on this to tell such a run
from a top-level one, so a collector must map every platform value that can
have a parent to `upstream`.

- **Trigger:** `push`, `change_request`, `schedule`, `manual`, `upstream`,
  `api`, `other`.
- **Status:** `success`, `failed`, `canceled`, `skipped`, `running`, `other`.
- **Ref kind:** `default`, `branch`, `change_request`, `tag`.

## Person or bot

Whether an actor is a person or a bot is derived when the file is read, not
decided when it is collected. The rule is a heuristic and will change; with
the name in the file it can change without collecting again.

The kind of an actor (`actor`, `root_actor`, `author`, `merger`) is:

1. the stored `*_kind`, when the key is present;
2. otherwise `unknown`, when the name is `null`;
3. otherwise `bot`, when the platform's bot flag is `true`;
4. otherwise `bot`, when the name matches a bot pattern;
5. otherwise `person`.

For the author of a change request there is one more way to be a `bot`,
checked after step 4: the source ref matches `renovate` or `dependabot`.

Bot patterns, matched without regard to case, taken from the prototype as a
starting point:

- contains `bot`, `renovate` or `dependabot`;
- starts with `project_<digits>` or `group_<digits>` (GitLab access tokens);
- contains `service`, `deploy` or `token`.

The patterns live in one place in the code and each has a test.

In a pseudonymized file names are hashes and the patterns cannot match. Such a
file therefore carries every `*_kind` key. A reader fails on a file whose
`meta` says `pseudonymized: true` and that lacks one. A file that is not
pseudonymized normally leaves the `*_kind` keys out.

## Reading

An error names the file and the line, and nothing is returned, when:

- the file is not gzip or is cut short, or a line is empty or not a JSON
  object;
- a line has the same key twice, or is longer than 16 MiB;
- the file holds more than 2 GiB of text once unpacked;
- a number is not finite, or a text cannot be written as UTF-8;
- the first line is not a `meta` record, or a second `meta` record appears;
- `format` is not `1`;
- `kind` is unknown;
- a required key is missing, a key is not defined here, or a value has the
  wrong type;
- an enum has a value not listed here;
- a timestamp has no UTC offset or does not parse;
- two records of one kind share an id;
- a job names a run that is not in the file;
- a run names itself as its parent;
- a run that was not started by another run (`parent_run` is `null` and
  `trigger` is not `upstream`) has `root_*` fields that differ from its own
  values, the stored kind included;
- a run that was started by another run has the `root_trigger` `upstream`
  (an unresolved chain is `null`), has a `root_trigger` without a
  `root_platform_trigger`, or has other `root_*` values next to a `null`
  `root_trigger`.

An error message shows a value from the file escaped and cut to a short
length, so a file cannot alter a terminal or forge a line in a log.

Allowed, because the other record can lie outside the collected period or in
a repository the collector could not read:

- a run whose `parent_run` is not in the file;
- a run whose `change_request` is not in the file.

## Code

- `src/econoci/model.py`: frozen dataclasses `Meta`, `Run`, `Job`,
  `ChangeRequest`, `Config`, and `Dataset`, which holds one `Meta` and the
  lists of the others. Timestamps are aware `datetime` objects. The derived
  kinds are available on the records.
- `src/econoci/dataset.py`: `read(path)` returns a `Dataset`, `write(dataset,
  path)` writes one, `DatasetError` is raised for every case under "Reading".
  `write` checks the dataset by the same rules before it writes, and the file
  appears under its name only when it is complete, so a failed write leaves a
  previous file at that path untouched.
- Both use the standard library only and run on Python 3.11, since the
  collector imports them.

## Personal data

A dataset file that is not pseudonymized contains usernames, and whatever
people put into branch and job names.

- Such a file is never committed. `*.jsonl.gz` is in `.gitignore`, and tests
  use synthetic data only.
- Real dataset files are kept outside the repository's working tree.

## Tests

Written first, from small synthetic datasets with invented names.

- A dataset with every record kind and every nullable field in both states
  survives write and read unchanged.
- Writing the same dataset twice gives the same uncompressed bytes.
- Each case under "Reading" raises `DatasetError` naming the line.
- The two allowed dangling references are accepted.
- Each normalized value is accepted, and one outside the list is rejected.
- Each step of "Person or bot" is covered, each bot pattern has a matching and
  a non-matching name, and a stored kind wins over a derived one.
- A pseudonymized file without a `*_kind` key is rejected.
- A top-level run carries its own values in the `root_*` fields.

The test session runs on Python 3.11 and 3.14 from here on, because
`src/econoci/` has to run on 3.11.

## Not included

- Collecting. Specification 0002.
- The report. Specification 0003.
- Pseudonymizing a file. Specification 0004. This specification only defines
  the `pseudonymized` flag and the `*_kind` keys it relies on.
- Commit titles, artifact sizes, the configured job timeout, the number of
  comments on a change request. A rule that needs one adds it with its own
  specification.
- Cost in money.
- Reading older format versions. There is only one.
