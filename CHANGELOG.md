# Changelog

## 3.12.1 — cleaner update dialog
- Release notes in the update dialog are shown as clean text: headings in bold, bullets with a hanging indent,
  no raw Markdown (`**`, `*`, links), words are no longer split across lines, and long notes scroll.
- First release that can be installed by the in-app updater of 3.12.

## 3.12 — in-app updates + UI polish
**Updates**
- The app checks GitHub once a day (Settings → Updates, can be turned off). When a new version is out it shows
  *Update now*: the installer is downloaded, checked, installed silently, and the app reopens on the new version.
  Your rules, settings and history are kept.
- The download is only accepted from GitHub, must have the exact size and SHA-256 that GitHub reports for the
  release file, and is deleted if anything doesn't match. Releases without that checksum are never auto-installed.
- *Skip this version* hides the reminder for that release. The portable version opens the release page instead.
- CI runs the real update path on Windows: app open → installer with the updater's arguments → app closed,
  updated and reopened, user rules untouched.

**UI/UX**
- Organize toolbar fits at the minimum window size (Search shrinks instead of cutting off *Select all*).
- Long names in tables (Organize, Duplicates, Folder labels, Automation log) show the full text on hover.
- Overview's count column says *Count* again (a duplicate text key showed "Ext."); a test now catches duplicate keys.
- Duplicates: *Keep this one* only appears when there are results.
- Folder labels: rows for folders that exist come first, a summary shows how many exist, *Apply labels* is only
  enabled when at least one folder exists, and *Create N missing folders* creates the rest in one step.
- Page descriptions wrap to the window width on every page; the empty Automation log explains what will appear.
- Per-monitor DPI v2: sharp on every monitor; moving the window to a monitor with another scale re-scales the UI.

## 3.11.1 — installer fix
- **Fixed:** the installer left out the default rules, so a fresh install showed "Rules file not found". Only the
  top-level `rules.yaml` is skipped now (your own rules are still kept on upgrade).
- If you installed 3.11.0: run this installer over it, nothing else to do.
- CI now installs the app silently, runs a self-test on the installed copy (`--self-test`) and uninstalls it.

## 3.11 — robustness (P0 + P1 of the v3.10 audit)
**Data safety**
- **Moves never copy.** A move is a rename on the same drive. If Windows refuses it (file open in another app,
  antivirus scan, download still being written) the item is reported as "in use" and left untouched. Previously
  the fallback copied then deleted, which could leave a duplicate or a half-deleted folder that undo didn't know about.
- **Undo can be retried.** Items that are in use stay in the batch; close them and run undo again.
- **System folders are refused:** drive roots, Windows, Program Files, ProgramData, AppData (and the folders above
  it), `C:\Users` and any user profile folder itself (pick Downloads, Desktop, Documents, …).
- **Folder lock held by the OS:** released automatically if the app crashes or is killed — no stale "Folder is
  busy". Closing the app during a task asks to stop it first; items already moved stay undoable.

**Rules**
- Recursive mode no longer takes apart folders already moved by folder rules (e.g. `_Archive/Folders/...`).
- `dest: "."` keeps files in their own subfolder in recursive mode (previously moved to the root).
- Files inside a folder that is itself being moved are no longer planned separately.
- Download placeholders are skipped (`x.pdf` next to `x.pdf.part`); watch mode also skips empty files.
- OneDrive photos that are not downloaded are no longer opened to read the EXIF date.

**Folder labels**
- Your own `_README.txt` is never overwritten or deleted.
- An existing custom folder icon is kept; an icon set by a rule is reverted to the original on remove.
- `folder_info` paths must be relative and inside the target folder.

**App**
- An error in one UI callback can no longer leave the app stuck on "busy".
- Tab only reaches controls on the visible page (hidden pages could be focused and activated before).
- Duplicates that changed after the check are not moved; results are cleared after organize, undo or watch.
- Changing the target folder stops automation for the old folder.
- Closing during a task stops it first, then still asks about unsaved rule changes.
- A failed move only removes the folders it created itself, never your existing empty folders.
- A folder icon you change in Explorer after labelling is kept.
- 159 tests; each fix has a regression test that fails on 3.10. Fixes were checked by an independent review.

