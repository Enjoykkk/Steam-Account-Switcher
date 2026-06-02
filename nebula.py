"""NebulaAuth 集成：启动应用、自动点击账号、复制 Steam Guard 代码并从剪贴板读取。"""

import subprocess
import time
from pathlib import Path

import pyperclip


VALID_CHARS = set("23456789BCDFGHJKMNPQRTVWXY")
NEBULA_WINDOW_TITLE_RE = r"^NebulaAuth.*"


def launch_nebula(exe_path):
    path = Path(exe_path)
    if not path.exists():
        raise FileNotFoundError(f"未找到 NebulaAuth: {exe_path}")
    subprocess.Popen([str(path)])


def _looks_like_guard_code(text):
    stripped = text.strip().upper()
    if len(stripped) != 5:
        return False
    return all(c in VALID_CHARS for c in stripped)


def get_code_from_clipboard(timeout=60):
    """等待用户从 NebulaAuth 复制 Steam Guard 代码到剪贴板。

    若调用时剪贴板中已有有效代码则直接使用；否则清空剪贴板并等待新的 5 位值。
    """
    current = pyperclip.paste()
    if _looks_like_guard_code(current):
        return current.strip().upper()

    try:
        pyperclip.copy("")
    except Exception:
        pass

    initial = pyperclip.paste()
    deadline = time.time() + timeout

    while time.time() < deadline:
        current = pyperclip.paste()
        if current != initial and _looks_like_guard_code(current):
            return current.strip().upper()
        time.sleep(0.25)

    raise TimeoutError(
        "剪贴板中未出现 Steam Guard 代码。"
        "请打开 NebulaAuth 并点击代码进行复制。"
    )


def _find_nebula_window(timeout=5):
    """返回 NebulaAuth 窗口（pywinauto WindowSpecification），找不到则返回 None。"""
    from pywinauto import Desktop  # 延迟导入：pywinauto 较重

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            win = Desktop(backend="uia").window(title_re=NEBULA_WINDOW_TITLE_RE)
            if win.exists() and win.is_visible():
                return win
        except Exception:
            pass
        time.sleep(0.3)
    return None


def _iter_descendants(window):
    """遍历窗口所有子元素，避免 pywinauto 异常中断。"""
    try:
        for el in window.descendants():
            yield el
    except Exception:
        return


def _element_text(el):
    """安全获取元素文本。"""
    try:
        return (el.window_text() or "").strip()
    except Exception:
        return ""


def get_code_from_nebula(account_name, timeout=15):
    """自动点击 NebulaAuth 中账号并获取写入剪贴板的代码。

    account_name 是账号在 NebulaAuth 列表中的显示名。
    支持前缀匹配（NebulaAuth 可能会截断较长名称）。
    """
    window = _find_nebula_window(timeout=5)
    if window is None:
        raise RuntimeError(
            "未找到 NebulaAuth 窗口。请先启动 NebulaAuth，"
            "或在设置中填写 exe 路径。"
        )

    try:
        window.set_focus()
    except Exception:
        pass

    account_lc = account_name.lower()

    # 1) 在列表中查找账号行。NebulaAuth 可能截断长名称，
    # 因此同时判断双向前缀。
    deadline = time.time() + timeout
    account_el = None
    while time.time() < deadline:
        for el in _iter_descendants(window):
            text = _element_text(el)
            if not text or len(text) > 80:
                continue
            tl = text.lower().rstrip(".")  # NebulaAuth 会为截断项追加 "..."
            if tl.startswith(account_lc) or account_lc.startswith(tl):
                account_el = el
                break
        if account_el:
            break
        time.sleep(0.3)

    if account_el is None:
        raise RuntimeError(
            f"在 NebulaAuth 列表中未找到账号“{account_name}”。"
            f"请核对 NebulaAuth 窗口中的准确名称。"
        )

    # 清空剪贴板，确保后续读取到的是新代码
    try:
        pyperclip.copy("")
    except Exception:
        pass

    try:
        account_el.click_input()
    except Exception as e:
        raise RuntimeError(f"无法点击 NebulaAuth 中的账号: {e}")

    # 2) 等待右侧面板出现 5 位代码
    time.sleep(0.4)
    deadline = time.time() + 8
    code_el = None
    while time.time() < deadline:
        for el in _iter_descendants(window):
            text = _element_text(el)
            stripped = text.strip().upper()
            if len(stripped) == 5 and all(c in VALID_CHARS for c in stripped):
                code_el = el
                break
        if code_el:
            break
        time.sleep(0.2)

    if code_el is None:
        raise RuntimeError(
            "选择账号后，未在 NebulaAuth 窗口中找到 Steam Guard 代码。"
        )

    # 3) 点击代码后，NebulaAuth 会将其复制到剪贴板
    try:
        code_el.click_input()
    except Exception as e:
        raise RuntimeError(f"无法点击 NebulaAuth 中的代码: {e}")

    # 4) 从剪贴板读取代码（带轻量重试，点击后可能不会立即更新）
    deadline = time.time() + 3
    while time.time() < deadline:
        clip = pyperclip.paste()
        stripped = (clip or "").strip().upper()
        if len(stripped) == 5 and all(c in VALID_CHARS for c in stripped):
            return stripped
        time.sleep(0.1)

    raise RuntimeError(
        "点击代码后剪贴板未获得有效值。"
        f"当前剪贴板内容: {pyperclip.paste()!r}"
    )
