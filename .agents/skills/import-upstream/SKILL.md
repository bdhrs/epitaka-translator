---
name: import-upstream
description: Check the original project this fork came from (dhammanana/epitaka_translator) for new commits, judge each one against this fork, and plan the port. Use when the user types /import-upstream or asks to check upstream, sync with the source repo, or asks what is new upstream.
---

# Import upstream (epitaka translator fork)

This skill is for this repo only. It studies new upstream commits and sets up a kamma thread to port what is worth having. It never edits source in the study step.

## Before you start

1. Read `AGENTS.md` and `kamma/tech.md` in the repo root. They hold the fork rules: which models are used, the no-Roman-letters rule, the DeepSeek model name, the test and type-check commands.
2. Read `UPSTREAM_LOG.md` in this skill folder. It lists the last upstream commit checked and every item already ported or skipped. Do not argue a skipped item again without new numbers.

## Steps

1. Fetch and list what is new. Use `git fetch upstream`, then `git log --oneline <last-checked>..upstream/main`. The last-checked commit is in the log. If there is nothing new, say so and stop. If there is no `upstream` remote, add `https://github.com/dhammanana/epitaka_translator.git`.
2. Read every new commit's diff. Say what the code does, not what the message says. Compare with how the fork changed the same files since the fork point (`git diff <fork-point> HEAD -- <file>`).
3. Mark each change as port, adapt, already covered, or skip. Give one reason each. Check it against the fork rules from `AGENTS.md`.
4. Measure before you propose a big change. Read the run logs in `data/` or the real data to see if the problem exists here. A change that fixes a problem the fork does not have is a skip.
5. Ask the user to decide. Ask in batches, one decision at a time, with the context first. Give a clear recommendation.
6. After the user decides, write a kamma thread (`/kamma:1-plan`, or `/kamma:quick` for a tiny change). Write `spec.md` and `plan.md` before any code.
7. After the work lands, add a dated entry to `UPSTREAM_LOG.md`: the new last-checked commit and each item as ported, adapted or skipped with its reason.

## Rules

- Never merge upstream. Read diffs as specs and rebuild them in the fork. Never run `git merge upstream/main`.
- Run `timeout 60 uv run pytest -q` and the Pyright command from `kamma/tech.md` after any port.
- Do not run `git commit` or `git push` unless the user asks.
- Keep chat replies in plain words, with no file paths or code names. Put those in the thread files.
