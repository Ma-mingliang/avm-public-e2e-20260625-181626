# GitHub PR REST Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Preserve AVM PR creation when `gh` TLS fails by falling back to GitHub REST with the currently logged-in account.

**Architecture:** `GitHubClient.create_pull_request` keeps `gh` as primary. A private REST helper obtains an existing `gh` token without exposing it, posts the equivalent PR payload, and normalizes the response. Errors remain fail-closed.

**Tech Stack:** Python standard library (`urllib.request`), GitHub REST API, pytest mocks.

---

### Task 1: Specify the fallback contract with tests

**Files:**

- Modify: `tests/unit/test_github_client.py`
- Modify: `src/avm/github/client.py`

- [ ] Write a failing test for `gh` failure followed by normalized REST success.
- [ ] Run `E:\Anaconda\python.exe -m pytest tests/unit/test_github_client.py -q` and observe the expected failure.
- [ ] Implement a minimal private REST fallback using `gh auth token` and `urllib.request`.
- [ ] Require an integer PR number and non-empty `html_url`; otherwise raise `GitHubError`.
- [ ] Re-run the focused tests and commit `src/avm/github/client.py` plus its tests.

### Task 2: Verify quality gates and the real v6 lifecycle

**Files:**

- Verify: `src/avm/github/client.py`
- Verify: `tests/unit/test_github_client.py`

- [ ] Run Ruff and the complete GitHub client/PR command tests.
- [ ] Retry v6 `avm create-pr --json`; proceed only after it returns a real PR URL and number.
- [ ] Continue to merge and publish only through AVM state transitions.
