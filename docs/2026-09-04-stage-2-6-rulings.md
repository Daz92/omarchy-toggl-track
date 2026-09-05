# Stage 2–6 rulings — amendments to the panel redesign spec

**Date:** 2026-09-04
**Amends:** [`docs/2026-09-04-panel-redesign.md`](2026-09-04-panel-redesign.md)
**Acceptance reference:** [`docs/design-guide.html`](design-guide.html)

Seven agents extracted the per-stage requirements from the spec and the design guide, and a
reconciliation pass found five interface conflicts and eight places the two documents disagree.
These rulings resolve every one of them. Where this file and the spec disagree, **this file wins**;
it was written later and with the conflicts visible.

The governing rule throughout: **for a rendered value the design guide wins, because the user's
acceptance criterion is "follows the html to the dot". For behaviour and contracts the spec wins.**

---

## 1. Interface conflicts

### R-A · `ui/CalendarScope.qml` is created once, by stage 2, as a stub

Both stage 2 (via spec §5's four-file split) and stage 5 (via its content) claimed to *create* this
file. Stage 2 creates it as a minimal stub that satisfies the `ui/` import and `build`'s
`ui/*.qml` glob. **Stage 5 modifies it.** Stage 2 must not invent calendar content.

### R-B · The day-block cursor is declared in stage 3, implemented in stage 4

Stage 3's `◷ BLOCK` result row must, per spec §6.4, "jump to day scope, cursor on that block" — but
stage 4 is what produces the cursor concept. A consumer must not precede its producer.

**Stage 3 declares `property int dayCursorIndex: -1` on `Panel.qml`** and its BLOCK row sets scope,
date and index. That is all stage 3 does with it. **Stage 4 implements what the cursor means** —
drawer targeting and keyboard movement. One line forward, no retrofit.

### R-C · `Ctrl+J` / `Ctrl+K` dispatch is defined once, in stage 3

Stage 3 binds these to move the result-row cursor; stage 4 binds the same keys to move the day-block
cursor. Both live on the single shared `PanelKeyCatcher`.

**Stage 3 writes the scope-conditioned dispatch in `Panel.qml`** — a switch on `root.scope` routing
to the right handler. **Stage 4 implements `dayScope.moveCursor()` and slots into that switch**,
rather than re-wiring the catcher. Whoever touches the catcher second must not overwrite the first.

### R-D · Two duration formatters, deliberately, because the guide is not self-consistent

The guide renders day rows, the day header and the facts line as always-hour — `0h50`, `2h25`,
`8h05`. It renders command-line CONT rows as a hybrid — `45m` under an hour, `2h25` at or over.
Those are different formats for the same quantity, and the guide contradicts *itself*, not the spec.

"To the dot" means reproducing what the guide shows, so **both formats ship**:

- `Model.compactDuration()` — exists today, hybrid, keeps its current call sites and the CONT rows.
- `Model.clockDuration()` — **new, authored in stage 3**, always `HhMM` zero-padded, used by day
  rows, the day header, the facts line and every calendar total.

Stage 3 authors `clockDuration` even though stage 4 is its first heavy consumer, so that stage 4 and
stage 5 both inherit it rather than each inventing one. Both functions get a comment naming the other
and stating that the split is deliberate.

### R-E · Stage 3 owns the settings `ColumnLayout`

The `WORKSPACE` / `HISTORY` / `IDLE REMINDER` / `LOG DETAIL` / `BREAK` block (`Panel.qml:849-1027`)
is gated on `activeTab`, which stage 3 renames to `scope`. No stage claimed it.

**Stage 3 claims it, keeps it in `Panel.qml`,** and re-gates it on the new three-valued scope. The
existing timer-only and day-only groups keep their behaviour; the `cal` scope shows the calendar's
own controls, which stage 5 supplies. Stage 3 must leave a working panel for `scope === "cal"` even
before stage 5 exists — an empty settings section is acceptable, a broken binding is not.

---

## 2. Guide versus spec

### R-F · The `Qt.darker` baseline is 23, not 21

Both documents say 21. A direct grep says 23, and two more were added by stage 1's settings work.
**23 is the binding baseline. The acceptance test is that `grep -c Qt.darker` across `Panel.qml` and
`ui/*.qml` returns 0** after stage 2. This is a code count, not a rendered value, so neither
document's authority applies — the repository does.

### R-G · Result-row verb strings are required copy

The guide renders `START`, `CONT`, `PROJ`, `BLOCK` as literal all-caps labels. The spec gives only
glyphs and actions. **Guide wins — those exact strings ship.**

### R-H · The running clock is 11px, not the 24px display size

The guide's running strip renders the clock at `--f-body-sm` (11px, weight 500, accent), and its own
`--f-display: 24px` token is defined but never referenced anywhere in the file. This is a deliberate
demotion of today's 24px bold `PanelHero`. **Guide wins.** Stage 3 replaces the hero with the strip.

### R-I · `^j/^k` in timer scope is binding

The guide's timer hint bar shows it; the spec mentions it only for day rows. **The guide fills a
genuine spec gap and is treated as binding** — see R-C for how the two bindings coexist.

### R-J · The conflict glyph is `▲`

The guide shows `▲` in day rows, in the month and fortnight legends, and in prose — three places of
four. The week-scope hint row alone shows `▨`. **`▲` is authoritative; the `▨` is a mockup slip.**

### R-K · The week axis label renders the derived bounds; the geometry is what binds

The guide's axis label reads `08:00–19:00` while its own CSS geometry — 156px of grid at 13px rows —
implies twelve rows, i.e. `08:00–20:00`. The guide disagrees with itself.

**The geometry binds, because it drives `top = (startHour - axisStart) * rowHeight`.** The label is
not a fixed string at all: spec §8.1 derives the axis from the data, so the label renders whatever
the derived bounds are. The mock's `08:00–19:00` was illustrative of one day's data, not a constant.
`rowHeight = round(156 / span)`, floored at 8px, exactly as §8.1 states.

### R-L · Overflow copy is the guide's string, exactly

`▸ 3 entries fall outside 07:00 – 21:00` — leading urgent-coloured glyph, spaced en dash, no trailing
period. The spec's unspaced-with-period variant is superseded.

---

## 3. Coverage gaps

### R-M · The classifier setting gets a UI control (stage 6)

`classifier` (`off` / `local`) is the only new manifest setting with no control. **Stage 6 adds a
`ButtonGroup` mirroring the existing `LOG DETAIL` pattern**, plus the warning line that the local
model reads window titles.

### R-N · Stage 4 must define what a skipped block looks like

Spec §7.5 gives `Backspace` a "skip" action but never says what a skipped block renders as.
**Stage 4 defines its glyph and colour, and states whether a skipped block still counts toward the
day total** — it must, since blocks account for all active time.

### R-O · `BarWidget.qml` must be provably unchanged

`root.elapsedLabel` and `root.barLabel` feed the bar's own compact label, which is separate from the
in-panel running strip that R-H demotes. **Stage 3's acceptance includes an explicit check that the
bar label still renders**, since `BarWidget.qml` cannot be gated by either QML tool.

### R-P · `Style.hoverFill` / `Style.selectedFill` derive from `Color.foreground`, not `Color.popups.text`

Verified in the shell's own `Style.qml:190-191`. A theme that sets `[popups] text` far from
`foreground` will show hover and selection fills that do not match the panel's text colour. This is
an external shell dependency and **not fixable in this repository — it is recorded in stage 2's risk
list**, not treated as a defect to chase.

---

## 4. Sequencing

Confirmed by the reconciliation, with one correction:

```
2 → 3 → 4 → 6
      ↘ 5
```

- **Stage 2** depends only on the merged stage 0/1. First.
- **Stage 3** depends on stage 2's `PanelTheme` and the file split.
- **Stage 4** depends on stage 3's `parseCommand`, `clockDuration`, cursor property and key dispatch.
- **Stage 5** depends firmly on stage 2 and stage 3, and only loosely on stage 4 — it needs the
  `◌`/`▲` glyph convention and `clockDuration`, both of which R-D and R-J pin down in stage 3. It
  **may run before or beside stage 4**.
- **Stage 6** depends on stage 4's block fields and `~` marker. Last.
- **Stage X** work — the `manifest.json` settings schema and the `_http_message` 400-body fix — has
  no dependency on 2–6 and is folded into stage 2 to get it out of the way early.

---

## 5. Standing constraints for every stage

Unchanged from the merged work, repeated because they bind all five plans:

- **No `;` after a QML object member.** A parse error both QML tools report with *zero output*.
- **Signal handlers declare their parameters.** `onChanged: function(value) { … }`.
- **Check `qmlformat`'s exit status directly; never pipe it.**
- **`BarWidget.qml` is hand-reviewed** — both tools reject `function open(): void`, which
  `IpcHandler` requires.
- **A `Repeater` is not an `Item`**, so `visible` does not hide its output. Gate on the model.
- **`PanelKeyCatcher` consumes `j k h l x`** before a focused editor sees them, and must be told to
  stand down via `blocked: root.editorFocused`.
- **`Style.cornerRadius` resolves to 0.** Nothing is rounded.
- **Python: standard library only. No daemon.** One request per process.
- **Never retry a mutation; never reuse `start`/`continue` for historical entries.**
- **Toggl rejects `start_date` earlier than `today − 91`**, and the same floor applies to `since`.
- **There is no QML test harness in this repository.** `qmlformat` proves syntax and
  `omarchy plugin validate` proves the manifest; everything else is verified by restarting the shell
  and looking at it. Every stage's acceptance includes a screenshot check.

---

## 6. Amendment, 2026-09-04 — R-D is replaced by R-D2

R-D said two formatters ship: `Model.compactDuration()` keeping "its current call
sites and the CONT rows", and a new always-hour `Model.clockDuration()`. The first
half is wrong, and it was found while writing stage 3's plan rather than by either
document.

`compactDuration` renders `2h 25m` — hours, a space, minutes, an `m` suffix
(`Model.js:26-33`). **The design guide contains zero spaced `Xh Ym` strings**:
`grep -c "h [0-9]\+m" docs/design-guide.html` returns 0. Every at-or-over-an-hour
duration in the guide is `HhMM` zero-padded — `2h25`, `8h05`, `0h50`, `96h40` — and
every under-an-hour one is bare minutes: `45m`, `50m`, `16m`, `11m`.

So `compactDuration` has **no rendered site anywhere in the guide**, and R-D
assigned it two. Its three live call sites are all guide-rendered surfaces:
`ui/DayScope.qml:72` (day header total), `:181` (block duration) and `:319` (the
inspect app lines, which the guide renders as `1h34`, `0h37`, `0h14` — zero-padded
even under an hour).

### R-D2 · Two formatters, and neither is `compactDuration`

- **`Model.clockDuration(seconds)`** — always `HhMM`, zero-padded on both sides,
  hours uncapped (`0h14`, `2h25`, `96h40`). Used by day rows, the day header, the
  inspect drawer's TOPICS and APPS lists, and every calendar total.
- **`Model.rowDuration(seconds)`** — bare minutes under an hour, `clockDuration`
  at or above it (`45m`, `16m`, `2h25`). Used by the command line's CONT rows and
  by the facts line, which mixes both forms in the guide: `2h25 active`,
  `2h41 wall`, `16m idle removed`, `longest run 11m`.

Both are authored in **stage 3** so stages 4 and 5 inherit them.

**`compactDuration` and its tests are deleted in stage 3**, and its three call
sites move to `clockDuration`. It is not kept as a spare: a function that renders
a format the guide never shows is a trap for stages 4-6, which have no reason to
re-derive this analysis. `formatDuration` (`HH:MM:SS`, the running timer label) is
untouched and unrelated.

Cost if wrong: the guide's own CONT-row rendering is the only evidence that `45m`
rather than `0h45` is wanted under an hour in that one place. If that reading is
wrong, `rowDuration` collapses into `clockDuration` and one call site changes.

---

## 7. Amendment, 2026-09-04 — R-Q, the stop affordance

Found while composing stage 3's merged Task 5+6 dispatch, by tracing what the task
deletes rather than by reading either document.

**Neither the design guide nor the spec provides any way to stop a running timer.**
The guide's running strip (`docs/design-guide.html` §01) is a dot, a clock, a
description and a meta line. Its hint bar lists `↵ act`, `⇥ complete`, `^j/^k move`,
`^d day`, `^l calendar`, `esc close`. Every occurrence of "stop" in the guide and in
the spec refers to something else — `_stop_current` as a side effect of `start`, or
prose like "stops there".

Today the panel stops a timer through the START button, which becomes STOP while one
runs (`ui/TimerScope.qml:63,70` → `Panel.qml:402`'s `stop()`). Stage 3's Task 5
rewrites that file wholesale and deletes the control; Task 6 keeps `stop()` with no
caller. The plan's own open questions note this and leave it. Shipping that as
written gives a time tracker that can start timers and never stop them.

### R-Q · Stop is a keyboard binding, not a control

**Decided by the user**, since it is a knowing deviation from the stated acceptance
criterion ("follows the html to the dot") and the alternatives differed materially:

- `Ctrl+S` stops the running timer, bound on the command-line `TextField`'s own
  `Keys.onPressed` alongside `Ctrl+D`/`Ctrl+L`/`Ctrl+T`/`Ctrl+J`/`Ctrl+K`.
- The timer-scope hint bar gains one entry, `^s stop`, positioned after `^j/^k move`
  and before `^d day`.
- **No visible control anywhere.** The running strip renders exactly what the guide
  shows, in every state.

Rejected: keeping a STOP control in the running strip (a visible deviation from the
guide); a fifth `⏹ STOP` result row (invents a verb alongside START/CONT/PROJ/BLOCK,
which the guide never shows); and shipping with no stop path at all.

**The hint entry appears only while a timer is running.** With nothing running the
hint bar is byte-identical to the guide's, which is what the acceptance criterion
asks for; the entry is only useful when there is something to stop. Cost if wrong:
stopping is less discoverable than a button, and a user who has never seen the hint
must find it while a timer runs.

`Panel.qml`'s `stop()` function is unchanged and gains this as its only caller, so
Task 6's "kept with no UI path" note no longer applies.

---

## 8. Amendment, 2026-09-04 — R-R, the colour-tier mapping is stage 2's table

Found by the stage 3 whole-branch review after I queried a one-tier discrepancy in the
result rows. The discrepancy was real; the cause was larger than the symptom.

**Two plan documents in this repository published contradictory colour tables.**

- `docs/plans/2026-09-04-stage-2-theme-and-ui-split.md:429-438` maps
  `darker(fg, 1.4/1.5)` → `textMuted`, `1.6` → `textFaint`, `1.8` → `textDisabled`.
- `docs/plans/2026-09-04-stage-3-command-line-and-scopes.md:171` mapped `--dim18` →
  `textFaint` and omitted `--dim16` entirely.

So `textFaint` was asked to serve two different guide tiers depending on which plan an
implementer happened to read, and every `textFaint` in stage 3's own snippets followed the
wrong table. **No per-task reviewer could have caught this** without reading a different
stage's plan — which is precisely what a whole-branch review is for.

### R-R · Stage 2's table is authoritative

`--dim15` → `textMuted`, `--dim16` → `textFaint`, `--dim18` → `textDisabled`.

The evidence: `ui/DayScope.qml` already obeys it, using `textFaint` at exactly two sites
(`:166`, `:200`), both the applied-block state, which the guide renders at `--dim16`; every
`--dim18` surface in that file is `textDisabled`. And the arithmetic is near-exact —
`Util.alpha(fg, 0.55)` composited over the panel background gives a 0.616 channel scale
against the guide's `--dim16` at 0.625.

Stage 3's line 171 has been corrected in place, with the contradiction recorded rather than
quietly overwritten.

**This was visible on screen without consulting the guide at all**: in day scope the scope
chips and `ui/DayScope.qml:87`'s count line render simultaneously, and both are `--dim18` in
the guide, but the panel painted them at two different brightnesses.

### What is deliberately NOT done

**`ui/PanelTheme.qml`'s alphas stay at 0.72 / 0.55 / 0.38.** Spec §9.1 fixes them and 23
sites depend on them. Retuning to 0.60/0.55/0.47 would reproduce the guide's hexes more
exactly under the `aether` theme and break the role semantics everywhere else.

The consequence is accepted: the outer two tiers overshoot, turning the guide's 1.485×
meta-to-duration luminance contrast into roughly 2.826×. That is the right direction at
about twice the magnitude — measured against what shipped before this ruling, which was
**1.000×**, meaning the guide's deliberate emphasis was absent rather than merely off by a
step. Directionally-right-but-overstated is the better outcome, and it is what the rest of
the panel already does.

Two standing caveats, recorded so a later stage does not re-litigate them: the guide's hexes
are only what the `aether` theme happens to produce, and become unreachable entirely if a
theme sets a translucent `popups.background-alpha`; and the guide's own defect table calls
the 1.5/1.6/1.8 split "used inconsistently for the same semantic role", so some `--dim18`
selectors in it may be transcribed legacy noise rather than intent. That second caveat does
**not** cover the row's `num` column — CONT rows did not exist in the old panel, so its
`--dim15` is fresh intent, not transcription.

---

## 9. Amendment, 2026-09-04 — R-S, project and task resolution is fuzzy and ranked

Raised by the user: their organisation's project names are too long to display, the naming
is not standardised, and they do not control how project managers enter it. Investigating
surfaced a second, more serious problem they had also hit.

### The grammar cannot express their names at all

`parseCommand` splits on whitespace, so `@` binds a single whitespace-free token. Measured
against the live workspace cache: **25 active projects, of which 20 are multi-word**, median
name length 23, longest 51 (`NW-091 Northwind Venturer Upgrade Testing & Validation`). Only
`PTO`, `Sick`, `Holiday`, `Offshore` and `Overhead` can be typed at all. Tasks are worse —
373 active, median 22, longest 77, nearly all multi-word — so `@project/task` never resolves.

Verified: `@NW-074 Northwind Voyager Projects` tokenises as `@NW-074` plus three loose words,
matches nothing, and lands in `unmatched`. The completion makes it circular: `@Res` ghosts to
`@Research and Development`, Tab inserts it, and the parser then rejects what it just wrote.

**This makes stage 3 a functional regression, not merely incomplete.** The composer stage 3
deleted selected projects through a `SearchableDropdown` that worked with any name. So R-S
blocks stage 3's merge to master.

### R-S · Names are never rewritten; matching is fuzzy and ranked

Chosen by the user over three alternatives (a derived short key, a user-edited alias file,
and a grammar-only fix). Its decisive property: **nothing is renamed, so no derivation can go
stale as naming drifts** — which is the constraint the user actually stated.

- The `@` token stays whitespace-free and is a QUERY, not a name.
- Ranked candidates appear in the result rows; `Enter` on a `▤ PROJ` row binds the project.
  Selection happens through the row list, not through text completion — which is what removes
  the circularity above.
- Full names are never shortened in the data. Display shortening is elision only, as now.

### The scoring function, validated against the live data

A pure `Model` function, ranked descending, ties broken by shorter name. Rules, highest first:
whole-name prefix; any word prefix (earlier words score higher); acronym of all word initials;
acronym of SIGNIFICANT word initials (stopwords `and of the for a to in on up &` dropped);
acronym of a trailing run of words, so a leading job code can be skipped; substring at a word
boundary; substring anywhere; subsequence. Longer names are penalised slightly throughout.

Prototyped and measured on the real 25 projects and 373 tasks:

| query | top hit |
| --- | --- |
| `rd` | Research and Development |
| `nvt` | NW-075 Northwind Voyager Testing |
| `trav` | Travel Day |
| `wild` | NW-092-H370 Wild Harbour |
| `091` | NW-091 Northwind Venturer Upgrade Testing & Validation |
| `gppd` | Growth: Paper & Presentation Development |
| `ph2` | Phase 2 Test Report |
| `zerodip` | ZeroDip Single Circuit Breaker Modifications |
| `psa` | Project Support (Admin & Support) |

The significant-word acronym rule is load-bearing: without it `rd` ranks `Shipyard` first, on
the substring `…ya-rd`. Raw subsequence alone is unusable — it ranks
`Growth: Paper & Presentation Development` above `Travel Day` for `trav`.

### Consequences

- Stage 3's in-flight FIX 3 (bind the project when the project half matches exactly) is not
  wasted: under R-S an exact match is simply the highest-scoring case. It is absorbed, not
  superseded.
- The `@` ghost completion is removed or repurposed — completing to a name containing spaces
  is the defect, so Tab must never insert one.
- `@project/task` becomes: once a project is bound, a `/` fragment ranks that project's tasks.
- The 8-row PROJ cap from the guide becomes the ranked list's cap.

## 9. Amendment, 2026-09-04 — R-T, Tab falls through when there is nothing to complete

Found by the stage 3+3b final review (F7): R-S above makes `acceptCompletion` permanently a
no-op (`completion` is `""` for every `@` token, matched or not), but `Panel.qml` still
accepted `Tab` unconditionally into it. Because `open()` focuses the command line, that made
Omarchy's own cross-panel `Tab` switch unreachable in the panel's default state — a real
regression from master, which never focused an editor and so left `PanelKeyCatcher` (and its
`tabRequested` → `switchPanel`) live.

### R-T · Tab completes when there is something to complete; otherwise it switches panels

`Tab`/`Shift+Tab` on the command-line field now accepts a real completion when
`commandParsed.completion` is non-empty, and otherwise calls `switchPanel` directly (mirroring
`PanelKeyCatcher.tabRequested`'s own direction rule, which cannot fire here since the catcher
stands down whenever a text editor holds focus).

The guide's hint bar keeps `⇥ complete` unchanged (§01, byte-for-byte). Under R-S, no live path
currently produces a non-empty `completion`, so today `Tab` always falls through to the panel
switch — the hint names a capability that is dormant, not one that will never exist, and is
kept for guide fidelity rather than invented as a badge or removed as dead. If a future stage
reintroduces a real completion, this is the one place that needs no further change.

---

## 10. Amendment, 2026-09-04 — R-U and R-V, two stage 4 inheritances from the stage 3 final review

Recorded here so stage 4 does not inherit them as invisible debt.

### R-U · R-C's key dispatch lives on `cmdInput`, not on `PanelKeyCatcher`

R-C says the `Ctrl+J`/`Ctrl+K` scope-conditioned dispatch "lives on the single shared
`PanelKeyCatcher`". It does not, and correctly so: `moveResultCursor` (`Panel.qml`) guards on
`root.scope` and is wired to `cmdInput`'s `Keys.onPressed`, because `open()` focuses the
command line and `PanelKeyCatcher` is `blocked` whenever a text editor holds focus — the
panel's default state. The catcher's `onMoveRequested` is not connected at all.

**Stage 4 must slot `dayScope.moveCursor()` into the switch on `cmdInput`'s
`Keys.onPressed`**, not into `PanelKeyCatcher`. Wiring it to the catcher will never fire.
R-C's intent (define the dispatch once, extend it in stage 4) is unchanged; only the location
was wrong.

### R-V · In day scope the guide puts the command line BELOW the day header

`cmdBox` is one fixed child of `contentColumn`, above all three scope items. That matches
§01 exactly for timer scope. But §02 (`design-guide.html:486-508`) orders day scope as
`.dayhead, .dayhead, .sep, .cmd, .rows, .sep, .hints` — the command line sits below the day
header and its separator. A single fixed position cannot satisfy both sections.

Also from §02, absent today: the `.cmd .txt.ghost` placeholder reading `filter blocks`. The
field is a bare `TextInput` with no `placeholderText`, so this is an overlay `Text` gated on
`commandText === ""` and `scope === "day"`.

**Both are stage 4's.** Stage 3's acceptance is §01 and is met.

---

## 11. Amendments, 2026-09-04 — stage 4 rulings (R-W … R-Z)

### R-W · In-place block mutation needs a live read, not `modelData`, and a real tap

Recorded in `AGENTS.md` too because it is load-bearing for every stage after this
one. The previous `ui/DayScope.qml` never re-rendered a mutation until something
rebuilt its Repeater; two independent causes, both fixed in stage 4.

### R-X · The count line counts a guessed row as READY; Shift+Enter does not

Guide §02 renders two `● … ~` rows under `2 READY` and the hint `⇧↵ apply ready · 2`,
while spec §7.5 says a guess is never written unconfirmed. Rendered value → guide:
`blockSummary.ready` includes guesses and `countLine` shows it. Behaviour → spec:
`blockSummary.applicable` counts only `blockReady()` rows and drives the hint and the
batch apply. Zero categories are omitted from the count line.

### R-Y · Day-scope row keys act only while the command line is empty

The command line holds focus and is also the `filter blocks` field, so `Space`,
`e`, `Enter` and `Backspace` cannot be both row actions and typed characters. Rule:
with the field empty they act on the cursor row; with text present they type.
`Ctrl+J`/`Ctrl+K` and `Shift+Enter` act regardless. Cost: a filter beginning with
`e` needs a leading space or another first character. `Enter` with filter text
present does nothing, rather than starting a timer from a filter string.

### R-Z · Two drawer details the guide leaves open

The edit drawer's `space back to inspect` hint is not offered: inside a text field
Space must type a space. The bar tracks are a third of the row, not half, and bar
fills and timeline ticks take a stable per-name colour — both at the user's
request, after seeing the first render.

---

## 12. Amendments, 2026-09-04 — stage 5 rulings (R-AA … R-AD)

### R-AA · Fortnight strips and month stacks are built from entries, not blocks
Spec 8.2 says "breaks between blocks are hatched". Drawing from blocks would cost
14 or 30 day_activity requests per page; the week grid already costs up to 7. The
strips use the range's Toggl entries, wall-time ordered, in project colour, with
1px gaps between entries. `◌` and `▲` flags still draw wherever block data is
cached (any day the week grid has fetched); nothing is fetched for them.

### R-AB · The axis settings live in the calendar body, toggled by `a`
Spec 8.1 says "edited in the calendar scope's settings section". The guide (§04)
shows the AXIS panel as its own mock with `a axis` in the hint bar. It lives under
the week grid, opened by `a`, week range only. The gear column's CALENDAR SETTINGS
section stays empty (R-E permits that).

### R-AC · Calendar keys follow R-Y
`h j k l w a` act only while the command line is empty; `Enter` opens the cursor
day only while it is empty. Typing filters entries by project, client, task,
description or tag (`filter by project or tag`).

### R-AD · Double-click opens a day; single click moves the cursor
The guide gives Enter and says nothing about the mouse. Single click selects so a
stray click cannot leave the calendar; double click opens.

---

## 13. Amendments, 2026-09-04 — stage 6 rulings (R-AE, R-AF)

### R-AE · The model checksum is the one HuggingFace publishes, not a sentinel
The stage 6 plan shipped `MODEL_SHA256` as all zeros, failing closed until a
maintainer downloaded the file. The hash does not require the download: the tree
API (`api/models/unsloth/Qwen3-0.6B-GGUF/tree/main`) publishes each blob's LFS
sha256 and size. `setup` pins `ac2d97712095a558e31573f62f466a3f9d93990898b0ec79d7c974c1780d524a`
at 396,705,472 bytes, matching spec 10.6's size to the byte. If upstream ever
republishes the file, re-read it from there; never guess.

### R-AF · Distribution package first, offered with sudo, release binary second
Spec 10.6: "the distribution package where available". Arch's `extra/llama-cpp`
ships `llama-server`. `setup` offers `sudo pacman -S --needed llama-cpp`
interactively and only then falls back to the upstream release zip under
`$XDG_DATA_HOME/omarchy-toggl-track/bin`. It never runs sudo unprompted.

## 14. Amendments, 2026-09-04 — first live classifier run (R-AG, R-AH)

### R-AG · The classify request disables Qwen3 thinking, pins output, and shows one example

The first live run of `classify` against the installed `llama-server`
(Qwen3-0.6B Q4_K_M, CPU build, 8 threads) degraded on every call: the model
"thought" for 535+ tokens at ~36 tok/s before emitting a byte of JSON, so the
20 s timeout of §10.5 elapsed every time. The request body therefore carries,
in addition to the JSON-schema `response_format`:

- `chat_template_kwargs: {"enable_thinking": false}` — reasoning buys nothing
  under a schema-constrained answer and costs the day its guesses;
- `max_tokens: 400` (`CLASSIFIER_MAX_TOKENS`) — a runaway becomes a
  truncated answer the parser drops, not a timeout;
- `temperature: 0` — the same day classifies the same way twice;
- `minItems`/`maxItems` on `results` equal to the block count — the grammar
  itself forces one result per block, where the model alone stopped after
  four of six.

The prompt gains one worked example (`CLASSIFIER_EXAMPLE_DESCRIPTION`),
placed after the blocks, nearest the answer. Without it the model answered
every block with a 120-character sentence starting "This work block relates
to". A result whose description equals the example verbatim is a
fabrication and is dropped by `_classify_results`. The instruction stays
under ~250 characters so the `debug` log (500 chars per string) still shows
the first block. Measured after the change: 1,330 prompt tokens, 6/6
results, 8–10 s wall on this CPU — inside the 20 s budget, which stays as
the spec has it.

`classify()` also reads `apps`/`domains` as either bare names or
`{name, seconds}` pairs; `str()` on the pairs had put Python reprs in the
prompt.

**Cost if wrong:** a future model that needs reasoning to pick a project
will do slightly worse; that is recoverable by editing one request field,
whereas a timeout on every call makes the whole stage inert.

### R-AH · A guess that only echoes the label with no project is no guess

`Model.classifyGuessFor` returns null when the result's description equals
the block's own label and no project was chosen. Such a guess shows the row
nothing new, yet would flag it `~`, exclude it from `Shift+Enter`
(`blockReady` excludes guessed blocks), and demand a confirmation for no
information. The live 0.6B model does this on most rows whose topics are a
single repository name. **Cost if wrong:** none visible — the row simply
stays in the state it was in before the classifier answered.

## 15. Amendments, 2026-09-04 — cosmetic pass and classifier findings (R-AI, R-AJ)

### R-AI · Compact chrome: one command row, one-line headers, one-line axis

Requested after the first live day with the classifier on. Three changes,
all reflected in `docs/design-guide.html`:

- The three action buttons (refresh, settings, open web) share the command
  row, to the right of the `.cmd` box, in every scope. The chrome row that
  held them above a separator is gone; `.cmd` is now the first thing in the
  timer scope, below the day header in the day scope, and the settings
  block still opens under the gear.
- The day header is one row: `‹ Fri 4 Sep ›`, `TODAY` when off today, the
  count line right-aligned, the day total on the far right in title size.
  The month header follows the same shape.
- The calendar axis panel is one row: `AXIS`, status text, `STARTS` field,
  `ENDS` field (`fieldWidth 64`, `bodySmall` digits, caption labels), `Reset`.

**Cost if wrong:** none functional; every control keeps its key and handler.

### R-AJ · Project guesses come from the data first, the model second

Eight prompt variants were measured live against Qwen3-0.6B on today's
blocks (system prompt, few-shot, richer app/domain data, projects before or
after blocks, description-only, per-block calls). Every variant copied a
string from the prompt — a window title, the example, or the minutes — and
none matched `nw-084-nven-nx8-deployment` to project NW-084. A 0.6B model
copies; it does not synthesise, and no model under the 500 MB cap does
better.

So `Model.guessProjectFromTopics(block, projects)` assigns a project
deterministically when the label or a window-title topic carries the
project's code token (`NW-084`, `[A-Z]{2,5}-\d{2,4}` matched
case-insensitively; codes resolve in topic order, so the code the block spent
most time on wins) or a distinctive whole word (≥ 6 characters, unique to one
project name, not on the generic-word stop list). App ids and web domains
never take part: "System Settings" must not land on a "RAID Based System
Improvement" project, which it did in the first live pass. It runs on every day load, before and independently of the
classifier, and lands through the same `guessed` path (`~`, confirm with
Space, never auto-applied). A block the heuristic assigned is already a
guess, so `classifyGuessFor` leaves it alone; the classifier answers only
the blocks the data could not place. The request now carries
a system message stating the role and the "under 10 words" rule; measured
effect on the 0.6B model was nil, and it is kept because a larger model
will honour it. The worked example R-AG introduced is withdrawn: live, the
model leaked it into most answers — verbatim, blended (`<repo> PR #42`), or
by copying its units — and an exact-echo filter cannot catch a blend.
Without an example the model copies a topic title, which R-AH discards when
it equals the label. `CLASSIFIER_EXAMPLE_DESCRIPTION` and its filter are
gone.

**Cost if wrong:** a false code match shows as a `~` guess the user must
confirm; nothing is applied without a key press.

## 16. Amendments, 2026-09-04 — stage 7 (R-AK)

### R-AK · A local history store learns the user's own labels and speaks first

The user's decision after the model trial: keep Qwen3-0.6B and make it
useful by giving it the user's own history to copy from. `toggl_api.py`
gains a `HistoryStore` at `$XDG_DATA_HOME/omarchy-toggl-track/history.json`
(human-editable JSON, version 1, 2,000 records, 5,000 remembered entry ids):

- **Learns** from every block already covered by a Toggl entry when a day
  loads — ours or a manual entry made in the Toggl web app alike — and from
  every apply, which now sends the block's topics, apps and domain along
  with `create_entry`. An entry id is learned once, so reloads never
  inflate the counts. A record is one (description, project) pair with the
  topic, app and domain names it has been seen with and their seconds.
- **Suggests**, for every pending block, the closest records scored 0..1:
  75 % the share of the block's topic seconds the record has seen, 15 % app
  overlap, 10 % same domain. Suggestions ride in the `day_activity` response
  as `block.history`, best first.
- **Guesses**: `Model.historyGuessFor` takes the best record at score ≥ 0.5
  as a `~` guess (description, project, task), before the code heuristic
  (R-AJ) and before the classifier, which leaves guessed blocks alone.
- **Prompts**: `classify` quotes up to two records at score ≥ 0.2 per block
  as `Past entries for similar activity: "…" (project N)`. A copying model
  copies the user's own past label — the behaviour that defeated every
  prompt in R-AJ becomes the feature.
- **Seeds**: `learn_history {workspace_id, days}` replays the last N days
  (≤ 92) through `day_activity`; days ActivityWatch or Toggl cannot answer
  are skipped. Run once after install: `setup` does not call it (it needs
  the token and ActivityWatch both live), the README shows the one-liner.
- **Never fails an action**: a missing, unreadable or corrupt store is
  renamed aside and started fresh; every store call inside `day_activity`,
  `create_entry` and `classify` is guarded.

The store is empty on day one and the user keeps entering manually for a
few weeks; each manual entry teaches it. **Cost if wrong:** a stale label
surfaces as a `~` guess the user must confirm; nothing is applied without a
key press, and the JSON can be edited or deleted by hand.

### R-AL · Single-day Toggl fetches ask for D..D+1

Found while seeding the history store: `learn_history` replayed 30 days and
learned nothing, because `/me/time_entries?start_date=D&end_date=D` returns
nothing — Toggl's `end_date` is exclusive (measured live: 0 entries for
`2026-08-31..2026-08-31`, 6 for `2026-08-31..2026-09-01`). Two callers were
affected since stage 4: `day_activity` when the panel does not supply the
day's entries (the CLI, `learn_history`), and `create_entry`'s overlap guard,
which therefore never saw the day it was guarding. Both now go through
`_next_day`. The panel itself was unaffected because it supplies entries it
loaded with an inclusive range. **Cost if wrong:** none; a wider window can
only surface entries that are really there.

