# econoCI

Find wasted CI runner time and say what to change.

econoCI optimizes CI pipelines and the infrastructure they run on: CI that is
faster, cheaper and wastes fewer resources. Developers wait less, and less
compute and energy is spent for nothing, which benefits society and the
environment.

Status: design only. Nothing here is ready to use.

- `docs/design-mvp.md`: what the first version does.

## Use of generative AI

econoCI is developed with an AI coding assistant (Claude Code, Anthropic),
used for design, code, tests and documentation. A person directs the work,
decides what is built and reviews every change before it is merged.

AI-assisted commits carry a `Co-Authored-By:` line naming the model.
econoCI itself uses no language model at run time.

License: Apache-2.0.
