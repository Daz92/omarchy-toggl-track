# PROJECT CONTEXT

**Commit:** 2fbd4ac
**Generated:** 2026-08-28
**Scope:** whole repository (flat — no nested context files earn their place)

Omarchy Shell bar plugin for Toggl Track. A QML panel talks to a one-shot Python
helper, which talks to the Toggl API v9 and to a local ActivityWatch server.

## ARCHITECTURE

```
BarWidget.qml ──Loader──> Panel.qml ──Process(stdin/stdout JSON)──> toggl_api.py
                              │                                          │
                          Model.js                          Toggl API v9 (HTTPS)
                       (pure helpers)                   ActivityWatch (127.0.0.1:5600)
```

`toggl_api.py` handles **exactly one JSON request per process** and exits. It is not
a daemon and holds no state between calls. `Panel.qml` starts a fresh `Process` for
every request. This is the single most load-bearing fact about the codebase — any
feature that seems to need persistence has to put it in Toggl, in the on-disk cache,
or in QML properties.

Request/response envelope:

```
stdin  {"action": "...", ...}
stdout {"ok": true,  "data": {...}}
       {"ok": false, "error": {"message": ..., "status": ..., "retryable": ...}}
```

Actions: `bootstrap` `sync` `start` `stop` `update` `continue` `day_activity`
`create_entry`.

## WHERE TO LOOK

| Path | Owns |
|------|------|
| `Panel.qml` (1055) | Panel chrome, theme wiring, request dispatch, response handling, scope switching; the TIMER/DAY tab bodies were extracted into `ui/*.qml` (down from 1712 lines) |
| `ui/PanelTheme.qml` (17) | The 8 colour-role `QtObject` sourced from `Style.*`/`Color.*` |
| `ui/TimerScope.qml` (313) | Composer + recent-entries body, extracted unchanged in structure from `Panel.qml` |
| `ui/DayScope.qml` (363) | Day header + block rows, extracted unchanged in structure from `Panel.qml` |
| `ui/CalendarScope.qml` (9) | Stub only — no calendar content or scope wiring yet; a later stage supplies both |
| `toggl_api.py` | Auth, HTTP, retries, caching, segmentation, all 8 actions |
| `Model.js` | Pure JS helpers: normalization, formatting, dates, block prep |
| `BarWidget.qml` (87) | Bar button, panel loader, IPC handlers |
| `tests/test_toggl_api.py` + `tests/test_toggl_log.py` | 128 Python tests total |
| `tests/test_model.mjs` | 29 node tests for `Model.js` |
| `setup` | Prompts for the API token, stores it via `secret-tool`, then runs the doctor |
| `toggl_secret.py` | Secret Service work `secret-tool` cannot express: the password-protected keyring, lock state, and why a lookup came back empty |
| `toggl_doctor.py` | Every dependency check behind `setup --check` |
| `manifest.json` | Plugin id, settings schema and defaults |
| `toggl_log.py` | Log levels, redaction, the 24-hour ring buffer |

## COMMANDS

```bash
omarchy plugin validate .
python3 -m unittest discover -s tests -v
python3 -m py_compile toggl_api.py tests/test_toggl_api.py
node tests/test_model.mjs
bash -n setup
./setup --check --offline                      # dependency report, no network
qmlformat Panel.qml >/dev/null                 # real syntax gate
qmllint -I /usr/share/omarchy/shell Panel.qml
./build --check                                # full release gate, no artifact
./install --dev --force                        # relink a development install
```

## ANTI-PATTERNS

**Never pipe `qmllint` and read `$?`.** It writes nothing on failure, so
`qmllint x.qml | tail` returns *tail's* exit status and a broken file looks green.
This produced a false "baseline passes" during development. Check its status
directly, or use `qmlformat`.

