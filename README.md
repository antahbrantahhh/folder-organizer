# Folder Organizer (Windows)

Rule-based file organizer: audit → preview → apply → undo. Nothing is ever deleted; duplicates are moved to
`_to_delete\` for you to review. Windows 11 style GUI, bilingual (English default / Bahasa Indonesia).

*Bahasa Indonesia: [README.id.md](README.id.md)*

## Install
**Installer (recommended):** run `FolderOrganizer-Setup-<version>.exe` from the
[Releases](https://github.com/antahbrantahhh/folder-organizer/releases) page. Per-user install, no admin rights,
Start menu entry and uninstaller. Your `rules.yaml` and history are kept on upgrade and uninstall.

**Portable:** extract `FolderOrganizer-<version>-portable.zip` anywhere and run `Folder Organizer.exe`.

> The .exe is not code-signed yet, so Windows SmartScreen may show "Windows protected your PC" on first run:
> click **More info → Run anyway**.

**From source:** install Python 3.11+ from python.org (tick **Add python.exe to PATH**), extract this folder
(e.g. `C:\Tools\folder-organizer\`) and double-click `Folder Organizer GUI.bat`. Dependencies are installed on
first run.

### Build it yourself
1. `build_exe.bat` → `dist\Folder Organizer\Folder Organizer.exe` (about 1–2 minutes, exact versions from
   `requirements.lock`). Task Manager and the taskbar show **Folder Organizer** with its own icon.
2. Optional: `build_installer.bat` → `installer\Output\FolderOrganizer-Setup-<version>.exe`
   (needs [Inno Setup 6](https://jrsoftware.org/isinfo.php), e.g. `winget install JRSoftware.InnoSetup`).

## Using it
| Page | Shortcut | What it does |
|---|---|---|
| Overview | Ctrl+1 | Scan: file count, size, stale files, duplicates, file types, largest files |
| Organize | Ctrl+2 | Preview the plan, pick items, organize |
| Duplicates | Ctrl+3 | Duplicates by content, choose which copy to keep |
| History | Ctrl+4 | Every batch + undo the last one |
| Folder labels | Ctrl+5 | Apply / remove folder descriptions |
| Automation | Ctrl+6 | Organize new files automatically while the app is open |
| Rules | Ctrl+7 | Visual + YAML rule editor |
| Settings | Ctrl+8 | Theme, language, history retention, updates, about |

Other shortcuts: **Ctrl+O** change target folder · **F5** re-run the scan/preview of the current page ·
**Esc** cancel the running task. The navigation rail works with the keyboard: Tab to focus, Up/Down to move,
Enter/Space to open.

Long tasks (scan, preview, duplicate check, moving) show progress, time left and a **Cancel** button. Cancelling
while moving is safe: items already moved are in History and can be undone.

**Terminal menu:** drag the target folder onto `organizer.bat` and choose from the menu.

**CLI:**
```
python organizer.py scan   "C:\Users\you\Downloads"
python organizer.py plan   "C:\Users\you\Downloads"
python organizer.py apply  "C:\Users\you\Downloads"
python organizer.py dedupe "C:\Users\you\Downloads" --apply
python organizer.py undo   "C:\Users\you\Downloads"
python organizer.py watch  "C:\Users\you\Downloads" --interval 60
python organizer.py label  "C:\Users\you\Downloads"            # apply labels
python organizer.py label  "C:\Users\you\Downloads" --remove   # remove labels created by the app
```
Flags: `--recursive`, `--yes`, `--rules other.yaml`, `--lang en|id` (default: same as the GUI).

## Suggested workflow
1. **Scan** to see the problem.
2. Adjust the rules on the **Rules** page.
3. **Preview**, then **Organize**. Not what you wanted? **Undo** in History.
4. **Duplicates**: move to `_to_delete\`, review, then delete by hand.
5. Optional: **Automation** for Downloads.

## Rules (`rules.yaml`)
Rules are checked top to bottom; the first match wins. Conditions: `category`, `ext`, `name_regex`,
`older_than_days`, `newer_than_days`, `min_size_mb`, `max_size_mb`. `enabled: false` switches a rule off.
Destination placeholders: `{period} {year} {month} {day} {ext} {EXT}`.
`dest: "."` = leave in place (used for installers & zips you just downloaded).
`{period}` = date folder following `date_format` (default `{year}-{month}` → `Documents/Notes/2026-10`); change it
in Rules → General → Date folders. The date comes from EXIF for photos, otherwise from the last-modified date.

**Category library** (`categories.yaml`, also Rules → Categories): 44 categories / 667 extensions + 52 file names
(e.g. `Dockerfile`, `README`, `.env`), for example `pdf`, `word`, `spreadsheet`, `photo`, `photo_raw`, `image`,
`video`, `archive`, `installer_windows`, `code`, `data`, `cad_mech`, `model_3d`, `engineering_sim`, `electronics`,
`keys_certs`. Every extension belongs to exactly one category.
```yaml
rules:
  - name: CAD
    category: cad_mech            # or [cad_mech, model_3d]
    dest: "Resources/CAD"
categories:                       # optional
  cad_mech: [scdoc]               # add an extension to a built-in category
  training_certs: {ext: [pdf], en: "Training certificates"}   # new category
