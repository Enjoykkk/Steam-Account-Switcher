# Steam Account Switcher

[🇷🇺 Русский](README.md) | 🇬🇧 English

A local Windows utility for quickly switching between Steam accounts. The program
automatically fills in login/password in the browser, retrieves the Steam Guard code
(from a `.maFile` or via NebulaAuth), and logs you into Steam. Each account opens
in its own Chrome profile so sessions never conflict.

---

## Features

- **tkinter GUI** — account list, double-click to login.
- **Two 2FA code sources:**
  - `mafile` — the program generates a Steam Guard code from the `shared_secret`
    inside the `.maFile` (same TOTP algorithm used by NebulaAuth/SDA).
  - `nebula` — the program automatically finds the NebulaAuth window via Windows
    UI Automation, clicks the correct account in the list, clicks the code —
    the code is copied to clipboard and entered into the Steam form.
- **Isolated Chrome profiles** — each account gets its own `chrome_profiles/<name>`
  folder so Steam sessions don't conflict.
- **Auto-click "Enter a code instead"** — if Steam shows the mobile app confirmation
  screen, the program clicks the link automatically (via React-compatible mouse event
  emulation).
- **Graceful close** — if you close the Chrome window manually the program doesn't
  crash; it silently updates the status bar.
- **Desktop shortcut** — launches the GUI without a console window via `pythonw.exe`.

---

## Project Structure

```
proj1/
├── main.py                # GUI (entry point)
├── mafile.py              # .maFile parsing + TOTP generation
├── nebula.py              # NebulaAuth launch, auto-click, clipboard read
├── steam_browser.py       # Chrome automation via Selenium
├── debug_enter_code.py    # Debug script for Steam UI issues
├── create_shortcut.ps1    # Creates "Steam Switcher" shortcut on the Desktop
├── requirements.txt       # Python dependencies
├── accounts.example.json  # Example config
├── accounts.json          # Real config (auto-created on first run)
├── icon.ico               # Shortcut icon
├── mafiles/               # Place your .maFile files here
└── chrome_profiles/       # Auto-created; one Chrome profile per account
```

---

## Requirements

- **Python 3.10+** (tested on 3.14).
- **Google Chrome** (any recent version; Selenium Manager downloads a compatible
  chromedriver automatically).
- **Windows 10/11** — `pywinauto` for NebulaAuth integration is Windows-only.
- **NebulaAuth** (optional) — only needed if you use `guard_source: nebula`.

> **NebulaAuth** is a third-party application by achies.
> This project does not include or distribute NebulaAuth — it only automates
> interaction with it via the Windows UI Automation API and the clipboard.

---

## Installation

