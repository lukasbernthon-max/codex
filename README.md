# Focus — Screenshot Study Assistant

A compact, always-on-top Windows study companion built with Python and PySide6. Select an IXL question, review a prominent answer, and learn from a short explanation and verification step. Focus never clicks, types, or submits answers on IXL.

## Download the Windows app

Open [the latest Focus release](https://github.com/lukasbernthon-max/codex/releases/latest)
and download **Focus.exe** under Assets. Double-click it to open the floating
assistant. Python and dependencies are bundled; no installation commands or ZIP
extraction are needed. Enter your own OpenAI API key in the first-launch Settings
window. Drag the title bar to move, resize from the edges, and use **Compact view**,
**Always on top**, and **Opacity** to control the popup. Native minimize and close
buttons are in the title bar.

GitHub's Windows workflow publishes a release only after tests and the packaged
executable startup check pass. Releases are unsigned, so Windows may show a
publisher warning; never disable security protections. Initial startup may take
a moment while the bundled runtime extracts. The Windows app requires 64-bit
Windows 10/11. Model accuracy and individual monitor capture configurations still
need real-world verification.

## Build/install from source (Windows 10/11)

**Automatic installation:** extract the complete project ZIP and double-click
`Install Focus.cmd`. It downloads a signed Python installer, installs the build
dependencies, creates `Focus.exe`, and adds a **Focus** desktop shortcut. You do
not need to type commands or install Python yourself. See `START HERE.txt`.
The automatic installer still needs validation on Windows; this project was
developed and tested with offscreen Qt on Linux. The ZIP is not a prebuilt binary.

For maintainers, `.github/workflows/windows-app.yml` automatically tests, builds,
and publishes a single executable when application changes reach `main`. It can
also be triggered manually. A packaged startup check gates release publication.

### Manual installation

1. Install **Python 3.11** (64-bit) from https://www.python.org/downloads/windows/ with the Python Launcher enabled. Python 3.12+ is also supported using the manual steps below.
2. Extract or clone this project into a writable folder.
3. Double-click `start.bat`. The first launch creates `.venv` and installs dependencies; subsequent launches check dependencies for updates within the supported ranges.
4. Open **Settings**, enter your own OpenAI API key, and save. You need API billing/credits; a ChatGPT subscription does not include API credits. The default model is `gpt-4.1-mini`; Settings accepts another vision model supporting structured Responses output.
5. With the pointer on the monitor containing the question, press **Ctrl + Shift + S**. Drag around the full question, diagrams, and choices. Release to send the selected region to OpenAI. Press **Esc** to cancel.

Manual installation in Command Prompt (choose your installed Python version):

```bat
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

## Controls

- **Capture question** captures the monitor under the pointer. Selection stays within one monitor. Move the question onto one monitor first if it spans displays.
- Drag the native title bar to move; use window borders or the bottom-right grip to resize. Native minimize, maximize, and close controls remain available. Windows 11 supplies rounded outer window corners; the inner cards are rounded on both supported Windows versions.
- Use **Opacity** to adjust transparency (55–100%).
- Choose **Concise** or **Detailed** before capture, or use **Retry** after changing the mode to request a new explanation. Retry makes another billable API request.
- **Copy answer** copies only the answer. Nothing is submitted to IXL.
- **Recent questions** stores up to ten results and screenshot previews during this session. **Clear** removes them and the current screenshot from the interface. Closing discards session history. Clipboard contents are managed separately by Windows.
- While solving, capture/history controls are disabled to prevent mismatched results. The window remains movable and responsive. Close waits for the active request to finish (55-second request timeout, at most one SDK retry).

## Privacy, reliability, and credentials

Only the selected region is sent to OpenAI; the full-monitor frame is temporarily held in memory for region selection. Capture only material you intend to share and avoid personal information. Screenshots and history are not written to disk by this application. OpenAI's API data policies apply to submitted content; this app does not promise zero provider retention.

Keys use `keyring` and Windows Credential Manager, never a source file, `.env`, or plaintext settings file. Preferences (model, verbosity, opacity) use Qt's OS settings store. Clear the key in Settings and save to delete the stored credential. If secure storage fails, solving is blocked rather than storing a plaintext fallback. API exceptions are displayed as sanitized messages.

The vision model is instructed to request a recapture when required details are unclear and to check its calculations. This is a **model-generated check, not an independent mathematical proof or calculator**. Incorrect answers remain possible, especially with ambiguous graphs or complex geometry. Review the explanation and use the tool in accordance with your school's rules.

## Package a Windows executable

Build **on Windows**, using a clean virtual environment and the same architecture as your target machine. PyInstaller does not cross-compile Windows binaries on Linux.

```bat
.venv\Scripts\python -m pip install pyinstaller
.venv\Scripts\python -m PyInstaller --noconfirm --clean --windowed --onedir --name Focus --collect-all keyring --collect-submodules pynput main.py
```

Distribute the entire `dist\Focus` directory; launch `Focus.exe` inside it. For a single executable replace `--onedir` with `--onefile` (slower startup). No API key is bundled. Test the packaged build on a clean Windows account, including credential storage and global hotkeys. Public distribution may require code signing to reduce SmartScreen warnings.

## Tests

```bat
.venv\Scripts\python -m pip install pytest
.venv\Scripts\python -m pytest -q
```

Tests use Qt's offscreen platform and mocked OpenAI responses. They exercise structured output validation, image request construction, failures, history, clipboard, scaled region cropping, cancel, and missing credentials. They do not spend API credits.

Windows acceptance checks: capture using both button and global shortcut; test each monitor at 100%, 150%, and 200% scaling (including a monitor left of the primary); confirm the overlay is absent from screenshots; solve a known equation and graph question; test an unreadable crop; disconnect the network and retry; minimize/restore; restart to verify secure key persistence; repeat with the packaged executable. Live OpenAI behavior requires your own key and account access.

## Troubleshooting

- **Shortcut unavailable/conflicts:** use the capture button or close software using the same shortcut. Elevated applications can block hooks from a non-elevated process.
- **Black/incorrect capture:** protected video, secure desktops, remote sessions, and unusual mixed-DPI arrangements can prevent capture. Test on the normal Windows desktop, on one monitor.
- **Key rejected / quota reached:** verify the key, project permissions, and API billing. Never send your key in a bug report.
- **Model rejected:** choose a vision model available to your account that supports the Responses API and structured output.
- **No network:** the screenshot remains local in memory for Retry. The application needs HTTPS access to `api.openai.com`; installation needs PyPI access.

## Project layout

`ixl_assistant/app.py` contains the UI and background worker; `capture.py` handles region selection; `solver.py` handles typed vision responses; `storage.py` wraps secure credentials. `main.py` is the entry point for Python and PyInstaller.
