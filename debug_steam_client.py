import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import steam_client as sc  # noqa: E402

OUT_PATH = Path(__file__).parent / "steam_dump.txt"
_lines = []


def out(text=""):
    print(text)
    _lines.append(str(text))


def _safe(fn, default=""):
    try:
        return fn()
    except Exception:
        return default


def dump_window(w, max_items=800):
    rect = _safe(lambda: w.rectangle(), None)
    out("=" * 78)
    out(f"WINDOW title={_safe(lambda: w.window_text())!r} "
        f"class={_safe(lambda: w.class_name())!r} pid={_safe(lambda: w.process_id())} rect={rect}")
    out("-" * 78)

    try:
        descendants = w.descendants()
    except Exception as e:
        out(f"  !! не удалось получить descendants: {e}")
        return

    count = 0
    for el in descendants:
        try:
            info = el.element_info
            ct = _safe(lambda: info.control_type)
            name = _safe(lambda: el.window_text())
            aid = _safe(lambda: info.automation_id)
            r = _safe(lambda: el.rectangle(), None)
            visible = _safe(lambda: el.is_visible(), None)

            interesting = ("Edit", "Button", "Hyperlink", "Text", "CheckBox",
                           "ComboBox", "Document", "Group", "Custom", "Image", "Pane")
            if not name and ct not in interesting:
                continue

            coords = f"({r.left},{r.top} {r.width()}x{r.height()})" if r else "?"
            out(f"  [{ct:10}] vis={visible} name={name!r:42} id={aid!r} {coords}")
            count += 1
            if count >= max_items:
                out("  ...(обрезано)")
                break
        except Exception:
            continue

    out(f"-- всего показано контролов: {count} --")
    out("")


def main():
    out(f"steam.exe       : {sc.find_steam_exe()}")
    out(f"steam.exe pids  : {sc._steam_pids()}")
    out(f"all steam pids  : {sc._all_steam_pids()}")
    out("")

    pids = sc._all_steam_pids()
    if not pids:
        out("Steam не запущен — запусти его и открой нужный экран, потом повтори.")
        _flush()
        return

    try:
        from pywinauto import Desktop
    except ImportError:
        out("pywinauto не установлен: pip install pywinauto")
        _flush()
        return

    name_map = sc._pid_name_map()

    found = 0
    for w in Desktop(backend="uia").windows():
        try:
            wpid = w.process_id()
            if wpid not in pids or not w.is_visible():
                continue
            found += 1
            pname = name_map.get(wpid, "?")
            out(f">>> Окно процесса {pname} (pid={wpid}):")
            dump_window(w)
        except Exception:
            continue

    if not found:
        out("Окон процессов Steam (steam.exe/steamwebhelper.exe) не найдено среди видимых.")
        out("Перечисляю ВСЕ видимые окна верхнего уровня (для поиска UI Steam):\n")
        for w in Desktop(backend="uia").windows():
            try:
                if not w.is_visible():
                    continue
                wpid = w.process_id()
                pname = name_map.get(wpid, "?")
                rect = _safe(lambda: w.rectangle(), None)
                out(f"  pid={wpid} proc={pname!r:25} title={_safe(lambda: w.window_text())!r} "
                    f"class={_safe(lambda: w.class_name())!r} rect={rect}")
            except Exception:
                continue

    _flush()


def _flush():
    try:
        OUT_PATH.write_text("\n".join(_lines), encoding="utf-8")
        print(f"\n[Результат записан в {OUT_PATH}]")
    except Exception as e:
        print(f"Не удалось записать файл: {e}")


if __name__ == "__main__":
    main()
