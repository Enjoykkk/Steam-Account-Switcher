"""Автоматизация Steam login через Selenium Chrome."""

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


# Эти исключения = пользователь закрыл окно браузера. Это не ошибка.
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
    """Снимает SingletonLock от прежнего падения Chrome — иначе профиль не откроется."""
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

    # Базовые флаги стабильности
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-features=ChromeWhatsNewUI")
    options.add_argument("--start-maximized")

    # Маскируем selenium чтобы Steam не блокировал
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # detach — чтобы Chrome не закрывался когда GUI-поток завершит логин
    options.add_experimental_option("detach", True)

    # Selenium 4.6+ сам качает подходящий chromedriver через Selenium Manager
    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def login(driver, username, password, guard_code_callback, status_callback=None):
    """Заполняет форму логина Steam.

    guard_code_callback() -> str — вызывается когда нужен Steam Guard код.
    status_callback(text) — опционально, для отображения статуса в UI.
    """
    def status(text):
        if status_callback:
            status_callback(text)

    status("Открываю Steam...")
    driver.get(STEAM_LOGIN_URL)

    wait = WebDriverWait(driver, 30)

    status("Жду форму логина...")
    user_input, pass_input, submit_btn = _find_login_form(driver)

    user_input.clear()
    user_input.send_keys(username)
    pass_input.clear()
    pass_input.send_keys(password)

    status("Отправляю форму...")
    submit_btn.click()

    # После сабмита Steam может сначала показать экран "подтверди через моб. приложение".
    # Кликаем "Enter a code instead" чтобы попасть на ввод кода.
    status("Жду Steam Guard...")
    _click_enter_code_instead(driver, timeout=10)

    guard_inputs = _wait_for_guard_inputs(driver, timeout=20)

    if guard_inputs:
        status("Получаю код...")
        code = guard_code_callback()
        status(f"Ввожу код {code}...")
        _enter_guard_code(driver, guard_inputs, code)

    # Ждём редирект с login-страницы
    status("Жду завершения логина...")
    try:
        WebDriverWait(driver, 30).until(
            lambda d: "login" not in d.current_url.lower()
        )
        status("Готово")
    except Exception as e:
        if _is_window_closed_error(e):
            status("Окно браузера закрыто")
        else:
            status("Логин не подтвердился, проверь окно браузера")


def _find_login_form(driver):
    """Возвращает (поле_логина, поле_пароля, кнопка_submit) внутри формы Steam-логина.

    Важно: ищем username не по всей странице (там есть поиск Steam в шапке),
    а внутри той же <form>, где находится поле пароля.
    """
    # 1) Ждём поле пароля — это якорь формы логина
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
            "Поле пароля не появилось. Возможно Steam показал капчу — посмотри браузер."
        )

    # 2) Скоупим поиск username и submit внутрь формы, содержащей пароль
    try:
        scope = pass_input.find_element(By.XPATH, "./ancestor::form[1]")
    except Exception:
        # Нет тега form — берём ближайший div-контейнер с обоими полями
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
            raise RuntimeError("Не нашёл контейнер формы логина")

    # 3) Username внутри формы
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
        raise RuntimeError("Не нашёл поле имени аккаунта внутри формы")

    # 4) Submit внутри формы
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
        raise RuntimeError("Не нашёл кнопку 'Войти'")

    return user_input, pass_input, submit_btn


_JS_FIND_ENTER_CODE = r"""
const phrases = ['enter a code', 'введите код', 'ввести код'];

// directText: только прямой текст узла (без рекурсии в children)
function directText(el) {
    let s = '';
    for (const n of el.childNodes) {
        if (n.nodeType === 3) s += n.textContent || '';
    }
    return s.trim().toLowerCase();
}

// Ищем элемент чей собственный текст содержит фразу — это будет листовой элемент,
// не родительский контейнер с кучей вложенного текста
const all = document.querySelectorAll('*');
for (const el of all) {
    const t = directText(el);
    if (!t || t.length > 100) continue;
    if (!phrases.some(p => t.includes(p))) continue;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;

    // Поднимаемся до кликабельного предка: <a>, <button>, role=button, onclick
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
// Полная последовательность событий мыши — React ловит синтетический click через них
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
    """Кликает 'Enter a code instead' через JS с эмуляцией событий React."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if driver.execute_script(_JS_COUNT_GUARD_INPUTS) >= 5:
                return False
            el = driver.execute_script(_JS_FIND_ENTER_CODE)
            if el is not None:
                driver.execute_script(_JS_CLICK_REACT, el)
                # Дать React время отрисовать поля кода
                time.sleep(0.5)
                if driver.execute_script(_JS_COUNT_GUARD_INPUTS) >= 5:
                    return True
                # Поля не появились — пробуем ещё раз через 0.5с
                continue
        except Exception as e:
            if _is_window_closed_error(e):
                return False
        time.sleep(0.3)
    return False


def _wait_for_guard_inputs(driver, timeout=20):
    """Ждём появления полей ввода Steam Guard кода. Возвращаем список или []."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            inputs = driver.find_elements(By.XPATH, "//input[@maxlength='1']")
            visible = [i for i in inputs if i.is_displayed()]
            if len(visible) >= 5:
                return visible[:5]
            # Возможно уже залогинились (нет 2FA или сессия живая)
            if "login" not in driver.current_url.lower():
                return []
        except Exception as e:
            if _is_window_closed_error(e):
                return []
            raise
        time.sleep(0.3)
    return []


def _enter_guard_code(driver, inputs, code):
    """Вводит 5-символьный код в поля. Steam обычно сам переходит к следующему полю."""
    code = code.strip().upper()
    if len(code) != 5:
        raise ValueError(f"Неверная длина кода: {code!r}")

    try:
        inputs[0].click()
    except Exception:
        pass

    actions = ActionChains(driver)
    for ch in code:
        actions.send_keys(ch)
    actions.perform()

    # Если автопереход не сработал — вводим в каждое поле явно
    time.sleep(0.5)
    try:
        values = [el.get_attribute("value") or "" for el in inputs]
        if "".join(values).strip() != code:
            for el, ch in zip(inputs, code):
                el.clear()
                el.send_keys(ch)
    except Exception:
        pass