## 3.10 — release readiness (P2 of the re-audit)
- **One process per folder:** a lock in `%APPDATA%` stops the GUI, the CLI and watch mode from moving files in
  the same folder at the same time. A lock left behind by a crash is taken over automatically. Watch mode skips a
  cycle instead of failing; the GUI shows "Folder is busy".
- **rules.yaml edited outside the app:** saving from the GUI now notices the change and asks to
  *Overwrite* or *Reload from file* instead of silently overwriting it.
- **Undo history is pruned:** journals older than 90 days are deleted after each batch (the 20 most recent are
  always kept). Settings → History: 30 / 90 / 180 / 365 days or keep forever.
- **Rules can be switched off** (`enabled: false`, *Enabled* switch in the rule form, "(off)" in the list).
- **Bilingual folder labels:** `folder_info` values can be `{en: ..., id: ...}`; labels are written in the app's
  language and the editor changes only the active language.
- **Defaults:** the "Known projects" folder rule no longer contains personal project names (generic example,
  disabled). `rules.yaml`, README and changelog are in English; Indonesian README in `README.id.md`.
- **Check for updates** (Settings → Updates): reads the latest GitHub release, never installs anything itself.
- **Release engineering:** `version.py` is the single version source; `requirements.lock` pins exact versions for
  builds; GitHub Actions CI (tests on Windows + Linux incl. GUI, .exe build + smoke test, installer, release on
  tag `v*`, optional code signing via secrets); Inno Setup installer (`build_installer.bat`, per-user, no admin).
- **Code:** rule validation, config preparation, file walking and the YAML merge split into small functions
  (max complexity C); the Rules page split into `rules.py`, `rule_editor.py`, `label_editor.py`.
- 132 tests.

## 3.9 — hardening (P0 + P1 of the re-audit)
- **Logging & error handling:** rotating log at `%APPDATA%\FolderOrganizer\logs\app.log` (batches, undo, failures,
  errors). Errors in buttons/menus no longer vanish silently in the .exe: they are logged and shown in an InfoBar
  with an *Open log* button.
- **Already-organized files stay put:** a file already in its destination pattern (e.g. `Notes/2026-09`) is left
  alone even if its modified date changes. Old layouts (e.g. `Documents/2026`) are still migrated.
- **Folder rules with `dest: "."`** really leave the folder in place (previously it was renamed to "X (2)").
- **Categories:** +35 extensions (`.ts` TypeScript, `.raw`, `.csproj`/`.sln`, web templates, `.http`,
  `go.sum`/`go.mod`, …) and matching of extensionless names (`Dockerfile`, `README`, `.gitignore`,
  `.env` → keys & secrets).
- **Fast GUI on big plans:** the table shows at most 2,000 rows (Select all/Clear still apply to every filtered
  item) and search is debounced. 17,000 items: render 2 s → 0.2 s, typing in Search 1 s → < 0.01 s.
- **rules.yaml** is saved to `%APPDATA%` automatically when the app folder is not writable (e.g. `Program Files`).
  Rules and log locations are shown in Settings.
- **Long paths:** failures caused by the Windows 260-character limit are explained instead of a raw error.
- 110 tests (engine, rules_io, categories, end-to-end GUI).

## 3.8 — year-month folders
- New placeholder `{period}` + global setting `date_format` (default `{year}-{month}` → `2026-10`).
  Other choices: `2026`, `2026/10`, `2026/2026-10`, `2026-10-29` (Rules → General → Date folders).
- Every time-based destination in the default `rules.yaml` uses `{period}`: documents, notes, spreadsheets,
  presentations, finance, e-mail, web pages, photos, images, screenshots, video, archives, logs, old folders.
- Reference destinations (CAD, code, fonts, design, identity, keys, installers) intentionally have no date.

## 3.7 — category library
- `categories.yaml`: 44 categories, 632 extensions, no duplicates (documents, media, design, archives, software,
  developer, engineering/CAD/simulation/PCB, security, system). EN/ID labels.
- Rules can use `category: cad_mech` or `category: [photo, image]`, combined with `ext`.
- Custom categories in `rules.yaml → categories:` (add extensions, replace, or new categories).
- Validation: mistyped categories are rejected with a suggestion.
- GUI: Category field + picker in the rule form (with an extension preview), **Categories** tab to browse the library.
- Default `rules.yaml` rewritten (39 file rules, 6 folder rules): identity documents & keys first, whole-word name
  patterns, new installers & archives left alone for 7 days (`dest: "."`), camera photos vs images/graphics,
  CAD/3D/simulation/PCB, school material, extracted tools, projects recognised by name.
