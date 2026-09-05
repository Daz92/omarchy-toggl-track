# Carry-forward findings for stages 3, 4, 5, 6

Produced by adversarial critique of the first plan drafts. The drafts for stages 3, 4 and 5
were rejected for a **sequencing** reason (each was written against the tree as it exists
today, not against what its predecessor stage actually produces), so those plans will be
rewritten. **These findings are version-independent and must survive the rewrite** — they are
about the design guide and about correctness, not about line numbers.

Stage 2's plan was approved and is being executed. Stage 6's plan was approved with findings.


---

## Stage 3 — verdict: BLOCKING — the plan is written against a pre-stage-2 Panel.qml and cannot be executed against what stage 2's own plan actually produces; Task 3 as written would additionally break the panel once stage

### Design-guide fidelity gaps (the acceptance criterion is 'to the dot')

- **[medium — self-flagged, correct pixel/col]**
  - guide: Theme values come from Style.*, Color.* and ui/PanelTheme.qml, never literals (this stage's own stated global constraint) — yet .tk-tag/.tk-bill in the guide's CSS render as var(--warn)=#f9e2af and var(--ok)=#a6e3a1, roles that do not exist in ui/PanelTheme.qml or Color.qml.
  - plan:  Task 4's colorFor map hardcodes "tag": "#f9e2af" and "bill": "#a6e3a1" as literal hex strings directly in QML, correctly matching the guide's rendered colour but violating the stage's own 'never literals' rule. The plan self-flags this as Open Question 2 and leaves it unresolved rather than adding real PanelTheme roles or getting an explicit sign-off before Task 4 is implemented.
- **[low — subtle glow effect, QML has no dir]**
  - guide: .cmd { ...; box-shadow: inset 0 0 0 1px rgba(137,180,250,0.14); } — the command-line box has an inset accent glow in addition to its 1px solid accent border.
  - plan:  Task 4 Step 4's cmdBox Rectangle only sets border.color/border.width; the inset box-shadow is not reproduced and is not mentioned anywhere in the plan (not even as an acknowledged gap).

### Correctness issues

- BLOCKING STRUCTURAL MISMATCH: Stage 3's Depends-on section and Task 4/5/6 all assume ui/TimerScope.qml is an empty stub and that PanelHero + the full composer (descriptionField, projectDropdown, taskDropdown, tagsField MultiSelect, the Billable Toggle, the search SearchableDropdown) still live directly inside Panel.qml at the quoted line numbers/blocks. Reading docs/plans/2026-09-04-stage-2-theme-and-ui-split.md Task 4 directly (the plan's own declared, required predecessor) shows the opposite: stage 2 extracts ALL of that content — PanelHero, the composer, the search button plumbing — verbatim (only re-themed) into a fully-wired ui/TimerScope.qml with `required property var root`/`panelThem
- Task 3's rename pass ('grep -c activeTab Panel.qml' returns 0 is the stated success criterion) only edits Panel.qml. But stage 2's own Task 4 Step 1 shows ui/TimerScope.qml itself gated on `visible: root.activeTab === "timer"` (and stage 2's Task 5 does the same for ui/DayScope.qml with `activeTab === "day"`). Task 3 never touches ui/TimerScope.qml or ui/DayScope.qml (they are not in its Files list), so after Task 3 renames/deletes root.activeTab in Panel.qml, both scope components' top-level `visible: root.activeTab === ...` bindings reference a property that no longer exists. This directly contradicts the stage's own Global Constraint that 'each task must end with a working plugin ... the 
- Task 4's Design Note and Open Question 3 correctly identify that PanelKeyCatcher cannot see Ctrl-modified keys and that the command-line TextInput holding focus makes root.editorFocused true almost permanently — this reasoning is sound — but the plan never verifies that root.editorFocused actually becomes true for this specific TextInput (i.e., that the existing 'blocked: root.editorFocused' wiring, computed from Window.activeFocusItem per the rulings' §5 standing constraint, is keyed off the right item once cmdInput is nested two levels deep inside an Item and a RowLayout inside cmdBox). No step in Task 4 confirms or tests this; it is asserted, not shown.

### Missing requirements

- Open Question 1 (theme access: singleton PanelTheme vs a required `theme` property passed down) is flagged but left unresolved — Task 5's ui/TimerScope.qml is authored against a direct `import "PanelTheme.qml" as PanelThemeType` + local instantiation guess, which is very likely wrong given stage 2's Task 2/4 show Panel.qml owns one `panelTheme: PanelTheme {}` instance and passes it down as a required `panelTheme` property to each extracted ui/*.qml file — the same mechanism confirmed for ui/Time
- No task in this plan actually merges the command-line UI into ui/TimerScope.qml's real post-stage-2 shape (required property var root / panelTheme, field aliases). Task 5 rewrites ui/TimerScope.qml 'entirely' as if starting from a blank stub, discarding stage 2's PanelHero/composer content and its `root`/`panelTheme` required-property contract, rather than integrating the new running-strip/result-rows content alongside (or after deleting) what stage 2 put there. The plan needs an explicit task t

### Placeholder violations

- Task 6 Step 5 elides the SearchableDropdown/MultiSelect/Toggle bodies with '...' and tells the executor to 'use the file you are editing as the source of truth for the exact bounds, not this plan's elision.' This is defensible for a whole-block deletion, but it means the plan does not actually specify what is being deleted — acceptable only if the surrounding anchors (the preceding/following lines it does quote) are still verbatim-present post-stage-2, which the review's main finding shows they 

---

## Stage 4 — verdict: reject

### Design-guide fidelity gaps (the acceptance criterion is 'to the dot')

- **[medium]**
  - guide: .factline b { color: var(--dim15) } — every numeric figure in the facts line (2h41 wall, 16m idle removed, 63 switches, 11m longest run) is bold at the brighter dim15 tier, distinct from the surrounding dim18 label text (.factline default). Only the 'active' figure additionally jumps to full --fg.
  - plan:  Task 3's four non-'active' facts-line Text elements (wall, idle removed, switches, longest run) each set a single flat `color: PanelTheme.textFaint` for the whole string — label and numeric value alike. Only the 'active' Text gets rich-text tiering (PanelTheme.text for the number). The guide's two-tier value/label distinction that the digest itself calls out (R4-11: 'dim15 for values, dim18 for the line's default text colour') is collapsed to one tier for 4 of 5 items.
- **[medium]**
  - guide: .barrow .s { color: var(--dim15) } and .barrow .n { color: var(--dim15) } — both the seconds column and the name column in every TOPICS/APPS/DOMAINS bar row render at the brighter dim15 tier.
  - plan:  Task 3's bar-row delegates (all three sections: TOPICS, APPS, DOMAINS — 6 Text elements total) set `color: PanelTheme.textFaint` for both the seconds Text and the name Text, i.e. the dimmer tier throughout. PanelTheme.textFaint (0.55 alpha) is the role stage 2's own spec (§9.1) and this plan's Global Constraints associate with the guide's dim18, not dim15 — PanelTheme.textMuted (0.72) is the dim15-equivalent role and is never used in these six spots.
- **[low]**
  - guide: .field { height: var(--ctl-h); padding: 0 var(--ctl-px); border: 1px solid var(--border-normal); background: var(--fill-normal); } .field.focused { border-color: var(--accent); background: var(--fill-hover); } — explicit height/padding/border/background values for the edit drawer's two fields, both unfocused and focused.
  - plan:  Task 4's descriptionField/projectTaskField TextFields set none of these — only Layout.fillWidth, text, placeholderText and foreground. The plan's own Step 4 acceptance text just asserts 'qs.Ui TextField default' already matches (28px tall, focus ring) without ever reading the actual TextField.qml source, unlike the diligence the plan explicitly applies to PanelKeyCatcher.qml a few pages later. This is an unverified assumption about matching R4-22's literal values.

### Correctness issues

- Row-click vs keyboard drawer-toggle divergence produces an invalid dual-open state: Task 3 Step 1's row MouseArea (`onClicked: ... blockRow.modelData.inspectOpen = !blockRow.modelData.inspectOpen`) never checks or clears `editOpen`, unlike the keyboard path `toggleInspectCursor()` (Task 5) which explicitly special-cases `block.editOpen` and calls `backToInspect()` instead of a bare toggle. Sequence: click a row (opens inspect) -> click 'e' (openEdit sets editOpen=true, inspectOpen=false, correct) -> click the row body again -> inspectOpen flips true while editOpen stays true. Both `inspectDrawer` (visible: modelData.inspectOpen) and `editDrawer` (visible: modelData.editOpen) now render simul
- The same row-toggle MouseArea is `anchors.fill: parent` against blockRow's outer Rectangle, whose height becomes `inner.implicitHeight` once a drawer is open (Task 3 Step 2's own change from a fixed 22 to that binding) — so the MouseArea covers the open drawer's content area, not just the 22px row strip. None of the TOPICS/APPS/DOMAINS Text/Rectangle bar elements, the timeline legend, or the inter-row gaps have their own MouseArea, so a click anywhere on that whitespace while reading an open inspect drawer falls through to this background handler and toggles the drawer shut (or, combined with the previous finding, opens a second one on top of edit).
- The edit drawer's advertised 'save + apply' Enter binding (Task 5's hint row, sourced from the guide's EDIT hints) has no wiring to actually fire: descriptionField and projectTaskField are plain TextFields with no `onAccepted`/`Keys.onReturnPressed` handler calling `dayScope.applyCursor()`. `PanelKeyCatcher` is `blocked: root.editorFocused` specifically while such a field holds focus (by design, so typed keys reach it) — meaning the catcher's own Enter dispatch never sees the keystroke either while a field is focused. As written, pressing Enter mid-edit does nothing; applying requires defocusing the field first, which is not how the guide or the plan's own hint text describe the interaction,
- Task 5's hint-row RowLayout gates the '^j/^k next block' Text on `inspectOpen || editOpen`, so it renders during EDIT mode too. The guide's EDIT hint row is exactly `EDIT · ↵ save + apply · space back to inspect · esc close` (no Ctrl+J/K entry — that binding is meaningless while a field has focus and the catcher is blocked). The plan's edit-mode hint row therefore shows an extra item the guide doesn't, in an order the guide doesn't produce.
- Minor: the plan's Task 2 Step 2 deletion-range citation 'Panel.qml:1371-1677' is off by roughly 15 lines against the actual current HEAD (the `Model.compactDuration(root.daySummary.totalSeconds)` Text it names as the start marker is actually at line 1386, and the surrounding day-header RowLayout the deletion needs to include starts at 1338). The plan does supply a content-based fallback instruction for this, so it is recoverable, but the number itself is wrong — inconsistent with the otherwise exact-to-the-line accuracy of every other citation in Task 1 and Task 2 (532-534, 537, 568, 579, Model.js:65-94, tests/test_model.mjs:14-19/97, all independently verified correct against the repo).

### Missing requirements

- Spec §7.5's 'Enter: apply the cursor row' has no implementation path for the edit-drawer case where the row's own fields hold focus (see correctness_issues) — the plan documents the desired behaviour in prose ('applyCursor() already reads current field values...so no separate save step is needed') but never adds the accept-handler that would make it true.
- R4-22's field styling (28px height, 10px horizontal padding, border-normal, fill-normal/fill-hover backgrounds, accent focus border) is asserted to already hold via component defaults but is never verified against the actual qs.Ui TextField source, unlike every other cross-repo assumption in this plan which the author explicitly checked (PanelKeyCatcher.qml, Color.qml, Panel.qml line numbers).

### Placeholder violations

- Lines 737, 1393 and 1768 all say a departure/assumption is "flagged in `open_questions`", but the plan document contains no `open_questions` section anywhere (grep confirms zero definitions, only these three references). This is a broken pointer to documentation that doesn't exist — an implementer following the plan cannot go look up what was supposedly flagged there, which matters most for the R4-14 colour-departure and the Ctrl+J/K-detection risk, both real open questions with nowhere they're 

---

## Stage 5 — verdict: reject

### Design-guide fidelity gaps (the acceptance criterion is 'to the dot')

- **[high]**
  - guide: docs/design-guide.html:247-249,676-682 — `.rangechips { margin-left: auto; }`, with `.tot` given a fixed `margin-left:12px` right after it. Net layout: `‹ date ›` on the left, then a filling gap, then the `W·2W·M` chips and the total grouped together at the right edge, 12px apart.
  - plan:  Task 3 Step 2 / Task 4 Step 2: the header RowLayout is `‹, date, ›, chips-Repeater, Item{Layout.fillWidth:true}, total`. The fill item sits AFTER the chips and BEFORE the total, so the chips render bunched next to the date/nav on the left, and only the total is pushed to the far right — the opposite grouping from the guide.
- **[high]**
  - guide: docs/design-guide.html:679-683 — the week mock's `.floor` row, directly under `.dayhead` and always visible in week scope, reads `axis 08:00–19:00 · automatic, from your tracked hours` with a right-aligned `a` hint.
  - plan:  Task 4/5/6 never render this row at all. The only place axis-mode text appears is `axisModeLabel` inside the Task 6 AXIS sub-panel, which stays hidden (`visible: ... && root.axisSettingsOpen`) until the user presses `a`. Week scope's default view is missing this line entirely.
- **[high]**
  - guide: docs/design-guide.html:267-270 and spec §8.1 (digest R5-13): conflict week-grid blocks render `border:1px solid var(--urgent)` PLUS a 45° hatch fill: `background-image: repeating-linear-gradient(45deg, rgba(243,139,168,0.18) 0 3px, transparent 3px 6px)`.
  - plan:  Task 5 Step 1's conflict-block Rectangle sets only `border.color: theme.urgent` and a plain background; no hatch pattern is drawn anywhere in the plan.
- **[high]**
  - guide: docs/design-guide.html:271 and spec §8.1 (digest R5-12): unassigned blocks render `border: 1px dashed rgba(205,214,244,0.35)`, background transparent.
  - plan:  Task 5's unassigned-block Rectangle uses `border.width: 1; border.color: Util.alpha(theme.text, 0.35)` — a solid border, since a plain QML `Rectangle` has no dashed-border property. The plan never flags this as needing a different technique, yet Task 5 Step 2's own manual-verify text still tells the reviewer to 'confirm ... unassigned blocks render dashed', which the given code cannot produce.
- **[high]**
  - guide: spec §8.2 and digest R5-31/R5-32: the fortnight density strip is 'wall-time-ordered' with breaks between blocks hatched, and a conflicting block renders as a distinct solid urgent flex segment.
  - plan:  Task 4 Step 3's `projectSegments()` groups entries by `project_color` in first-seen array order (not wall-clock time), never emits a gap/hatch segment, and never distinguishes a conflicting entry as its own urgent segment. The plan's own comment concedes the degradation ('never fortnight's density-strip gap hatching ... degrades to just the project stack').
- **[high]**
  - guide: docs/design-guide.html — both `.strip i` and `.stack i` are sized with CSS `flex: N` where N is each segment's proportional tracked time (explicit design note: 'The stack encodes proportion, not category. A 4px band split by project time.').
  - plan:  Task 4 Step 3's segment `Rectangle` delegate hardcodes `Layout.preferredWidth: 1` for every segment regardless of `modelData.seconds` (which is computed but never consumed for sizing), so every project segment renders equal-width. This is also a functional correctness defect, not only a fidelity one.
- **[medium]**
  - guide: docs/design-guide.html:891-895 — the month hints row wraps only the glyph in `<b>` (colored `--dim15` per `.hints b`); the rest of the text ('unapplied blocks', 'conflict') stays the default `.hints` color `--dim18`. No warn/urgent color is used anywhere in that row.
  - plan:  Task 4 Step 2 sets `color: theme.warn` on the whole '◌ unapplied blocks' Text and `color: theme.urgent` on the whole '▲ conflict' Text.
- **[medium]**
  - guide: docs/design-guide.html:736-738 — the week mock's own `.hints` row includes a dashed-swatch `◌` + 'unapplied' segment and a `conflict` segment (glyph per R-J = ▲), shown whenever in week scope.
  - plan:  Task 4 Step 2's shared hints row gates the unapplied/conflict legend Texts on `p.calendarRange === "month"` only, so week scope never shows this legend.
- **[low]**
  - guide: docs/design-guide.html:218 — `.hints { gap: 14px; }`.
  - plan:  Task 4 Step 2's hints `RowLayout` uses `spacing: Style.spacing.xxl`, which is 12px in `/usr/share/omarchy/shell/Commons/Style.qml`; `Style.spacing.xxxl` (14px) is the token that actually matches.
- **[low]**
  - guide: docs/design-guide.html:746 — the AXIS mock's mode line literally reads `Fixed, 07:00 – 21:00` (spaced en dash).
  - plan:  Task 6's `axisModeLabel` builds `"Fixed, " + start + ":00–" + end + ":00"` with no spaces around the en dash.

### Correctness issues

- Task 4 Step 3: the project-color stack/strip segments use `Layout.preferredWidth: 1` for every delegate regardless of `modelData.seconds`, so segments always render equal-width in a QtQuick Layouts RowLayout — the code as written cannot produce the proportional stack the design (and spec's own 'encodes proportion' language) requires. This is a functional bug, not a style nit.
- Testability (review point 5): `axisModeLabel` (Task 6 Step 2), `overflowCountLabel` and `monthCountsLabel`/`projectSegments` (Task 4/5) are pure string/array-building functions of already-available data, left inside ui/CalendarScope.qml with zero node-test coverage — despite Task 1 establishing exactly this Model.js+test_model.mjs pattern for functionally identical logic (calendarHeaderLabel, calendarFloorHint, calendarDayTotals, calendarRangeTotal, calendarConflictDates). This repo has no QML test harness, so these four pieces of logic ship completely untested where they could trivially have been Model.js functions.
- The plan's repeated 'ship broken code, then correct it in the next paragraph' authoring style is a real execution-risk pattern: Task 3's calendarVisibleBlocks/calendarAxis, Task 4's monthCountsLabel (illegal duplicate function+property declaration), and Task 5's hour-gutter positioning (dead `* 0` expression, no actual `y:` binding) and `Model.DAY_NAMES_FULL` reference (doesn't exist in Model.js) are all given wrong first, then fixed. An engineer who copies the first fenced block per step and moves to 'Run to verify' would ship a parse error (Task 4's duplicate function+property name is a qmllint/runtime-level error, not necessarily caught by qmlformat) or a silently-wrong layout (Task 3, Ta

### Missing requirements

- R5-13 (spec §8.1 + guide): diagonal hatch fill for conflict blocks in the week grid — entirely absent from Task 5's implementation.
- R5-12 (spec §8.1 + guide): dashed border for unassigned blocks in the week grid — not achievable with the plain Rectangle border the plan uses, and not flagged as needing an alternative technique.
- R5-31/R5-32 (spec §8.2): fortnight density strip must be wall-time-ordered, must hatch breaks between blocks, and must render a conflicting block as a distinct solid urgent segment — none of this is implemented; the plan's `projectSegments()` groups by project color in array order with no gap/conflict handling at all, and this gap is only mentioned as an aside comment, not surfaced as one of the plan's two flagged 'scoping decisions' the way the flag-population gap was.
- The week scope's always-visible 'axis {bounds} · {mode} · a' summary row under the dayhead (guide section 04 week mock) has no home anywhere in Tasks 4-6 — the plan only ever renders axis-mode text inside the AXIS settings sub-panel, which is hidden by default.
- R5-37 (guide `.calcell.today`/`.fncell.today`): the inset box-shadow highlight (`box-shadow: inset 0 0 0 1px rgba(137,180,250,0.28)`) on today's cell is never implemented — only the accent border is drawn (Task 4 Step 3). Minor relative to the above, since an accent border partially approximates the intent, but it is a named, rendered guide value the plan drops silently.

### Placeholder violations

- No literal TBD/'implement later' markers found. However, the plan repeatedly ships a first code block that is admittedly broken and only corrects it in prose immediately after (Task 3: calendarVisibleBlocks/calendarAxis given wrong shape, then rewritten; Task 4: monthCountsLabel declared as both a function and a same-named readonly property — illegal QML — then rewritten; Task 5: the hour-gutter Repeater is given a dead `* 0` height expression with a comment 'positioned via y below' that sets no

---

## Stage 6 — verdict: approve_with_findings


### Correctness issues

- Task 1 Step 1 test `test_classify_string_fields_truncate_at_500_characters` is vacuous: it injects a 600-char string into the fake server's `description` field (which ends up under `record["response"]`), but asserts `len(record["prompt"]) <= 500`. `prompt` is built purely from the short test-fixture block/project data and was never going to exceed 500 chars regardless of whether `toggl_log._clean()`'s truncation works. This test would pass even if 500-char truncation were completely broken, so it does not actually verify R6-24/§10.8's truncation requirement for the response field. The correct assertion would check `record["response"]["results"][0]["description"]`.
- Task 1 Step 3's prose says label 'is validated in Step 5 below, for contract completeness' — but Step 5's actual `classify()` code never reads `block.get("label")` at all (it's silently dropped, not validated). The claim in the plan text is false, even though the resulting behavior (never forwarding label to the prompt) is correct and matches the test `test_classify_prompt_carries_only_normalised_topics_never_raw_labels`.
- `_classifier_install_runtime_from_release` (Task 5 Step 3) downloads a `llama-server` binary from GitHub's latest release and directly `chmod 755`+executes it with zero integrity verification (no checksum/signature), asymmetric with the rigorous SHA-256 pinning required for the model file. Not required by spec/rulings (only the model needs a pinned checksum), so not a spec violation, but a real gap in an otherwise security-conscious plan.

### Missing requirements

- `Model.classifyBlockPayload`'s `domains` array (Task 3) can never contain more than one entry, because `Model.prepareBlocks()` — unmodified by this stage, owned by stage 0/1 — collapses the backend's full `domains: [{name,seconds},...]` list down to a single `block.domain` string before Panel.qml ever sees it. Spec §10.5/R6-7 calls for 'the domain names' (plural) per block in the classify prompt; in practice a block spanning two domains (e.g. github.com and jira internal) will only ever surface 
- Task 5 Step 2's manual verification of `_classifier_download_model` (`bash -c 'source ./setup; _classifier_download_model'`) depends on the unconditional `for tool in secret-tool python3; do command -v ...; done` gate at the top of `setup` succeeding, but — unlike Task 4 Step 4's stub-secret-tool pattern — never puts a stub `secret-tool` on PATH. On a machine that actually lacks `secret-tool` (e.g. a minimal CI container without libsecret-tools), this verification step aborts with an unrelated '
- `classifyBlockPayload`'s hardcoded `.slice(0, 8)` topic cap and `_classify_prompt`'s `"no client"` fallback string (used when `project.client` is empty) are both invented implementation details with no basis in spec/guide/rulings, and no test in either Task 1 or Task 3 exercises either branch (no test supplies a block with >8 topics or a project with an empty client).
