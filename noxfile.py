import nox

nox.options.default_venv_backend = "uv"
nox.options.sessions = ["lint", "tests", "commit_messages", "review_trailers"]

# The initial commit predates specs/provenance-log.md.
FIRST_CHECKED_RANGE = "8076110..HEAD"


@nox.session(python="3.14")
def tests(session):
    session.install("pytest")
    session.run("pytest", *session.posargs)


@nox.session(python="3.14")
def lint(session):
    session.install("ruff")
    session.run("ruff", "check", ".")
    session.run("ruff", "format", "--check", ".")


@nox.session(python="3.14")
def commit_messages(session):
    session.run("python", "tools/check_commit_messages.py", FIRST_CHECKED_RANGE)


@nox.session(python="3.14")
def review_trailers(session):
    # main, not HEAD: commits on a branch are not reviewed yet.
    session.run("python", "tools/check_review_trailers.py", "8076110..main")