- Tests for the default rules against real-world file & folder names (`tests/test_categories.py`).

## 3.6 — standalone .exe
- `build_exe.bat` builds `Folder Organizer.exe` (PyInstaller, one-folder). Task Manager & taskbar show
  **Folder Organizer** with its own icon instead of "Python (default windowed)".
- No Python needed on the target PC; the build folder can be moved or copied to another PC.
- `rules.yaml` lives next to the .exe (copied from your rules at build time, or the defaults on first run).

## 3.5.1
- Removed the app logo at the top of the rail (it is already in the title bar).
- Sharp window & taskbar icon: every size (16–256 px) is drawn on its own pixel grid and Windows uses the
  multi-size `.ico` directly (previously overridden by a scaled-down 64 px PNG, which looked blurry).

## 3.5 — P2 of the audit
**Fully bilingual**
- All engine, rule-validation and CLI messages are EN/ID (default English). The CLI follows the GUI language, or `--lang en|id`.
- Dates in tables follow the language (e.g. `29 Okt 2026`). The `organizer.bat` menu is in English.

**Cancel & progress**
- Scan, preview, duplicate check, moving and rule testing can be cancelled (Cancel button or Esc).
- The progress row shows the stage, items/size processed and estimated time left.
- Cancelling while moving is safe: items already moved are journaled and can be undone.

**Rules & labels**
- Saving rules from the GUI keeps the comments in `rules.yaml` (ruamel.yaml round-trip, atomic write + backup).
- Comments typed in the YAML tab are saved too.
- Folder labels can be removed (GUI: Remove label; CLI: `label --remove`). Only labels created by the app are removed.
- App-created labels no longer in the rules are shown as "not in rules".

**Keyboard accessibility**
- The navigation rail is focusable with Tab, arrow keys move, Enter/Space opens; focus ring and tooltips.
- Shortcuts: Ctrl+1…8 (pages), Ctrl+O (change folder), F5 (rescan/re-preview), Esc (cancel).

**Code**
- `organizer_gui.pyw` (2,240 lines) split into the `gui/` package: `common`, `widgets`, `shell`, one module per page.
- `requirements.txt` & `requirements-dev.txt`; the launchers install from them.
- 69 tests: engine, rules_io and an end-to-end GUI smoke test (optional, `RUN_GUI_TESTS=1`).

## 3.4 — hardening (P0 + P1 of the audit)
**Data safety**
- Batch journals are guaranteed unique (timestamp to the microsecond + exclusive create). Previously two batches in
  the same second overwrote each other, so the first could not be undone.
- Link detection uses the reparse tag: only symlinks/junctions are skipped. OneDrive files & folders (cloud
  reparse points) are processed normally again.
- OneDrive files that are not downloaded are not read during the duplicate check.
- Destinations must be relative and inside the target folder. `..`, absolute paths and destinations through a
  symlink to the outside are rejected.

**Rule validation**
- Mistyped keys are rejected with a suggestion (e.g. `older_than_day` → `older_than_days`), top-level keys too.
- Destination placeholders are validated (`{year}`, `{month}`, `{day}`, `{ext}`, `{EXT}`; no `{ext}` for folders).
- Numbers must be ≥ 0; empty `ext` = every file type.
- The GUI rule editor shows the same errors before saving.

**Behaviour**
- Folder age = the last change inside the folder (recursive), not just the top-level date. Very large folders
  (> 50,000 entries) count as active.
- Default `folder_fallback` is now `null`: folders matching no rule stay in place.
- Journals & plan CSVs are stored in `%APPDATA%\FolderOrganizer\state\` (old journals in `.organizer\` still work).
- The launcher installs Pillow, so photos really are sorted by EXIF date.

**Other**
- 47 automated engine tests (`python -m pytest -q`).
- The engine uses `ConfigError` (CLI-compatible) instead of calling `sys.exit` directly.

## 3.3
- SVG-based navigation rail icons (rendered per theme & DPI).
## 3.2
- Navigation rail, flat table headers, Windows 11 style (tri-state) checkboxes.
## 3.1
- Skip junctions & application-owned folders; detect Controlled folder access.
## 3.0
- Windows 11 style GUI, bilingual EN/ID, visual + YAML rule editor, app & taskbar icon.