```

- **Recursive mode** leaves folders moved by folder rules (e.g. `_Archive/Folders/...`) intact, and `dest: "."`
  keeps a file in its own subfolder.
- **Your projects:** the folder rule *Known projects* is a disabled example. Put your project names in its
  `name_regex` and switch it on.
- **Validation:** mistyped keys (with a suggestion), unknown placeholders, invalid numbers and destinations that
  are absolute or leave the target folder (`..`) are rejected with a clear message, in the GUI and the CLI.
- **Folder age** is the most recent change of any file/subfolder inside it.
- **Comments are kept:** saving from the GUI changes only what you edited; comments and order stay. The previous
  version is backed up to `rules.yaml.bak`.
- **Edited elsewhere?** If `rules.yaml` changed on disk (e.g. in Notepad) while the app had it open, saving asks
  whether to overwrite it or reload the file.
- Default `folder_fallback: null`: folders matching no rule stay in place (safe for Documents).

## Folder labels
A label writes the description to `desktop.ini` (tooltip when hovering in Explorer) and `_README.txt` in that
folder. Descriptions can be plain text or `{en: ..., id: ...}`; the app writes the language it is set to.
**Remove label** removes only what the app created; other `desktop.ini` settings (icon, view) stay. App-created
labels that are no longer in the rules are marked "not in rules" so you can clean them up.

## Safety
- **Moves never copy:** an item is renamed on the same drive or, if Windows refuses (file open, antivirus,
  download in progress), reported as "in use" and left untouched. Undo can be retried for items that were in use.
- **System folders are refused:** drive roots, Windows, Program Files, ProgramData, AppData, `C:\Users` and any
  user profile folder itself. Pick a folder such as Downloads, Desktop or Documents.
- **One process per folder:** the GUI, the CLI and watch mode never move files in the same folder at the same
  time. The lock is held by Windows and released automatically if the app crashes.
- Folder labels never overwrite your own `_README.txt` and keep existing custom folder icons.
- Already-organized files (e.g. in `Notes/2026-09`) are not moved again when scanning subfolders.

## Data locations
- Log: `%APPDATA%\FolderOrganizer\logs\app.log` (rotating, 3 × 1 MB). Unexpected GUI errors show an *Open log* button.
- `rules.yaml`: next to the app (portable). If the app folder is not writable (e.g. `Program Files`) it is
  `%APPDATA%\FolderOrganizer\rules.yaml`. Settings shows the location.
- Undo history: `%APPDATA%\FolderOrganizer\state\<folder>-<hash>\`, not in the target folder, so it is not synced
  by OneDrive. Kept 90 days by default (Settings → History); the 20 most recent batches are always kept. Old
  journals in `.organizer\` (≤ v3.3) still work.

## Skipped automatically
- Hidden/system files, `desktop.ini`, `Thumbs.db`, unfinished downloads (`.crdownload`, `.part`, `.tmp`)
- Folders `.organizer`, `_to_delete`, `.git`, `node_modules`, `$RECYCLE.BIN`
- Symlinks & junctions (e.g. My Music inside Documents) and application-owned folders (Custom Office Templates, Outlook Files, …)
- OneDrive files that are not downloaded are not read during the duplicate check (so no download is triggered)
- Files open in another app (reported as failed, nothing lost)

## Updates
The installed app checks GitHub once a day (turn it off in Settings → Updates) and you can check any time with
**Check for updates**. When a new version is available:
- **Update now** downloads the installer, verifies it, installs it silently and reopens the app. Your rules,
  settings and history are kept.
- The installer is only accepted from GitHub and must match the size and SHA-256 checksum GitHub publishes for
  the release file; otherwise it is deleted and nothing is installed.
- **Skip this version** hides the reminder until the next release. The portable version opens the release page.

> Until the .exe is code-signed, updates are only as trustworthy as the GitHub account that publishes them —
> keep two-factor authentication on for that account.

## Code layout
```
organizer.py          engine + CLI (also used by the GUI)
rules_io.py           read/write rules.yaml keeping comments, detect external edits
categories.yaml       file category library (44 categories)
i18n.py               all EN/ID text + date/duration formatting
updates.py            GitHub release check
version.py            the app version (single source)
organizer_gui.pyw     GUI launcher (--version: smoke test)
gui/common.py         constants, theme, helpers
gui/widgets.py        rail, tooltip, InfoBar, dialog, table
gui/shell.py          window, navigation, shortcuts, task runner (progress/cancel)
gui/pages/*.py        one file per page (rules: rules.py + rule_editor.py + label_editor.py)
build_icons.py        SVG → PNG rail icons + app icon (needs cairosvg)
build_exe.bat         build the .exe (PyInstaller) · folder_organizer.spec · version_info.txt
build_installer.bat   build the installer · installer/folder_organizer.iss
.github/workflows/    CI: tests (Windows + Linux, GUI), .exe + installer build, release on tag
tests/                engine, rules_io, categories, updates, release, GUI smoke tests
```

## Development
```
pip install -r requirements-dev.txt
python -m pytest -q                                   # everything except GUI
set RUN_GUI_TESTS=1 && python -m pytest -q tests      # + GUI smoke tests (opens windows)
```
- Rail icons: edit `assets/icons/*.svg`, then `python build_icons.py`.
- Release: bump `version.py`, `version_info.txt`, `installer/folder_organizer.iss` and `CHANGELOG.md` (a test
  checks they match), push a tag `v3.10.0` → CI builds and publishes the release.
- Code signing: add repository secrets `SIGN_PFX_BASE64` and `SIGN_PFX_PASSWORD`; CI signs the .exe and installer.
- Dependency updates: `pip install -U -r requirements.txt`, run the tests, copy the versions into `requirements.lock`.

## Run at login (optional)
Task Scheduler → Create Basic Task → trigger **At log on** → Action: `pythonw.exe`, arguments
`"C:\Tools\folder-organizer\organizer.py" watch "C:\Users\you\Downloads"`.
