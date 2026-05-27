"""Интеграция с NebulaAuth: запуск приложения, автоматический клик по аккаунту,
копирование Steam Guard кода и чтение его из буфера обмена."""

import subprocess
import time
from pathlib import Path

import pyperclip


VALID_CHARS = set("23456789BCDFGHJKMNPQRTVWXY")
NEBULA_WINDOW_TITLE_RE = r"^NebulaAuth.*"


def launch_nebula(exe_path):
    path = Path(exe_path)
    if not path.exists():
        raise FileNotFoundError(f"NebulaAuth не найден: {exe_path}")
    subprocess.Popen([str(path)])


def _looks_like_guard_code(text):
    stripped = text.strip().upper()
    if len(stripped) != 5:
        return False
    return all(c in VALID_CHARS for c in stripped)


def get_code_from_clipboard(timeout=60):
    """Ждём пока пользователь скопирует Steam Guard код в буфер из NebulaAuth.

    Если код уже в буфере к моменту вызова — используем сразу. Иначе чистим буфер
    и ждём новое 5-символьное значение.
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
        "Steam Guard код не появился в буфере. "
        "Открой NebulaAuth и нажми на код чтобы скопировать его."
    )


def _find_nebula_window(timeout=5):
    """Возвращает окно NebulaAuth (pywinauto WindowSpecification) или None."""
    from pywinauto import Desktop  # ленивый импорт — pywinauto тяжёлый

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
    """Итератор по всем потомкам окна. Защищён от исключений pywinauto."""
    try:
        for el in window.descendants():
            yield el
    except Exception:
        return


def _element_text(el):
    """Безопасно достаёт текст элемента."""
    try:
        return (el.window_text() or "").strip()
    except Exception:
        return ""


def get_code_from_nebula(account_name, timeout=15):
    """Автоматически кликает по аккаунту в NebulaAuth и забирает код в буфер.

    account_name — логин аккаунта как он отображается в списке NebulaAuth.
    Поддерживается префиксное совпадение (NebulaAuth обрезает длинные имена).
    """
    window = _find_nebula_window(timeout=5)
    if window is None:
        raise RuntimeError(
            "Окно NebulaAuth не найдено. Запусти NebulaAuth заранее или "
            "укажи путь к exe в настройках."
        )

    try:
        window.set_focus()
    except Exception:
        pass

    account_lc = account_name.lower()

    # 1) Ищем строку аккаунта в списке. NebulaAuth может обрезать длинные имена,
    # поэтому учитываем и обратное направление префикса.
    deadline = time.time() + timeout
    account_el = None
    while time.time() < deadline:
        for el in _iter_descendants(window):
            text = _element_text(el)
            if not text or len(text) > 80:
                continue
            tl = text.lower().rstrip(".")  # NebulaAuth добавляет "..." к обрезанным
            if tl.startswith(account_lc) or account_lc.startswith(tl):
                account_el = el
                break
        if account_el:
            break
        time.sleep(0.3)

    if account_el is None:
        raise RuntimeError(
            f"Аккаунт '{account_name}' не найден в списке NebulaAuth. "
            f"Сверь точное имя в окне NebulaAuth."
        )

    # Чистим буфер чтобы потом гарантированно прочитать свежий код
    try:
        pyperclip.copy("")
    except Exception:
        pass

    try:
        account_el.click_input()
    except Exception as e:
        raise RuntimeError(f"Не удалось кликнуть по аккаунту в NebulaAuth: {e}")

    # 2) Ждём пока в правой панели появится 5-символьный код
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
            "Не нашёл Steam Guard код в окне NebulaAuth после выбора аккаунта."
        )

    # 3) Клик по коду — NebulaAuth копирует его в буфер
    try:
        code_el.click_input()
    except Exception as e:
        raise RuntimeError(f"Не удалось кликнуть по коду в NebulaAuth: {e}")

    # 4) Читаем код из буфера (с небольшим ретраем — клик не моментальный)
    deadline = time.time() + 3
    while time.time() < deadline:
        clip = pyperclip.paste()
        stripped = (clip or "").strip().upper()
        if len(stripped) == 5 and all(c in VALID_CHARS for c in stripped):
            return stripped
        time.sleep(0.1)

    raise RuntimeError(
        "После клика по коду буфер не получил валидное значение. "
        f"Текущее содержимое буфера: {pyperclip.paste()!r}"
    )
