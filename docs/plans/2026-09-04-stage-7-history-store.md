# Stage 7 — Local History Store Implementation Plan

> **For agentic workers:** executed inline by the session that wrote it, per the
> user's standing instruction ("implement what's left end to end inline").

**Goal:** Learn, locally and automatically, which projects and descriptions the
user has attached to which activity, and use that history before and inside the
0.6B classifier — so guesses come from the user's own past, which a copying
model reproduces faithfully.

**Architecture:** `toggl_api.py` gains a `HistoryStore` (JSON under
`$XDG_DATA_HOME/omarchy-toggl-track/history.json`, human-editable). It learns
from every applied block in `day_activity` — ours or a manual Toggl entry — and
from `create_entry` when the panel sends the block's activity. It suggests, for
every pending block, the closest past records by weighted topic overlap; the
suggestions ride along in the `day_activity` response (`block.history`) and are
quoted into the classify prompt. `Model.js` turns a confident suggestion into
the same `~` guess the classifier uses. A `learn_history` action seeds the store
from the last N days.

**Spec:** `docs/2026-09-04-panel-redesign.md` §7 (guessed rows), §10 (classifier);
rulings R-AH, R-AJ, and R-AK (this stage) in `docs/2026-09-04-stage-2-6-rulings.md`.

## Global Constraints

- Store lives in `$XDG_DATA_HOME/omarchy-toggl-track/history.json`, never the cache dir.
- Nothing from the store is ever applied without a key press; suggestions land as `guessed: true`.
- `day_activity`, `create_entry`, and `classify` never fail because the store is missing, unreadable, or full. A broken file is renamed aside and started fresh.
- Every entry is learned once: `entry_ids` records what has been seen (cap 5,000), so reloads do not inflate counts.
- Record cap 2,000, pruned by `last` seen. Topic/app/domain names stored verbatim; `toggl_log` already redacts them below `debug`.
- Suggestion score is in [0, 1]; `Model.historyGuessFor` takes a guess at ≥ 0.5; the prompt quotes records at ≥ 0.2, at most two per block.

## Tasks

1. `HistoryStore` — load/save, `learn(block, entry)`, `suggest(block, limit)`, `seen(entry_id)`; unit tests with `tempfile`.
2. `TogglAPI(data_root=...)`; `day_activity` learns from applied blocks and attaches `history` to pending blocks; `create_entry` learns when `block` is supplied; tests.
3. `classify` quotes suggestions into the prompt; test asserts the line.
4. `learn_history` action `{workspace_id, days}`; test with two fake days.
5. `Model.historyGuessFor`, `applyHistoryGuesses`; `prepareBlocks` passes `history`; node tests. Panel: history → code heuristic → classifier; `submitBlock` sends `block`.
6. Docs: ruling R-AK, AGENTS.md note, README section; seed the live store for 30 days and verify a `~` guess from history in the day scope.
