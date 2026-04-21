# Merge Scenarios — Detailed Examples

## Scenario 1: Clean Merge (No Conflicts)

PR adds a new feature, no files overlap with local changes.

```bash
# Preferred: squash merge via GitHub (preserves author)
gh pr merge 17 --repo HKUDS/OpenHarness --squash \
  --subject "feat(skills): add diagnose skill (#17)"

# Result: author "Qu Zhi" appears in git log
```

## Scenario 2: CHANGELOG Conflict Only

Almost every PR touches CHANGELOG.md. Handle by excluding it:

```bash
gh pr diff 14 --repo OWNER/REPO | \
  git apply --exclude='CHANGELOG.md'
git add -A

# Manually merge CHANGELOG sections (keep both)
# Then commit with original author
git commit --author="washi4 <washi4@users.noreply.github.com>" \
  -m "feat: add OpenAI-compatible client (#14)"
```

## Scenario 3: Conflicting UI Files

PR #14 modified ui/app.py and ui/backend_host.py which were also changed by PR #13.

```bash
# Apply excluding conflicting files
gh pr diff 14 --repo OWNER/REPO | \
  git apply --exclude='src/ui/app.py' --exclude='src/ui/backend_host.py' --exclude='CHANGELOG.md'

# Manually add the PR's changes to conflicting files
# Read the PR diff to understand what they added, apply by hand
# Commit with author
git commit --author="Author <email>" -m "feat: description (#14)"
```

## Scenario 4: Selective Merge (Skip Features)

PR #16 has auto-compact (already implemented locally) + --resume (wanted) + cron (wanted).

```bash
# Exclude the file containing the unwanted feature
gh pr diff 16 --repo OWNER/REPO | git apply \
  --exclude='src/engine/query_engine.py' \  # skip auto-compact
  --exclude='CHANGELOG.md' \
  --exclude='README.md'

# Commit with explanation
git commit --author="Chao Qin <win4r@users.noreply.github.com>" \
  -m "feat: wire --resume/--continue and cron scheduler (#16)

Cherry-picked from PR #16. Excluded auto-compact (already implemented
with LLM-based approach from reference source)."
```

## Scenario 5: Duplicate PRs (Same Bug, Different Fix)

PR #11 and #13 both fix the double-Enter bug. #13 is smaller and cleaner.

```bash
# Merge #13 (the better fix)
gh pr merge 13 --repo OWNER/REPO --squash

# Close #11 with acknowledgment
gh pr close 11 --repo OWNER/REPO --comment \
  "Fixed via PR #13 (smaller patch for the same bug). \
Thank you for the detailed investigation!"
```

## Scenario 6: PR From a Fork

The contributor pushed to their fork, not a branch on the repo.

```bash
# Fetch via PR ref (works for any PR regardless of source)
git fetch origin pull/14/head:pr-14
git merge pr-14 --no-edit

# If merge conflict:
git mergetool  # or manually resolve
git add -A && git commit --no-edit

git push origin main
```

## Scenario 7: Batch Merge (Multiple PRs)

Merge in dependency order, test after each:

```bash
# 1. Small fixes first (least risk)
gh pr merge 17 --squash  # skill file
gh pr merge 13 --squash  # 1-file bug fix

# 2. Medium changes
gh pr merge 12 --squash  # memory improvement

# 3. Large features last (most conflict risk)
# PR #14 needs manual conflict resolution
git fetch origin pull/14/head:pr-14
git merge pr-14
# resolve CHANGELOG conflict
git push origin main

# 4. Test after all merges
python -m ruff check src/ tests/
python -m pytest tests/ -q
```

## Post-Merge Fix Commit Pattern

When the merged PR introduces a compatibility issue (e.g., API mismatch with a provider):

```bash
# Fix in a SEPARATE commit (don't amend the author's commit)
git commit -m "fix(api): handle Kimi reasoning_content in OpenAI client

Kimi k2.5 requires reasoning_content on assistant tool_call messages.
Fix: capture during streaming, replay when converting back.
Found during post-merge testing with harness-eval."
```

This preserves the original author's commit intact while documenting the fix separately.