**`BarWidget.qml` cannot be gated by either QML tool here.** Both `qmllint` (255)
and `qmlformat` (1) reject `function open(): void`, and Quickshell's `IpcHandler`
requires exactly that typed form. Stripping the return types makes both pass and
breaks IPC, so do not. Verified: strip the three `(): void` on lines 83-85 and
`qmlformat` returns 0. Gate `Panel.qml` with `qmlformat`; review `BarWidget.qml`
by hand.

**Never put `;` after an object member in QML.** `Item { Text {} ; Text {} }` is a
parse error; `Item { Text {} Text {} }` is fine. A refactor that collapsed
components onto single lines introduced 13 of these, and both tools reported the
failure with *zero* output. If a QML file fails to parse with no message, look for
`};` between sibling objects first.

**Never reuse `start` or `continue` to write historical entries.** Both stop the
running timer before creating the new one (`toggl_api.py:_stop_current`). The Day
tab uses `create_entry`, which posts a completed entry and touches nothing else.

**Never retry a mutation blindly.** `TogglClient.request(..., mutation=True)` does
not retry on 5xx or timeout, on purpose — a resent POST creates a duplicate entry.
Reads do retry. Enforced by `test_create_entry_mutation_does_not_retry_on_5xx_or_timeout`
and `test_mutation_does_not_retry`.

**Never write durable state into the metadata cache.** `$XDG_CACHE_HOME/omarchy-toggl-track`
is TTL'd (24h account, 60m workspace) and safe to delete at any moment.

**Never let the token reach a URL, argv, or a log.** Enforced by
`test_auth_creation_does_not_put_token_in_request_url`. It is read from
`secret-tool` at `service=daz.toggl-track account=api-token` on each run.

**Never offer a history range beyond 92 days.** Measured against the live API on
2026-09-03: `GET /me/time_entries` rejects any `start_date` earlier than `today-91`
with HTTP 400 and the body `start_date must not be earlier than <date>`. A 92-day
window is the largest that succeeds. The same floor applies to `since`. The shipped
`historyDays: 365` option made every `sync` fail; `_history_days` now clamps it.

**Never let the log carry a window title at `info`.** `toggl_log.SENSITIVE` drops
those keys unless the level is `debug`. The whole reason classification runs locally
is that titles do not leave the machine, and the log lives in the install directory.

**Never call `logger.write()` directly from the request path.** Use `_log()`, which
swallows every exception. Logging must never turn a working request into a failure.

## CONVENTIONS

**Python: standard library only.** No `requirements.txt`, no `pyproject.toml`, no
third-party imports. Network I/O is `urllib`. Keep it that way — the plugin is
loaded by a shell with no venv.

**QML: multi-line, one property per line.** Run `qmlformat -n -i` after editing.
The one-line style is what caused the parse bug above.

**QML: use `qs.Ui` components, not hand-rolled `Rectangle` + `MouseArea`.**
`Panel.qml` uses Button (6), SearchableDropdown (5), PanelActionButton (5),
ButtonGroup (4), TextField (3), PanelSeparator (3), PanelSectionHeader (2),
Toggle, PanelHero, MultiSelect. They carry the theme's `[controls]` fill/border
states, focus rings and keyboard nav; hand-rolled equivalents carry none.

**Theme values come from `Style.*` and `Color.*`, never literals.** Note
`Style.cornerRadius` resolves to **0** under the current theme — the design is
square-cornered. Use `Style.spacing.{controlHeight,rowGap,panelGap,controlPaddingX}`
rather than raw `Style.space(N)` where a semantic token exists.

**Task ids require a project id.** Both `start` and `continue` reject a task
without one (`test_start_rejects_task_without_project`,
`test_continue_rejects_task_without_project`).

## DAY TAB / ACTIVITYWATCH

`day_activity` reads three ActivityWatch buckets over REST, selected **by bucket
type**, not by name: `currentwindow`, `afkstatus`, `web.tab.current`.

**A row is a block, not an app slot.** `segment_blocks` intersects window spans
with `not-afk`, drops `_IGNORED_APPS` (screensaver, lock), then groups fragments
into stretches separated by a pause longer than `min_block_minutes`. Each block
reports `label` (top topic), `topics` (all, ranked), `apps`, `domain`, `seconds`
(active) and `span_seconds` (wall).