1. **Place the project** in any folder (e.g. `E:\proj1\`).
2. **Install dependencies:**
   ```powershell
   pip install -r requirements.txt
   ```
3. **Create a Desktop shortcut** (optional):
   ```powershell
   powershell -ExecutionPolicy Bypass -File E:\proj1\create_shortcut.ps1
   ```

---

## First Run

1. Run `python main.py` (or use the shortcut).
2. On first start an empty `accounts.json` is created.
3. Click **Settings** → set the path to `NebulaAuth.exe` if you plan to use nebula mode.
4. Click **Add** → fill in the fields:
   - **Name** — displayed in the list (any label you like).
   - **Steam login** — your Steam account name.
   - **Password** — your Steam password.
   - **Path to .maFile** — use the `...` button to browse. Required for `mafile` mode.
   - **2FA source** — `mafile` or `nebula`.
   - **Name in NebulaAuth** — only for `nebula` mode, if the name shown in NebulaAuth
     differs from your Steam login. Leave blank otherwise.
5. Double-click an account in the list to log in.

---

## `accounts.json` Format

```json
{
  "accounts": [
    {
      "label": "Main",
      "login": "my_steam_login",
      "password": "my_password",
      "mafile": "mafiles/main.maFile",
      "guard_source": "mafile",
      "nebula_account_name": null
    },
    {
      "label": "Trade",
      "login": "trader_login",
      "password": "trader_password",
      "mafile": null,
      "guard_source": "nebula",
      "nebula_account_name": null
    }
  ],
  "settings": {
    "chrome_profiles_dir": "chrome_profiles",
    "nebula_auth_path": "C:\\Program Files\\NebulaAuth\\NebulaAuth.exe"
  }
}
```

### Account fields

| Field | Type | Description |
| --- | --- | --- |
| `label` | string | Display name in the program's list |
| `login` | string | Steam login |
| `password` | string | Steam password (stored in plain text!) |
| `mafile` | string \| null | Path to `.maFile` (absolute or relative to `main.py`) |
| `guard_source` | `"mafile"` \| `"nebula"` | Where to get the Steam Guard code from |
| `nebula_account_name` | string \| null | Account name as shown in NebulaAuth list. `null` → uses `login` |

### Settings

| Field | Description |
| --- | --- |
| `chrome_profiles_dir` | Folder for Chrome profiles (default: `chrome_profiles`) |
| `nebula_auth_path` | Full path to `NebulaAuth.exe` |

---

## How It Works

### `mafile` mode

1. The program opens the `.maFile` and extracts `shared_secret`.
2. Computes the TOTP code from the current time (HMAC-SHA1 + Steam Guard character
   encoding: `23456789BCDFGHJKMNPQRTVWXY`).
3. If fewer than 5 seconds remain before the code rotates, it waits for the next one
   so the code doesn't expire mid-entry.
4. Enters the code into the Steam form.

### `nebula` mode

1. Launches `NebulaAuth.exe` (if a path is set in Settings).
2. Uses `pywinauto` (UI Automation) to locate the `NebulaAuth*` window.
3. Finds the account in the left list by prefix match (handles truncated names with `...`).
4. Clicks the account → waits for the 5-character code to appear on the right.
5. Clicks the code → NebulaAuth copies it to the clipboard.
6. The program reads the clipboard and enters the code into Steam.

If automation fails (e.g. the NebulaAuth UI changed), there is a fallback: the program
asks you to copy the code manually and detects it from the clipboard within 60 seconds.

### Browser

- Selenium 4.6+ downloads a compatible chromedriver automatically via Selenium Manager.
- Each account uses a separate `--user-data-dir`.
- `SingletonLock` is cleaned from the profile folder before launch (in case Chrome crashed).
- Flags like `--disable-blink-features=AutomationControlled` mask Selenium from Steam's
  automation detector.
- `detach=True` — Chrome stays open after the program finishes its login sequence.

---

## Security

**IMPORTANT:** passwords are stored in `accounts.json` in plain text. This is a
deliberate decision for simplicity of local use. As a result:

- Do not leave `accounts.json` on a shared PC.
- Do not commit `accounts.json`, `mafiles/`, or `chrome_profiles/` to git.
- If you share your PC with others, consider rewriting the config module to use an
  encrypted store with a master password.

Recommended `.gitignore` entries:

```
accounts.json
mafiles/
chrome_profiles/
__pycache__/
*.pyc
```

---

## Troubleshooting

### `Chrome instance exited`
Outdated chromedriver cache. Clear it:
```powershell
Remove-Item "$env:LOCALAPPDATA\.cache\selenium" -Recurse -Force
```

### `No such element: //input[@type='password']`
Steam changed the login form markup. Run `debug_enter_code.py` and share the output —
the selectors will be updated.

### `NebulaAuth window not found`
- NebulaAuth is not running. Set `nebula_auth_path` in Settings, or open NebulaAuth
  before clicking Login.
- The window is minimized to tray. Restore it from the tray.

### `Account '<name>' not found in NebulaAuth list`
The name in NebulaAuth differs from the Steam login. Open the account via **Edit**
and fill in the **Name in NebulaAuth** field with exactly what you see in the list.

### Captcha on login
Steam sometimes shows a CAPTCHA when it suspects automation. The browser window stays
open — solve the captcha manually, and the script will continue entering the code.

### Shortcut icon not updating
Explorer cache. Run `ie4uinit.exe -show` or sign out and back in.

---

## Dependencies

| Package | Purpose |
| --- | --- |
| `selenium` | Chrome automation |
| `pyperclip` | Clipboard read/write for NebulaAuth integration |
| `pywinauto` | UI Automation for NebulaAuth integration |

`tkinter` is part of the Python standard library — no installation needed.

---

## License

Personal pet project, use at your own risk. The program works with your own Steam
accounts and `.maFile` files that you created via Steam Mobile Authenticator / NebulaAuth.
