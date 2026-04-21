---
name: pr-merge
description: This skill should be used when the user asks to "merge a PR", "review and merge pull requests", "integrate external contributions", "handle PR conflicts", "cherry-pick from a PR", or needs to merge GitHub PRs while maximizing contributor attribution.
version: 0.1.0
---

# PR Merge — Contributor-First Pull Request Integration

Merge external pull requests while maximizing original author attribution. Core principle: **merge first, resolve conflicts after** — never rewrite a contributor's work from scratch.

## Core Principles

1. **Preserve authorship** — use `gh pr merge --squash` for clean PRs. For manual merges, use `--author="Name <email>"`.
2. **Merge first, fix after** — accept the PR's approach even if it differs from local style. Fix conflicts in a separate commit.
3. **Selective merge is OK** — exclude files with `--exclude` when a PR contains features already implemented locally. Document what was excluded.
4. **Never `git apply` + self-commit** — this loses author attribution entirely.

## Workflow

### 1. Triage Open PRs

```bash
gh pr list --repo OWNER/REPO --state open \
  --json number,title,author,additions,deletions,mergeable
```

Classify each PR: merge directly, merge with conflict resolution, selective merge, or close.

### 2. Merge Clean PRs via GitHub

Prefer `gh pr merge` — preserves author automatically:

```bash
gh pr merge NUMBER --repo OWNER/REPO --squash \
  --subject "feat: description (#NUMBER)"
```

### 3. Handle Conflicting PRs Locally

```bash
git fetch origin pull/NUMBER/head:pr-NUMBER
git merge pr-NUMBER --no-edit
# Resolve conflicts keeping both sides where possible
git add -A && git commit --no-edit
```

### 4. Selective Merge (Skip Some Files)

When a PR contains features already implemented locally:

```bash
gh pr diff NUMBER --repo OWNER/REPO | \
  git apply --exclude='path/to/skip.py' --exclude='CHANGELOG.md'
git commit --author="Author Name <author@email>" \
  -m "feat: description (#NUMBER)

Cherry-picked from PR #NUMBER. Excluded: file.py (already implemented)."
```

### 5. Close Duplicate/Superseded PRs

```bash
gh pr close NUMBER --repo OWNER/REPO \
  --comment "Fixed via PR #OTHER. Thank you for the contribution!"
```

### 6. Post-Merge Verification

```bash
python -m ruff check src/ tests/    # lint
python -m pytest tests/ -q          # unit tests
git push origin main                # push
```

Then run `harness-eval` for end-to-end verification on an unfamiliar codebase.

## Attribution Checklist

Before pushing a merged PR:

- [ ] Original author appears in `git log` (via `--author` or GitHub squash merge)
- [ ] Commit message references PR number (`#NUMBER`)
- [ ] If selectively merged, commit body explains exclusions
- [ ] Closed PRs have a comment thanking the contributor
- [ ] Duplicate PRs acknowledge the contributor's investigation

## Common Pitfalls

- `git apply` + self-commit loses author
- Rewriting from scratch instead of merging — merge their code, fix style after
- Force-pushing main after merge — may remove contributor commits
- Forgetting CHANGELOG conflicts — always exclude and handle manually
- Not testing after merge — clean merge doesn't mean working code

## Additional Resources

### Reference Files

- **`references/merge-scenarios.md`** — Detailed examples for each merge scenario (clean, conflicting, selective, duplicate)