**Do not reintroduce grouping by app, or by runs of one dominant title.** Both
were measured against a real day and both fail:

| Approach | Result on one real 10.9h day |
|---|---|
| Merge same-app fragments, drop < 5 min | 31 rows, **46% of active time silently deleted** |
| Merge same-app, min 1 min | 168 rows |
| Run-length encode per-minute dominant topic | 339 runs, longest **12 min**; no setting yields coherent rows |
| Blocks separated by a real pause | **10 rows, 100% of active time** |

The reason is in the data: the day is ~4,500 focus fragments and 295 distinct
titles, because working on one thing means switching editor → browser → chat
every couple of minutes. Nothing that keys on the app or the title can group
that; only the pauses can.

`min_block_minutes` is the break threshold, not a minimum row length. A block
shorter than it can still exist when a lone fragment sits between two long
pauses. That is honest — the time is real — and it must not be "fixed" by
dropping the block, which is exactly how the old model lost half the day.

Domain enrichment is gated by `_browser_app()`, an allowlist. **A browser missing
from that list silently yields no domains** — this happened with `zen`, the
user's actual browser, for every row. Short names like `zen` match only the
trailing segment of a reverse-DNS app id, so `zenity` does not false-positive.

`_topic()` normalises a window title into a human-recognisable name: it strips
unread counters, a trailing browser name and a trailing Google Docs/Sheets/Slides
suffix. It must not strip an ordinary hyphenated title such as
`nx8-server - Bitbucket`.

Block times are stored as UTC ISO strings; `Model.clockTime()` converts to local
for display. `_day_bounds` computes local-day boundaries, so a "day" is not a
UTC day.

`applied` is set when a block overlaps *any* existing entry. QML separates the
two real cases in `Model.prepareBlocks` by looking up the overlapping entry's
`created_with`: ours (`omarchy-toggl-track/...`) renders as APPLIED, anything
else as CONFLICT.

## GOTCHAS

**In-place block mutation needs `dayRevision`.** Day block fields are mutated in
place so the `Repeater` does not rebuild delegates on every keystroke (which would
steal TextField focus). QML bindings do not observe plain-JS mutation, so the
delegate reads `readonly property int rev: root.dayRevision` and every derived
binding references it via the comma operator, e.g.
`readonly property bool ready: (rev, root.blockReady(modelData))`. Bump
`root.slotChanged()` after any mutation or the UI will not update.

**`Repeater` is not an `Item`, so `visible` does not hide its output.** The
expanded topic breakdown must be gated on the *model*
(`model: blockRow.expanded ? modelData.topics.slice(0, 8) : []`). Setting
`visible` on the Repeater silently does nothing and every collapsed row renders
eight extra lines.

**`applyData()` clobbers `entries`.** It assigns from `data.entries`, which the
`day_activity` response also carries. `handleResponse` therefore returns early for
`day_activity` and `create_entry` *before* reaching `applyData`.

**`request()` drops calls while one is in flight.** It returns early if
`requestPending`. Batch apply works around this with an explicit `applyQueue`
pumped from each `create_entry` response.

**Editing QML requires `omarchy-restart-shell`, not a rescan.** The bar keeps the
plugin's `Loader` alive across `omarchy-shell shell reloadConfig`, so a panel edit
does not appear until quickshell restarts. `omarchy-shell shell rescanPlugins` —
which the README used to recommend — is not in this shell's IPC surface at all
(`qs -p /usr/share/omarchy/shell ipc show`, target `shell`); it prints nothing and
exits 0, so it is indistinguishable from success. Compare `ping`, which returns `ok`.

**Signal handlers must declare their parameters.** `onChanged: { ... value ... }`
relies on injected parameters, which Qt deprecates and logs at runtime. Write
`onChanged: function(value) { ... }`. All nine handlers in `Panel.qml` use the
formal form; check `qs -p /usr/share/omarchy/shell log` after a restart for
`qt.qml.context` warnings when adding more.

