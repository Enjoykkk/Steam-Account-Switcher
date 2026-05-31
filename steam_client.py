"""Автоматизация входа в десктопный клиент Steam (GUI-автоматизация формы).

Поток:
  1. Закрываем текущий Steam (со всеми вспомогательными процессами).
  2. Запускаем Steam заново — появляется экран "Кто играет?".
  3. Кликаем "+" (добавить аккаунт) → появляется форма логина.
  4. Вводим логин/пароль, отправляем.
  5. На экране Steam Guard вводим код (из mafile/NebulaAuth).

Интерфейс клиента — Chromium (CEF), поэтому используем pywinauto (UI Automation)
для поиска контролов + ввод с клавиатуры. Селекторы подгоняются по реальному
дереву контролов (см. debug_steam_client.py).

Примечание: CLI-аргумент `steam.exe -login user pass` на современном клиенте
НЕ выполняет онлайн-вход (поднимает офлайн-сессию из кэша), поэтому не используется.
"""

import subprocess
import time
from pathlib import Path


DEFAULT_STEAM_PATHS = [
    r"C:\Program Files (x86)\Steam\steam.exe",
    r"C:\Program Files\Steam\steam.exe",
]


def _steam_exe_from_registry():
    """Путь к steam.exe из реестра (надёжно при нестандартной установке)."""
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
    """Находит steam.exe: настройки → реестр → стандартные папки."""
    if configured and Path(configured).exists():
        return configured

    from_reg = _steam_exe_from_registry()
    if from_reg:
        return from_reg

    for p in DEFAULT_STEAM_PATHS:
        if Path(p).exists():
            return p
    return None


# Вспомогательные процессы, которые Steam порождает помимо steam.exe.
# SteamService.exe — системная служба, её НЕ трогаем.
STEAM_PROCESS_NAMES = ("steam.exe", "steamwebhelper.exe")


def _running_pids(image_name):
    """PID'ы процесса по имени образа через tasklist (без сторонних зависимостей)."""
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
    """Карта PID -> имя процесса (для определения какому процессу принадлежит окно)."""
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
    """Добивает зависшие процессы Steam (кроме SteamService)."""
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
    """Корректно закрывает Steam и ВСЕ его вспомогательные процессы.

    Без этого steamwebhelper.exe остаётся висеть, и новый запуск стартует в
    режиме 'НЕТ СОЕДИНЕНИЯ'.
    """
    if not _all_steam_pids():
        return True

    try:
        subprocess.Popen([steam_exe, "-shutdown"])
    except Exception:
        pass

    # Ждём пока завершатся и steam.exe, и все steamwebhelper.exe
    deadline = time.time() + wait_timeout
    while time.time() < deadline:
        if not _all_steam_pids():
            time.sleep(grace)  # пауза перед чистым перезапуском
            return True
        time.sleep(0.5)

    # Не дождались — добиваем зависшие и ждём ещё немного
    _force_kill_leftovers()
    deadline = time.time() + 8
    while time.time() < deadline:
        if not _all_steam_pids():
            time.sleep(grace)
            return True
        time.sleep(0.5)

    return not _all_steam_pids()


# ---------------------------------------------------------------------------
# Координаты — доли (fx, fy) относительно окна 'Войти в Steam' (class SDL_app).
# Steam-CEF не отдаёт контролы через UIA, поэтому кликаем по координатам.
# При необходимости подгоняются под реальный интерфейс.
# ---------------------------------------------------------------------------
STEAM_UI_WINDOW_CLASS = "SDL_app"
LOGIN_FORM_TITLE = "Войти в Steam"

# Экран "Кто играет?" — кнопка "+" (добавить аккаунт). Справа от аватарок.
PICKER_ADD_FRAC = (0.90, 0.55)

# Форма логина — поля и кнопка.
FORM_USERNAME_FRAC = (0.33, 0.32)
FORM_PASSWORD_FRAC = (0.33, 0.50)
FORM_LOGIN_BTN_FRAC = (0.33, 0.69)

# Экран "Подтвердите вход через моб. приложение" — ссылка "Войти с помощью кода".
LOGIN_WITH_CODE_FRAC = (0.50, 0.74)

# Тайминги (секунды).
CONFIRM_SCREEN_WAIT = 15.0   # ожидание серверной проверки логина/пароля
CODE_SCREEN_WAIT = 1.5       # ожидание появления полей ввода кода


def _escape_keys(text):
    """Экранирует спецсимволы pywinauto.keyboard ( +^%~(){}[] )."""
    special = set("+^%~(){}[]")
    return "".join("{%s}" % ch if ch in special else ch for ch in text)


