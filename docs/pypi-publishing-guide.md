# PyPI Publishing Guide

This document describes how to release RKS to PyPI in a repeatable way.

## 1. What "PyPI-ready" Means Here

The repository is considered PyPI-ready when all of the following are true:

- package metadata in [pyproject.toml](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/pyproject.toml) is complete enough for public distribution
- the published README is tailored for PyPI rendering through [README-PYPI.md](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/README-PYPI.md)
- packaged migrations are included in the wheel under [src/rks/migrations](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/src/rks/migrations)
- the package can be built as both `sdist` and `wheel`
- `twine check` passes on the generated distributions

This document does not itself publish to PyPI. It defines the workflow maintainers should follow.

## 2. One-Time Maintainer Setup

1. Create the PyPI project, or confirm that the package name is available.
2. Decide whether the repository will publish through:
   - `PYPI_API_TOKEN` repository secret, or
   - GitHub Trusted Publishing.
3. If using token-based publishing, add `PYPI_API_TOKEN` as a GitHub Actions secret.

The included workflow currently assumes token-based publishing.

## 3. Local Release Validation

Create a clean virtual environment and install release tooling:

```bash
python3 -m venv .release-venv
. .release-venv/bin/activate
python -m pip install -U pip
python -m pip install .[release]
```

Run the test suite:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Build the distributions:

```bash
python -m build --sdist --wheel
```

Validate the built metadata:

```bash
python -m twine check dist/*
```

Expected output:

- a source distribution under `dist/`
- a wheel under `dist/`
- `twine check` succeeds without rendering or metadata errors
- the built wheel can be smoke-tested with `rks --help`, `rks skills list`, `rks init <path>`, `rks init-db`, and `rks doctor`

## 4. Versioning

The package version is currently defined in [src/rks/__init__.py](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/src/rks/__init__.py) and exposed through dynamic metadata in [pyproject.toml](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/pyproject.toml).

Before a release:

1. update `rks.__version__`
2. make sure release notes and docs are in sync
3. rebuild the distributions

## 5. GitHub Actions

The repository includes two workflows:

- [package-check.yml](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/.github/workflows/package-check.yml)
  Runs tests, builds the package, and runs `twine check`.
- [publish-pypi.yml](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/.github/workflows/publish-pypi.yml)
  Publishes to PyPI on version tags like `v0.1.0`, assuming `PYPI_API_TOKEN` is configured.

## 6. Release Procedure

1. Ensure `main` is clean and all desired changes are merged.
2. Bump the version in [src/rks/__init__.py](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/src/rks/__init__.py).
3. Run the local validation steps in Section 3.
4. Commit the version bump and release notes.
5. Create and push a tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

6. Watch the `publish-pypi` workflow in GitHub Actions.
7. After publish completes, verify installation from PyPI:

```bash
python3 -m venv /tmp/rks-smoke
. /tmp/rks-smoke/bin/activate
python -m pip install research-knowledge-substrate
rks --help
```

## 7. Notes

- The runtime still defaults to a local workspace rooted at the current directory or `RKS_ROOT`.
- The package publishes the CLI and local HTTP service, not a hosted SaaS surface.
- If the package name changes before first release, update [pyproject.toml](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/pyproject.toml), [README-PYPI.md](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/README-PYPI.md), and this guide together.