**`PanelKeyCatcher` must be told to stand down.** It uses
`Keys.priority: Keys.BeforeItem`, so it sees keys *before* a focused descendant
and consumes `j` `k` `h` `l` `x` as cursor movement. Without `blocked`, those
letters cannot be typed into any description field — this was true from the first
commit and went unnoticed until the Day tab added an editor per row. `Panel.qml`
sets `blocked: root.editorFocused`, computed from
`keyCatcher.Window.activeFocusItem` being a `TextInput`/`TextEdit`, because slot
editors are created dynamically and cannot be named individually.

**`Window` only attaches to an `Item`.** `KeyboardPanel` is not one, so
`panel.Window.activeFocusItem` logs *"Window.window only supports types derived
from Item"* at runtime and silently yields nothing — `qmllint` does not catch it.
Attach to `keyCatcher` instead.

**Page keys need a `FocusScope` wrapper.** `PanelKeyCatcher` holds focus and
ignores PageUp/PageDown, and QML propagates keys *up* the parent chain, never down
into the `Flickable`. The shell's own convention (see
`plugins/dev-gallery/GalleryPanel.qml`) is to wrap the catcher in a `FocusScope`
with `Keys.priority: Keys.AfterItem` so unconsumed page keys bubble to it.

**Tab key is taken.** `onTabRequested` switches Omarchy *panels*, not tabs inside
this one. The TIMER/DAY strip is click-driven.

**ActivityWatch timestamps carry 9 fractional digits.** Fine on Python 3.14;
`datetime.fromisoformat` rejects them on ≤3.12. Events also return **newest
first** — do not assume ascending order.

## Two QML facts that cost a day to learn (stage 4)

