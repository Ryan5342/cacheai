# Contributing

Thanks for considering it. This is a small, early-stage project, so the
process is intentionally light.

## Setup

```bash
git clone https://github.com/Ryan5342/adaptcache
cd adaptcache
pip install -e ".[dev]"
```

## Running checks locally

```bash
pytest -v                    # full suite (spins up SQLite in-memory; Redis
                              # and SQLAlchemy tests skip themselves if you
                              # don't have `redis`/`sqlalchemy` installed or
                              # a local Redis running on :6379)
pytest --cov=adaptcache --cov-report=term-missing  # CI enforces a 90% floor
mypy adaptcache/ --strict    # the codebase is fully typed and mypy-clean;
                              # PRs should keep it that way
```

Both run automatically in CI on every push and PR
(`.github/workflows/tests.yml`), across Python 3.9-3.12 with a real Redis
service container.

## Guidelines

- **Be honest in docs and commit messages.** If something is a heuristic,
  call it a heuristic. If a benchmark only shows a result under specific
  conditions, say so. This project would rather under-claim than over-sell.
- **Add a test for behavior you add or change.** The existing tests
  (`tests/`, plus `examples/test_fastapi_app.py`) are the reference for
  style: real backends where practical (a real Redis, a real SQLite via
  SQLAlchemy) over mocks.
- **Keep PRs scoped.** Small, focused changes are much easier to review
  than a PR that touches five things at once.

## Reporting issues

Open a GitHub issue with a minimal reproduction if you can. For anything
security-related, please don't open a public issue -- see below.

## Security

If you find a security issue (e.g. something in the Redis or SQLAlchemy
integration that could leak or corrupt data across tenants/processes),
please report it privately rather than as a public issue until there's a
fix.
