"""通过 Selenium Chrome 自动化 Steam 登录。"""

import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import (
    InvalidSessionIdException,
    NoSuchWindowException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# 这些异常表示用户手动关闭了浏览器窗口，不属于程序错误。
WINDOW_CLOSED_EXCEPTIONS = (InvalidSessionIdException, NoSuchWindowException)


def _is_window_closed_error(exc):
    if isinstance(exc, WINDOW_CLOSED_EXCEPTIONS):
        return True
    if isinstance(exc, WebDriverException):
        msg = (str(exc) or "").lower()
        return any(
            phrase in msg
            for phrase in (
                "invalid session",
                "target window already closed",
                "not connected to devtools",
                "web view not found",
                "no such window",
                "chrome not reachable",
            )
        )
    return False


STEAM_LOGIN_URL = "https://store.steampowered.com/login/"


def _cleanup_profile_locks(profile_dir):
    """清理 Chrome 崩溃遗留的 SingletonLock，否则配置目录可能无法打开。"""
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        lock = Path(profile_dir) / name
        try:
            if lock.exists() or lock.is_symlink():
                lock.unlink()
        except OSError:
            pass


def make_driver(profile_dir=None):
    options = Options()
    if profile_dir:
        profile_path = Path(profile_dir).absolute()
        profile_path.mkdir(parents=True, exist_ok=True)
        _cleanup_profile_locks(profile_path)
        options.add_argument(f"--user-data-dir={profile_path}")

    # 基础稳定性参数
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-features=ChromeWhatsNewUI")
    options.add_argument("--start-maximized")

    # 隐藏 Selenium 痕迹，降低被 Steam 拦截概率
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # detach：GUI 线程结束登录流程后不自动关闭 Chrome
    options.add_experimental_option("detach", True)

    # Selenium 4.6+ 会通过 Selenium Manager 自动下载匹配的 chromedriver
    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def login(driver, username, password, guard_code_callback, status_callback=None):
    """填写 Steam 登录表单。

    guard_code_callback() -> str：需要 Steam Guard 代码时调用。
    status_callback(text)：可选，用于在 UI 中显示状态。
    """
    def status(text):
        if status_callback:
            status_callback(text)

    status("正在打开 Steam...")
    driver.get(STEAM_LOGIN_URL)

    wait = WebDriverWait(driver, 30)

    status("等待登录表单...")
    user_input, pass_input, submit_btn = _find_login_form(driver)

    user_input.clear()
    user_input.send_keys(username)
    pass_input.clear()
    pass_input.send_keys(password)

    status("提交表单...")
    submit_btn.click()

    # 提交后 Steam 可能先展示“通过手机应用确认”页面。
    # 点击 “Enter a code instead” 进入代码输入界面。
    status("等待 Steam Guard...")
    _click_enter_code_instead(driver, timeout=10)

    guard_inputs = _wait_for_guard_inputs(driver, timeout=20)

    if guard_inputs:
        status("获取代码...")
        code = guard_code_callback()
        status(f"输入代码 {code}...")
        _enter_guard_code(driver, guard_inputs, code)

    # 等待从 login 页面跳转
    status("等待登录完成...")
    try:
        WebDriverWait(driver, 30).until(
            lambda d: "login" not in d.current_url.lower()
        )
        status("完成")
    except Exception as e:
        if _is_window_closed_error(e):
            status("浏览器窗口已关闭")
        else:
            status("登录未确认，请检查浏览器窗口")


def _find_login_form(driver):
    """返回 Steam 登录表单中的 (登录框, 密码框, 提交按钮)。

    注意：不要在整页范围查找用户名框（页头还有 Steam 搜索框），
    而是在密码框所在的同一个 <form> 内查找。
    """
    # 1) 先等待密码输入框——它是登录表单锚点
    deadline = time.time() + 30
    pass_input = None
    while time.time() < deadline:
        for el in driver.find_elements(By.XPATH, "//input[@type='password']"):
            try:
                if el.is_displayed():
                    pass_input = el
                    break
            except Exception:
                continue
        if pass_input:
            break
        time.sleep(0.3)

    if not pass_input:
        raise RuntimeError(
            "密码输入框未出现。Steam 可能显示了验证码，请查看浏览器。"
        )

    # 2) 将用户名和提交按钮的搜索范围限制在包含密码框的表单内
    try:
        scope = pass_input.find_element(By.XPATH, "./ancestor::form[1]")
    except Exception:
        # 没有 form 标签时，取最近且同时包含两个输入框的 div 容器
        scope = None
        for level in range(1, 10):
            ancestor_xpath = "./" + "/".join([".."] * level)
            try:
                container = pass_input.find_element(By.XPATH, ancestor_xpath)
            except Exception:
                break
            text_inputs = container.find_elements(
                By.XPATH,
                ".//input[@type='text' or @type='email' or @type='tel' or not(@type)]",
            )
            if any(el.is_displayed() for el in text_inputs):
                scope = container
                break
        if scope is None:
            raise RuntimeError("未找到登录表单容器")

    # 3) 在表单内查找用户名输入框
    user_input = None
    for el in scope.find_elements(
        By.XPATH, ".//input[@type='text' or @type='email' or @type='tel' or not(@type)]"
    ):
        try:
            if el.is_displayed():
                user_input = el
                break
        except Exception:
            continue
    if not user_input:
        raise RuntimeError("未在表单内找到账号名输入框")

    # 4) 在表单内查找提交按钮
    submit_btn = None
    for xp in (
        ".//button[@type='submit']",
        ".//input[@type='submit']",
        ".//button",
    ):
        for el in scope.find_elements(By.XPATH, xp):
            try:
                if el.is_displayed() and el.is_enabled():
                    submit_btn = el
                    break
            except Exception:
                continue
        if submit_btn:
            break
    if not submit_btn:
        raise RuntimeError("未找到“登录”按钮")

    return user_input, pass_input, submit_btn


_JS_FIND_ENTER_CODE = r"""
const phrases = ['enter a code', '输入代码', '请输入代码'];

// directText: 仅节点自身文本（不递归 children）
function directText(el) {
    let s = '';
    for (const n of el.childNodes) {
        if (n.nodeType === 3) s += n.textContent || '';
    }
    return s.trim().toLowerCase();
}

// 查找自身文本包含短语的元素——这样更可能是叶子节点，
// 而不是包含大量嵌套文本的父容器
const all = document.querySelectorAll('*');
for (const el of all) {
    const t = directText(el);
    if (!t || t.length > 100) continue;
    if (!phrases.some(p => t.includes(p))) continue;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;

    // 向上查找可点击祖先：<a>、<button>、role=button、onclick
    let target = el;
    let cursor = el;
    for (let i = 0; i < 6 && cursor; i++) {
        const tag = (cursor.tagName || '').toLowerCase();
        const role = cursor.getAttribute && cursor.getAttribute('role');
        if (tag === 'a' || tag === 'button' || role === 'button' || cursor.onclick) {
            target = cursor;
            break;
        }
        cursor = cursor.parentElement;
    }
    return target;
}
return null;
"""

_JS_CLICK_REACT = r"""
const el = arguments[0];
el.scrollIntoView({block: 'center', inline: 'center'});
const opts = {bubbles: true, cancelable: true, view: window, button: 0};
// 完整鼠标事件序列——React 可能依赖这些事件触发合成 click
el.dispatchEvent(new MouseEvent('mouseover', opts));
el.dispatchEvent(new MouseEvent('mouseenter', opts));
el.dispatchEvent(new MouseEvent('mousedown', opts));
el.dispatchEvent(new MouseEvent('mouseup', opts));
el.dispatchEvent(new MouseEvent('click', opts));
if (typeof el.click === 'function') el.click();
"""

_JS_COUNT_GUARD_INPUTS = r"""
const inputs = document.querySelectorAll('input[maxlength="1"]');
let n = 0;
for (const el of inputs) {
    const rect = el.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) n++;
}
return n;
"""


def _click_enter_code_instead(driver, timeout=15):
    """通过 JS + React 事件模拟点击 'Enter a code instead'。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if driver.execute_script(_JS_COUNT_GUARD_INPUTS) >= 5:
                return False
            el = driver.execute_script(_JS_FIND_ENTER_CODE)
            if el is not None:
                driver.execute_script(_JS_CLICK_REACT, el)
                # 给 React 一点时间渲染代码输入框
                time.sleep(0.5)
                if driver.execute_script(_JS_COUNT_GUARD_INPUTS) >= 5:
                    return True
                # 输入框未出现，0.5 秒后重试
                continue
        except Exception as e:
            if _is_window_closed_error(e):
                return False
        time.sleep(0.3)
    return False


def _wait_for_guard_inputs(driver, timeout=20):
    """等待 Steam Guard 代码输入框出现，返回输入框列表或 []。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            inputs = driver.find_elements(By.XPATH, "//input[@maxlength='1']")
            visible = [i for i in inputs if i.is_displayed()]
            if len(visible) >= 5:
                return visible[:5]
            # 可能已登录（无需 2FA 或会话仍有效）
            if "login" not in driver.current_url.lower():
                return []
        except Exception as e:
            if _is_window_closed_error(e):
                return []
            raise
        time.sleep(0.3)
    return []


def _enter_guard_code(driver, inputs, code):
    """将 5 位代码填入输入框，Steam 通常会自动跳到下一个框。"""
    code = code.strip().upper()
    if len(code) != 5:
        raise ValueError(f"代码长度无效: {code!r}")

    try:
        inputs[0].click()
    except Exception:
        pass

    actions = ActionChains(driver)
    for ch in code:
        actions.send_keys(ch)
    actions.perform()

    # 若自动跳转未生效，则逐个输入框显式填写
    time.sleep(0.5)
    try:
        values = [el.get_attribute("value") or "" for el in inputs]
        if "".join(values).strip() != code:
            for el, ch in zip(inputs, code):
                el.clear()
                el.send_keys(ch)
    except Exception:
        pass