**A Repeater delegate's `modelData` is a copy.** A JS-array model reaches the
delegate as a `QVariantList`, so each object is copied when the row is created.
Mutating the source object in place (which `ui/DayScope.qml` must do so the edit
drawer's field keeps focus) is invisible to `modelData` — the row only refreshes
when something rebuilds the Repeater. Read the live object by indexing the
source array (`root.dayVisibleBlocks[index]`) on every revision bump instead.

**A bare comma tap does not re-evaluate.** `readonly property x: (rev, expr)`
looks like it depends on `rev`; the compiler drops the side-effect-free left
operand and captures no dependency. Pass the revision as a function argument
(`dayScope.at(rev, expr)`), which is always evaluated.

Both were proven by instrumenting a delegate with `console.log` and reading
`journalctl --user` — `rev` arrived, `modelData.inspecting` stayed false.

## Local classifier anti-patterns (stage 6)

**Never let a test touch the real history store.** `TogglAPI` opens
`$XDG_DATA_HOME/omarchy-toggl-track/history.json` only when constructed with
no client (production) or an explicit `data_root`; a `FakeClient` test without
`data_root` gets no store at all. Pass a `tempfile.TemporaryDirectory()` as
`data_root` when a test needs one.

**Never raise out of the history store.** `day_activity`, `create_entry` and
`classify` wrap every store call; a broken `history.json` is renamed aside and
the day renders without history rather than not at all (ruling R-AK).

**Never run the Vulkan llama-server without `GGML_VK_DISABLE_COOPMAT=1`.**
On the NVIDIA Vulkan driver measured here, cooperative-matrix kernels made
the model answer every block with index 0 and block 0's topics; nothing else
(flash attention, f16, KV cache type) mattered (ruling R-AM). `setup` writes
the variable into the unit; keep it there.

**Never send a Qwen3 request without `chat_template_kwargs.enable_thinking:
false`.** The model reasons by default; on the CPU build that alone spent the
whole 20 s classify budget before any JSON (rulings R-AG). Keep `max_tokens`,
`temperature: 0` and the `minItems`/`maxItems` pin on `results` too — the
grammar, not the model, guarantees one result per block.

**Never show the classifier anything you are not willing to see copied.** Past
descriptions came back verbatim in 17 of 26 outputs; candidate project names
came back as the description on every block of a live day (ruling R-AO). The
prompt carries the block and nothing else, and the schema has one field.

**Never let the model choose the project.** Counting beats it: the usage prior
scores 81% where the best of eight models scores 65%. `HistoryStore.project_scores`
owns that decision.

**Never batch blocks into one classify call.** Measured 0-5% project accuracy
batched against 19-65% per block, across every model tested.

**Never add negative style rules to the classifier prompt.** "Never list
apps", "do not write 'working on'" and the like made Qwen3-1.7B wordy and
repetitive on the same blocks where the positive assistant prompt gave nine
distinct phrases (ruling R-AN). Describe the job; do not enumerate the sins.

**Never put a worked example in the classify prompt.** Live, the 0.6B model
leaked every example it was shown — verbatim, blended (`<repo> PR #42`), or
by copying its units (R-AJ). An exact-echo filter cannot catch a blend; the
only safe example is none.

**Never treat a `classify` failure as an error.** Connection refused, a
timeout, a non-200, or a malformed body from `llama-server` all return
`{"ok": true, "data": {"results": [], "degraded": True}}` from
`toggl_api.classify()` — never `ok:false`. The Day scope must keep working
with topic labels when the classifier is absent or down; enforced by
`ClassifyTest` in `tests/test_toggl_api.py`.

**Never let `create_entry` gain a path to `classify` or port 8127.**
Enforced by `test_create_entry_source_never_mentions_classify_or_the_llama_port`,
which inspects `create_entry`'s own source rather than trusting a runtime
mock — a shared helper reachable from both functions would pass every
opener-based test while still creating the coupling this guards against.

**The classifier model lives under `$XDG_DATA_HOME`, never
`$XDG_CACHE_HOME`.** Mirrors the existing metadata-cache rule above, in the
opposite direction: the cache is disposable, the 378 MB model is not.

**The pinned model SHA-256 in `setup` (`MODEL_SHA256`) is the LFS sha256
HuggingFace publishes for `Qwen3-0.6B-Q4_K_M.gguf`** — read from
`api/models/unsloth/Qwen3-0.6B-GGUF/tree/main` on 2026-09-04, not computed
from a local download. If the upstream file is ever republished, re-read
it from there; never guess a plausible-looking hash.

## Keyring anti-patterns (publishing)

**Never call `secret-tool lookup` without knowing the collection is unlocked.**
Against a locked collection it does not fail — it blocks forever on a
`gcr-prompter` GUI dialog. The panel spawns the backend with stdin closed on a
ten-second leash, so the wait ends in a timeout with a password dialog stranded
on screen and nothing on it to explain why. `toggl_api._secure_keyring_block()`
asks D-Bus about the lock first and refuses in 134 ms instead.

**`secret-tool clear` matches on attributes across every collection.** Moving a
token between keyrings must clear *before* it stores, never after — clearing
afterwards deletes the copy just made.

**gnome-keyring accepts any password for a collection that is already open.**
An unconditional unlock therefore reports success for a wrong password and
teaches the user the wrong one. `toggl_secret.unlock()` returns early when the
collection is not locked.

**`secret-tool lookup` exits 1 with no output for three different problems** —
absent item, dead keyring daemon, no session bus — so the bare message sent
someone with a broken keyring round a loop through `setup`. The D-Bus diagnosis
in `describe_failure()` runs only on the failure branch, and falls back to the
plain message when PyGObject is missing rather than blaming an optional package
for a missing token.

**Omarchy's login keyring is not encrypted.** `install/user/default-keyring.sh`
creates it without a password and `login/sddm.sh` strips `pam_gnome_keyring`, so
the token is readable in `~/.local/share/keyrings/Default_keyring.keyring`.
Verified by finding a stored token verbatim in that file. Do not describe the
default path as "securely stored"; it is stored the way every other secret on
an Omarchy box is stored, and `setup --secure-keyring` is the way out.
