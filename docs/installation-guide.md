# RKS Installation Guide

This document explains how to install RKS and which installation path is recommended for different usage styles.

## 1. Installation Overview

The primary installation path today is a local source install.

This is suitable for:

- local personal use
- development and debugging
- agent-driven operation through Codex, Claude Code, or similar tools

The repository does not currently present itself as a PyPI, Homebrew, or standalone installer distribution, so source installation is the recommended default.

## 2. Requirements

Make sure the machine has:

- Python `>=3.10`
- `python3`
- `pip`
- the ability to create virtual environments

You can check with:

```bash
python3 --version
python3 -m pip --version
```

## 3. Install From Source

### 3.1 Get the code

```bash
git clone <repo-url>
cd research-knowledge-substrate
```

### 3.2 Create a virtual environment

```bash
python3 -m venv .venv
. .venv/bin/activate
```

### 3.3 Install RKS

```bash
python -m pip install -e .
```

This uses an editable install, which fits the current stage of the project:

- the `rks` command becomes available immediately
- repository changes are reflected in the active environment

## 4. Initialize the Workspace

After installation, initialize the local workspace:

```bash
rks config init
rks init-db
rks migrate
```

Inspect the effective configuration:

```bash
rks config show
```

## 5. Verify the Installation

At minimum, run:

```bash
rks --help
rks config show
rks init-db
```

If these commands work, the installation is basically healthy.

You can also try a minimal ingest:

```bash
printf '%s\n' '%PDF-1.4' 'Hello RKS.' > sample.pdf
rks ingest pdf sample.pdf
```

## 6. LLM and Agent Preparation

### 6.1 Using `llm-api` mode

If you want RKS to call a model provider directly, set an API key, for example:

```bash
export RKS_LLM_API_KEY=...
export RKS_LLM_MODEL=gpt-4.1-mini
```

Then you can run:

```bash
rks extract text <paper_id> --mode llm-api
rks extract claims <paper_id> --mode llm-api
rks summarize paper <paper_id> --mode llm-api
```

### 6.2 Using external agent mode

If you are using Codex, Claude Code, or another agent runtime, you usually do not need RKS itself to own provider credentials. Use:

```bash
rks extract text <paper_id> --mode agent
rks extract claims <paper_id> --mode agent
rks summarize paper <paper_id> --mode agent
```

Then import the agent-produced results through the documented `import` flows.

## 7. Recommended Install Shapes

### 7.1 Regular users

Recommended:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

This is the most reliable option today.

### 7.2 Developers

Editable install is also the right default for developers, since code, docs, or tests may change frequently.

### 7.3 Agent-operated environments

If Codex or Claude Code will operate directly inside the repository, also prefer editable install and make sure:

- the virtual environment is activated
- the `rks` command is available in the current shell
- the workspace has write access to the data directory

## 8. Rebuild or Reset

If you want to rebuild the Python environment, the simplest path is usually:

```bash
rm -rf .venv
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

If you only want to clear workspace data, you can remove the local `data/` directory, but that will also remove the local database and artifacts.

## 9. Common Problems

### 9.1 `rks` command not found

Typical reasons:

- the virtual environment is not active
- `pip install -e .` did not complete successfully

Retry:

```bash
. .venv/bin/activate
python -m pip install -e .
```

### 9.2 Python version too old

Upgrade to Python `3.10` or newer.

### 9.3 No database file after initialization

Run:

```bash
rks config show
```

Confirm where `data_dir` points. The database is typically located at:

```text
<data_dir>/rks.sqlite3
```

## 10. Suggested Next Reading

After installation, continue with:

- [user-usage-guide.md](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/docs/user-usage-guide.md)
- [agent-usage-guide.md](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/docs/agent-usage-guide.md)
- [manual-testing-guide.md](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/docs/manual-testing-guide.md)
