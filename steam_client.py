"""自动化登录 Steam 桌面客户端（GUI 表单自动化）。

流程：
  1. 关闭当前 Steam（含所有辅助进程）。
  2. 重新启动 Steam，出现“谁在玩？”页面。
  3. 点击 “+”（添加账号）进入登录表单。
  4. 输入登录名/密码并提交。
  5. 在 Steam Guard 页面输入验证码（来自 mafile/NebulaAuth）。

客户端界面基于 Chromium（CEF），因此使用 pywinauto（UI Automation）
定位控件并配合键盘输入。选择器按真实控件树调优（见 debug_steam_client.py）。

备注：在新版客户端中，CLI 参数 `steam.exe -login user pass`
不会执行在线登录（只会从缓存恢复离线会话），因此这里不使用该方式。
"""

import subprocess
import time
from pathlib import Path


DEFAULT_STEAM_PATHS = [
    r"C:\Program Files (x86)\Steam\steam.exe",
    r"C:\Program Files\Steam\steam.exe",
]


def _steam_exe_from_registry():
    """从注册表读取 steam.exe 路径（适用于非默认安装目录）。"""
    try:
        import winreg
    except ImportError:
        return None
    for hive, key in (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
    ):
        try:
            with winreg.OpenKey(hive, key) as k:
                for value in ("SteamExe", "InstallPath"):
                    try:
                        raw, _ = winreg.QueryValueEx(k, value)
                    except FileNotFoundError:
                        continue
                    if not raw:
                        continue
                    candidate = Path(raw.replace("/", "\\"))
                    if candidate.is_dir():
                        candidate = candidate / "steam.exe"
                    if candidate.exists():
                        return str(candidate)
        except OSError:
            continue
    return None


def find_steam_exe(configured=None):
    """查找 steam.exe：配置路径 → 注册表 → 默认目录。"""
    if configured and Path(configured).exists():
        return configured

    from_reg = _steam_exe_from_registry()
    if from_reg:
        return from_reg

    for p in DEFAULT_STEAM_PATHS:
        if Path(p).exists():
            return p
    return None


# Steam 除 steam.exe 外还会拉起的辅助进程。
# SteamService.exe 是系统服务，不进行处理。
STEAM_PROCESS_NAMES = ("steam.exe", "steamwebhelper.exe")


def _running_pids(image_name):
    """通过 tasklist 按进程名获取 PID（无第三方依赖）。"""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True,
        ).stdout
    except Exception:
        return set()

    name_lc = image_name.lower()
    pids = set()
    for line in out.splitlines():
        line = line.strip()
        if not line or not line.lower().startswith(f'"{name_lc}'):
            continue
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2:
            try:
                pids.add(int(parts[1]))
            except ValueError:
                pass
    return pids


def _pid_name_map():
    """PID -> 进程名映射（用于判断窗口归属进程）。"""
    try:
        out = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True
        ).stdout
    except Exception:
        return {}
    mapping = {}
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2:
            try:
                mapping[int(parts[1])] = parts[0]
            except ValueError:
                pass
    return mapping


def _steam_pids():
    return _running_pids("steam.exe")


def _all_steam_pids():
    pids = set()
    for name in STEAM_PROCESS_NAMES:
        pids |= _running_pids(name)
    return pids


def is_steam_running():
    return bool(_steam_pids())


def _force_kill_leftovers():
    """强制结束残留的 Steam 进程（不含 SteamService）。"""
    for name in STEAM_PROCESS_NAMES:
        if _running_pids(name):
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", name, "/T"],
                    capture_output=True, text=True,
                )
            except Exception:
                pass


def shutdown_steam(steam_exe, wait_timeout=30, grace=2.0):
    """正确关闭 Steam 及其全部辅助进程。

    否则 steamwebhelper.exe 可能残留，导致重新启动后进入“无连接”状态。
    """
    if not _all_steam_pids():
        return True

    try:
        subprocess.Popen([steam_exe, "-shutdown"])
    except Exception:
        pass

    # 等待 steam.exe 与所有 steamwebhelper.exe 退出
    deadline = time.time() + wait_timeout
    while time.time() < deadline:
        if not _all_steam_pids():
            time.sleep(grace)  # 干净重启前的缓冲等待
            return True
        time.sleep(0.5)

    # 超时未退出：强制清理残留进程后再等待
    _force_kill_leftovers()
    deadline = time.time() + 8
    while time.time() < deadline:
        if not _all_steam_pids():
            time.sleep(grace)
            return True
        time.sleep(0.5)

    return not _all_steam_pids()


# ---------------------------------------------------------------------------
# 坐标按窗口 '登录 Steam'（class SDL_app）的比例 (fx, fy) 定义。
# Steam-CEF 不能通过 UIA 暴露控件，因此采用坐标点击。
# 如有必要可按实际界面微调。
# ---------------------------------------------------------------------------
STEAM_UI_WINDOW_CLASS = "SDL_app"
LOGIN_FORM_TITLE = "登录 Steam"

# “谁在玩？”页面中的 “+” 按钮（添加账号），位于头像右侧。
PICKER_ADD_FRAC = (0.90, 0.55)

# 登录表单中的输入框与按钮。
FORM_USERNAME_FRAC = (0.33, 0.32)
FORM_PASSWORD_FRAC = (0.33, 0.50)
FORM_LOGIN_BTN_FRAC = (0.33, 0.69)

# “通过手机应用确认登录”页面中的“使用代码登录”链接。
LOGIN_WITH_CODE_FRAC = (0.50, 0.74)

# 时间参数（秒）。
CONFIRM_SCREEN_WAIT = 15.0   # 等待服务端校验登录名/密码
CODE_SCREEN_WAIT = 1.5       # 等待代码输入框出现