def _type_text(text):
    import pywinauto.keyboard as keyboard
    keyboard.send_keys(_escape_keys(text), pause=0.02, with_spaces=True)


def _send(keys):
    import pywinauto.keyboard as keyboard
    keyboard.send_keys(keys, pause=0.05)


def _find_steam_ui_window(timeout=90, title_contains=None):
    """Находит видимое окно Steam-UI (class SDL_app у steamwebhelper.exe)."""
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
    """Кликает по точке (доля окна) и возвращает фокус окну."""
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
    """Логинит аккаунт в десктопный клиент Steam через GUI-автоматизацию.

    Поток: закрыть Steam → запустить → "+" на экране выбора → форма логина →
    Steam Guard. Контролы CEF недоступны через UIA, поэтому клик по координатам
    + ввод с клавиатуры.
    """
    def status(text):
        if status_callback:
            status_callback(text)

    if not steam_exe or not Path(steam_exe).exists():
        raise FileNotFoundError("steam.exe не найден. Укажи путь к Steam в Настройках.")

    if restart_if_running and is_steam_running():
        status("Закрываю текущий Steam...")
        if not shutdown_steam(steam_exe):
            raise RuntimeError(
                "Не удалось закрыть запущенный Steam. Закрой его вручную и повтори."
            )

    status("Запускаю Steam...")
    try:
        subprocess.Popen([steam_exe])
    except Exception as e:
        raise RuntimeError(f"Не удалось запустить Steam: {e}")

    # 1) Ждём экран входа (экран "Кто играет?" / форма — оба class=SDL_app).
    # По имени не фильтруем: заголовок экрана выбора может отличаться от формы.
    status("Жду экран входа Steam...")
    window = _find_steam_ui_window(timeout=120)
    if window is None:
        raise RuntimeError(
            "Окно входа Steam не появилось. Возможно Steam сразу зашёл в аккаунт — "
            "сделай Steam → Сменить аккаунт и повтори."
        )
    time.sleep(1.5)  # дать CEF дорисоваться

    # 2) Клик "+" (добавить аккаунт). Если уже форма — клик по пустому месту безвреден.
    status("Открываю форму логина (+)...")
    _click_fraction(window, *PICKER_ADD_FRAC)
    time.sleep(1.5)

    # Окно могло пересоздаться — перечитываем
    window = _find_steam_ui_window(timeout=15) or window

    # 3) Заполняем форму логина
    status("Ввожу логин и пароль...")
    _fill_login_form(window, username, password)

    # 4) Экран "Подтвердите вход через моб. приложение" → жмём "Войти с помощью кода"
    status("Жду экран подтверждения...")
    time.sleep(CONFIRM_SCREEN_WAIT)  # серверная проверка логина/пароля
    window = _find_steam_ui_window(timeout=20) or window
    status("Переключаю на ввод кода...")
    _click_fraction(window, *LOGIN_WITH_CODE_FRAC)
    time.sleep(CODE_SCREEN_WAIT)

    # 5) Экран ввода Steam Guard кода
    window = _find_steam_ui_window(timeout=15) or window
    status("Получаю Steam Guard код...")
    code = guard_code_callback()
    status(f"Ввожу код {code}...")
    _type_guard_code(window, code)
    status("Код введён — проверь окно Steam")


def _fill_login_form(window, username, password):
    """Кликает по полям формы логина и печатает данные с клавиатуры."""
    # Логин
    _click_fraction(window, *FORM_USERNAME_FRAC)
    _send("^a")  # выделить всё, чтобы заменить
    time.sleep(0.1)
    _type_text(username)
    time.sleep(0.2)

    # Пароль
    _click_fraction(window, *FORM_PASSWORD_FRAC)
    _send("^a")
    time.sleep(0.1)
    _type_text(password)
    time.sleep(0.2)

    # Отправка (Enter в поле пароля). Если не сработает — клик по кнопке "Войти".
    _send("{ENTER}")
    time.sleep(0.6)


def _type_guard_code(window, code):
    """Печатает Steam Guard код. После клика 'Войти с помощью кода' первое поле
    авто-фокусируется, поэтому достаточно вывести окно на передний план и печатать."""
    code = code.strip().upper()
    if len(code) != 5:
        raise ValueError(f"Неверная длина кода: {code!r}")

    try:
        window.set_focus()
    except Exception:
        pass
    time.sleep(0.4)
    for ch in code:
        _send(ch)
        time.sleep(0.08)