### R-AM · Two classifier profiles: Qwen3-1.7B on Vulkan where a GPU exists, Qwen3-0.6B on CPU otherwise

The user's ruling after two measured trials. Every model under 1 GB with a
llama.cpp build was run against today's blocks with the production request
(LFM2-700M, LFM2-1.2B, Gemma 3 1B, Llama 3.2 1B, Qwen3-0.6B): none composed
a description — they copied a title, answered category words or raw
seconds, or ran past the token cap. Qwen3-1.7B Q4_K_M (1,107,409,472 bytes,
LFS sha256 `b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897`)
did compose ("FreeRDP connection and report viewing"), at 17–27 s on CPU
and 4–5 s on the RTX 500 Ada via Vulkan — but only with
`GGML_VK_DISABLE_COOPMAT=1`: with cooperative-matrix kernels on, this
driver returned garbage (every result `index 0`, block 0's topics copied);
flash attention, f16 and an f32 KV cache changed nothing.

So the spec's 500 MB cap (§10.6) becomes a per-profile rule:

- **gpu** — chosen when a Vulkan ICD and `libvulkan.so.1` are present
  (override with `TOGGL_CLASSIFIER_PROFILE=gpu|cpu`). `setup` installs the
  upstream `ubuntu-vulkan-x64` release tarball of the pinned tag (`b10816`,
  the same llama.cpp mise resolved) under
  `$XDG_DATA_HOME/omarchy-toggl-track/bin/vulkan/`, verified by size, clean
  extraction and `--version` (upstream publishes no tarball checksum), and
  Qwen3-1.7B verified by its sha256. The unit runs it with
  `--n-gpu-layers 99`, `Environment=GGML_VK_DISABLE_COOPMAT=1` and
  `GGML_VK_DISABLE_COOPMAT2=1`. If the tarball cannot be fetched or does not
  run, setup falls back to the cpu profile.
- **cpu** — unchanged: Qwen3-0.6B, runtime from mise, the distribution
  package or the upstream CPU release.

Both serve the model under one alias, `toggl-classifier`, so the client
never knows which; `CLASSIFIER_MAX_TOKENS` rises to 800 (≈40 tokens a block,
12 blocks fit; well inside 20 s at the GPU's 72 tok/s). `setup --classifier`
runs the stage unattended for scripted installs. **Cost if wrong:** a GPU
whose Vulkan driver misbehaves in some new way shows as degraded classify
results — never wrong applied entries — and `TOGGL_CLASSIFIER_PROFILE=cpu`
is the one-line escape.

**Addendum (first live install).** Under the systemd user session the
Vulkan loader listed the Intel Arc iGPU as `Vulkan0` and the RTX as
`Vulkan1`; llama-server ran the model on the iGPU at 10 tok/s and every
classify degraded. The interactive trial had been fast only because the
shell exported `__NV_PRIME_RENDER_OFFLOAD=1`. `setup` now writes that
variable into the unit and, when `llama-server --list-devices` shows more
than one device, pins `--device` to the first discrete one (NVIDIA, Radeon,
AMD, Arc A/B) — chosen under the same environment the unit runs with. On
the RTX: 57 tok/s, nine blocks in 10.9 s with hints, well under budget.

Second finding: quoting strong history hits to the model made it copy them
onto every block. Strong hits (score ≥ 0.5) never needed the model — they
become guesses in `Model.js` — so `classifyBlockPayload` now omits guessed
blocks entirely, and the remaining weak hits are phrased as a project hint
("still describe this block's own work"). Fewer blocks, faster answers,
and the model's own phrasing survives.

### R-AN · The classifier is an assistant, not a labeller

The user's direction after the GPU install: let the 1.7B synthesise, drop
the hard constraints, aim for unique descriptions. Thirteen live runs on two
real days (`2026-09-04`, nine blocks; `2026-09-02`, seven) settled it:

| Variant | Result |
|---|---|
| production prompt ("under 10 words, from topic names"), grammar, T=0 | copies a window title per block |
| free assistant prompt, rich input, grammar, T=0 | **9/9 and 7/7 distinct, concrete phrases** ("Analyzing telemetry data with Meridian", "Working on Proxmox VM and system configuration"), 10 s |
| same, T=0.7 / T=1.0 | similar text, project choice randomised, duplicates at 1.0 |
| same, free-form lines instead of the grammar | regressed to "Debugging: <title>" |
| same + "name the work, never list apps or sites" | wordy and repetitive: five distinct of nine, "Working on a single task related to Daq Decisions…" ×5 |
| same, T=0.4 | invented "marine platforms" on every block |
| thinking on | 2,123 tokens, 44 s, nothing parseable |

So: the system prompt describes the assistant's job in positive terms
(`CLASSIFIER_SYSTEM_PROMPT`), the JSON grammar stays (it improves the
phrasing, not just the parsing), temperature stays 0, thinking stays off,
and the input is rich — the top twelve window titles, every app and site
with minutes, the block's start time (`Model.classifyBlockPayload`). The
model's project choice is weak (it attached "Holiday" to a weekly report and
"Executive Tasks" to diagram work), so `Model.classifyGuessFor` keeps a
model-chosen project only when a word of the project's name, code or client
appears in the block's own words; otherwise the description lands and the
project stays unassigned. **Cost if wrong:** a livelier but occasionally
off description on a `~` row the user confirms or edits — never an applied
entry.

## 17. Amendments, 2026-09-05 — stage 8 (R-AO, R-AP)

### R-AO · Counting and geometry pick the project; the model only writes prose

Measured on 26 labelled blocks (every activity block a real Toggl entry
covers), leave-one-block-out, eight chat models across six vendors and two
embedding models:

| method | project accuracy |
|---|---|
| most-used project, no model at all | **81%** |
| usage prior blended with embedding centroids | **81%** (pure centroids 77%) |
| granite-4.0-1b, one call per block, no anchors | 65% |
| qwen3-4b 50%, qwen3-1.7b 38%, llama-3.2-3b 27%, phi-4-mini 23%, smollm3 19% | |
| gemma-3-4b, LFM2-2.6b | 4% |
| **any model, all blocks batched into one call** | **0–5%** |

Three findings, each acted on:

- **Request shape dominates.** One call per block beat the batched call by
  roughly nine times for every model. The batched shape is retired.
- **No model beats counting.** So `HistoryStore.project_scores` decides the
  project: `(1 - PROJECT_CENTROID_WEIGHT)` of the usage prior plus
  `PROJECT_CENTROID_WEIGHT` of cosine similarity against a per-project
  centroid, clamped at zero. The weight sweep held 81% from 0.0 to 0.7 and
  fell to 77% at 1.0, so 0.5 keeps today's accuracy while letting geometry
  grow into it. Centroids are running means folded in on every apply and
  every learned day; `learn_history {"rebuild": true}` backfills a store that
  predates them.
- **Everything shown to the model gets copied.** Quoting the user's past
  descriptions made models emit them verbatim (17 of 26 Granite outputs) and
  cost 27 points of project accuracy. Showing candidate project names made
  Granite write `"Research and Development (Northwind Internal)"` as the
  description of every block of a live day. So the model is shown the block
  and nothing else, and its schema has one field: `description`.

The chat model becomes **granite-4.0-1b** (901 MB, the best of the eight and
smaller than the Qwen3-1.7B it replaces) and the embedder **bge-small-en-v1.5**
(35 MB, CPU-only, its own `llama-server` on port 8128 — one process per model
is the documented answer). `setup` installs both against their published
checksums; the profile now chooses only the runtime.

**Cost if wrong:** the project falls back to the usage prior, which is what
the trivial baseline already scored.

### R-AP · Every apply is a training signal, and the harness is part of the product

The user corrects what the panel proposes, so the corrections are the label
stream. Three pieces:

- **Candidates, not a single guess.** `Model.descriptionCandidates` offers the
  model's phrasing, the user's own wording for similar activity, then the
  block's own window title — which out-measured every unaided model at
  F1 0.29 against 0.05–0.24. `Tab` on the cursor row walks them.
- **The correction log.** `create_entry` carries `suggested` (what was on
  screen and where it came from); `HistoryStore.record_correction` stores it
  against what was applied, and `correction_stats()` reports how often each
  source survived contact with the user.
- **`evaluate`.** A backend action that replays labelled blocks leave-one-out
  and scores every layer, so a change is judged by numbers rather than by how
  a screenshot looked. It reproduces the scratch harness exactly (81% prior,
  0.29 window-title F1). `with_model: true` includes the language model at one
  request per block.

**Cost if wrong:** the log is append-only and capped; nothing reads it back
into a decision automatically yet — it exists so the next ruling has evidence.

### R-AQ · One keyboard map, rendered everywhere

`Model.helpSections(scope)` is the single source of the key map: the help
overlay renders it and the README's Controls section is generated from it, so a
key cannot exist in one and be missing from the other. Reached with `^?`, a
bare `?` on an empty command line, or the `?` button in the header.

Gaps the review found, now closed. Arrows work in every scope: `↑`/`↓` move the
cursor whatever is typed, since a single-line input has no use for them, while
`←`/`→` page to the previous or next day or calendar period but only on an empty
command line, because otherwise they must move the caret. The day scope gains
`h`/`l` for the day either side and `t` for today; the calendar gains `t`. The
three header buttons gained keys — `^r` reload, `^,` settings, `^o` Toggl on the
web — having been mouse-only, and they now sit in their own row at 2 px spacing
because they are one cluster, not four controls spread across the header.

Two behaviours the overlay exposed. Escape is layered: the first press dismisses
the overlay, only the next closes the panel. And `open()` resets the scope to
timer, because the panel object outlives a close, so whatever scope it was left
in used to greet the next open.

**Cost if wrong:** a key that shadows typing. The empty-command-line rule is
what prevents that.