def _escape_keys(text):
    """转义 pywinauto.keyboard 特殊字符（ +^%~(){}[] ）。"""
    special = set("+^%~(){}[]")
    return "".join("{%s}" % ch if ch in special else ch for ch in text)


def _type_text(text):
    import pywinauto.keyboard as keyboard
    keyboard.send_keys(_escape_keys(text), pause=0.02, with_spaces=True)


def _send(keys):
    import pywinauto.keyboard as keyboard
    keyboard.send_keys(keys, pause=0.05)


def _find_steam_ui_window(timeout=90, title_contains=None):
    """查找可见的 Steam UI 窗口（steamwebhelper.exe 的 SDL_app 窗口）。"""
    from pywinauto import Desktop

    deadline = time.time() + timeout
    while time.time() < deadline:
        pids = _all_steam_pids()
        if pids:
            try:
                for w in Desktop(backend="uia").windows():
                    try:
                        if not w.is_visible() or w.process_id() not in pids:
                            continue
                        if w.class_name() != STEAM_UI_WINDOW_CLASS:
                            continue
                        title = (w.window_text() or "")
                        if title_contains and title_contains.lower() not in title.lower():
                            continue
                        return w
                    except Exception:
                        continue
            except Exception:
                pass
        time.sleep(0.5)
    return None


def _abs_coords(window, fx, fy):
    r = window.rectangle()
    return int(r.left + fx * r.width()), int(r.top + fy * r.height())


def _click_fraction(window, fx, fy):
    """按窗口比例坐标点击并恢复窗口焦点。"""
    from pywinauto import mouse
    try:
        window.set_focus()
    except Exception:
        pass
    time.sleep(0.2)
    x, y = _abs_coords(window, fx, fy)
    mouse.click(button="left", coords=(x, y))
    time.sleep(0.2)


def login_steam_client(
    steam_exe,
    username,
    password,
    guard_code_callback,
    status_callback=None,
    restart_if_running=True,
):
    """通过 GUI 自动化将账号登录到 Steam 桌面客户端。

    流程：关闭 Steam → 启动 → 选择页点击 “+” → 登录表单 → Steam Guard。
    由于 CEF 控件无法通过 UIA 访问，采用坐标点击 + 键盘输入。
    """
    def status(text):
        if status_callback:
            status_callback(text)

    if not steam_exe or not Path(steam_exe).exists():
        raise FileNotFoundError("未找到 steam.exe。请在“设置”中指定 Steam 路径。")

    if restart_if_running and is_steam_running():
        status("正在关闭当前 Steam...")
        if not shutdown_steam(steam_exe):
            raise RuntimeError(
                "无法关闭正在运行的 Steam。请手动关闭后重试。"
            )

    status("正在启动 Steam...")
    try:
        subprocess.Popen([steam_exe])
    except Exception as e:
        raise RuntimeError(f"无法启动 Steam: {e}")

    # 1) 等待登录界面（“谁在玩？”页面/登录表单均为 class=SDL_app）。
    # 不按标题过滤：选择页标题可能与登录表单不同。
    status("等待 Steam 登录界面...")
    window = _find_steam_ui_window(timeout=120)
    if window is None:
        raise RuntimeError(
            "Steam 登录窗口未出现。可能已自动登录账号——"
            "请在 Steam 中执行“切换账号”后重试。"
        )
    time.sleep(1.5)  # 等待 CEF 完成渲染

    # 2) 点击 “+”（添加账号）。若已在表单页，点击空白位置也无副作用。
    status("打开登录表单（+）...")
    _click_fraction(window, *PICKER_ADD_FRAC)
    time.sleep(1.5)

    # 窗口可能被重建，重新获取一次
    window = _find_steam_ui_window(timeout=15) or window

    # 3) 填写登录表单
    status("输入登录名和密码...")
    _fill_login_form(window, username, password)

    # 4) “通过手机应用确认登录”页面 → 点击“使用代码登录”
    status("等待确认页面...")
    time.sleep(CONFIRM_SCREEN_WAIT)  # 等待服务端校验登录名/密码
    window = _find_steam_ui_window(timeout=20) or window
    status("切换到代码输入...")
    _click_fraction(window, *LOGIN_WITH_CODE_FRAC)
    time.sleep(CODE_SCREEN_WAIT)

    # 5) Steam Guard 代码输入页面
    window = _find_steam_ui_window(timeout=15) or window
    status("获取 Steam Guard 代码...")
    code = guard_code_callback()
    status(f"输入代码 {code}...")
    _type_guard_code(window, code)
    status("代码已输入——请检查 Steam 窗口")


def _fill_login_form(window, username, password):
    """点击登录表单字段并通过键盘输入数据。"""
    # 登录名
    _click_fraction(window, *FORM_USERNAME_FRAC)
    _send("^a")  # 全选后覆盖
    time.sleep(0.1)
    _type_text(username)
    time.sleep(0.2)

    # 密码
    _click_fraction(window, *FORM_PASSWORD_FRAC)
    _send("^a")
    time.sleep(0.1)
    _type_text(password)
    time.sleep(0.2)

    # 提交（在密码框按 Enter）。若无效，再点击“登录”按钮。
    _send("{ENTER}")
    time.sleep(0.6)


def _type_guard_code(window, code):
    """输入 Steam Guard 代码。点击“使用代码登录”后，第一个输入框会自动聚焦，
    因此只需激活窗口并发送按键。"""
    code = code.strip().upper()
    if len(code) != 5:
        raise ValueError(f"代码长度无效: {code!r}")

    try:
        window.set_focus()
    except Exception:
        pass
    time.sleep(0.4)
    for ch in code:
        _send(ch)
        time.sleep(0.08)
