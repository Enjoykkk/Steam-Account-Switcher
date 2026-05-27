"""Steam Account Switcher — GUI для быстрого логина в Steam-аккаунты.

Хранит логин/пароль/путь к mafile в accounts.json рядом с main.py.
Steam Guard код берёт либо из mafile (TOTP), либо из NebulaAuth (через буфер обмена).
Каждый аккаунт логинится в свой профиль Chrome чтобы сессии не конфликтовали.
"""

import json
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from mafile import code_from_mafile, seconds_until_next_code
from nebula import get_code_from_clipboard, get_code_from_nebula, launch_nebula
from steam_browser import _is_window_closed_error, login, make_driver


BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "accounts.json"


def load_config():
    if not CONFIG_PATH.exists():
        return {
            "accounts": [],
            "settings": {
                "chrome_profiles_dir": "chrome_profiles",
                "nebula_auth_path": "",
            },
        }
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def save_config(config):
    CONFIG_PATH.write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
    )


class App:
    def __init__(self, root):
        self.root = root
        root.title("Steam Account Switcher")
        root.geometry("780x440")

        self.config = load_config()
        self._active_drivers = []

        main = ttk.Frame(root, padding=10)
        main.pack(fill="both", expand=True)

        cols = ("label", "login", "source", "mafile")
        self.tree = ttk.Treeview(main, columns=cols, show="headings", height=14)
        self.tree.heading("label", text="Название")
        self.tree.heading("login", text="Логин")
        self.tree.heading("source", text="2FA")
        self.tree.heading("mafile", text="mafile")
        self.tree.column("label", width=160)
        self.tree.column("login", width=160)
        self.tree.column("source", width=80, anchor="center")
        self.tree.column("mafile", width=320)
        self.tree.pack(fill="both", expand=True, side="top")
        self.tree.bind("<Double-1>", lambda e: self.login_selected())

        btns = ttk.Frame(root, padding=(10, 0, 10, 5))
        btns.pack(fill="x")
        ttk.Button(btns, text="Войти", command=self.login_selected).pack(side="left", padx=3)
        ttk.Button(btns, text="Добавить", command=self.add_account).pack(side="left", padx=3)
        ttk.Button(btns, text="Изменить", command=self.edit_account).pack(side="left", padx=3)
        ttk.Button(btns, text="Удалить", command=self.delete_account).pack(side="left", padx=3)
        ttk.Button(btns, text="Открыть NebulaAuth", command=self.open_nebula).pack(side="left", padx=3)
        ttk.Button(btns, text="Настройки", command=self.open_settings).pack(side="left", padx=3)
        ttk.Button(btns, text="Обновить", command=self.refresh).pack(side="left", padx=3)

        self.status = ttk.Label(root, text="Готов", anchor="w", padding=5, relief="sunken")
        self.status.pack(fill="x", side="bottom")

        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self.config = load_config()
        for acc in self.config.get("accounts", []):
            self.tree.insert(
                "",
                "end",
                values=(
                    acc.get("label", ""),
                    acc.get("login", ""),
                    acc.get("guard_source", "mafile"),
                    acc.get("mafile", "") or "—",
                ),
            )

    def get_selected_index(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return self.tree.index(sel[0])

    def get_selected(self):
        idx = self.get_selected_index()
        if idx is None:
            return None
        return self.config["accounts"][idx]

    def set_status(self, text):
        self.status.config(text=text)
        self.root.update_idletasks()

    # ---- Account actions ----

    def login_selected(self):
        acc = self.get_selected()
        if not acc:
            messagebox.showwarning("Внимание", "Выбери аккаунт в списке")
            return
        threading.Thread(target=self._do_login, args=(acc,), daemon=True).start()

    def _do_login(self, acc):
        try:
            self.set_status(f"[{acc['label']}] подготовка...")
            source = acc.get("guard_source", "mafile")

            if source == "mafile":
                mafile_path = acc.get("mafile")
                if not mafile_path:
                    raise ValueError("Для guard_source=mafile нужно указать путь к .maFile")
                full_path = mafile_path if Path(mafile_path).is_absolute() else BASE_DIR / mafile_path
                if not Path(full_path).exists():
                    raise FileNotFoundError(f"mafile не найден: {full_path}")

                def get_code():
                    secs = seconds_until_next_code()
                    if secs < 5:
                        self.set_status(f"[{acc['label']}] жду свежий код ({secs}с)...")
                        time.sleep(secs + 1)
                    return code_from_mafile(full_path)

            elif source == "nebula":
                nebula_path = self.config.get("settings", {}).get("nebula_auth_path") or ""
                if nebula_path and Path(nebula_path).exists():
                    self.set_status(f"[{acc['label']}] открываю NebulaAuth...")
                    try:
                        launch_nebula(nebula_path)
                        time.sleep(1.5)  # окну нужно время на запуск
                    except Exception as e:
                        self.set_status(f"NebulaAuth не запустился: {e}")

                # Имя в списке NebulaAuth: можно переопределить, иначе берём логин
                nebula_account = (acc.get("nebula_account_name") or "").strip() or acc["login"]

                def get_code():
                    self.set_status(f"[{acc['label']}] забираю код из NebulaAuth...")
                    try:
                        return get_code_from_nebula(nebula_account, timeout=15)
                    except Exception as e:
                        # Если автоматика не сработала — даём шанс ручному копированию
                        self.set_status(
                            f"[{acc['label']}] автоматика не сработала ({e}). "
                            f"Скопируй код руками (60с)..."
                        )
                        return get_code_from_clipboard(timeout=60)
            else:
                raise ValueError(f"Неизвестный guard_source: {source}")

            profiles_root = self.config.get("settings", {}).get("chrome_profiles_dir", "chrome_profiles")
            profile = BASE_DIR / profiles_root / _safe_filename(acc["label"])

            self.set_status(f"[{acc['label']}] запускаю Chrome...")
            driver = make_driver(profile_dir=str(profile))
            self._active_drivers.append(driver)

            login(
                driver,
                acc["login"],
                acc["password"],
                get_code,
                status_callback=lambda t: self.set_status(f"[{acc['label']}] {t}"),
            )
            self.set_status(f"[{acc['label']}] готово")
        except Exception as e:
            if _is_window_closed_error(e):
                self.set_status(f"[{acc['label']}] окно браузера закрыто")
                return
            self.set_status(f"Ошибка: {e}")
            messagebox.showerror("Ошибка", f"{acc.get('label','?')}: {e}")

    def add_account(self):
        AccountDialog(self.root, on_save=self._on_account_saved)

    def edit_account(self):
        idx = self.get_selected_index()
        if idx is None:
            messagebox.showwarning("Внимание", "Выбери аккаунт")
            return
        AccountDialog(
            self.root,
            on_save=lambda data: self._on_account_saved(data, replace_index=idx),
            initial=self.config["accounts"][idx],
        )

    def _on_account_saved(self, data, replace_index=None):
        if replace_index is None:
            self.config.setdefault("accounts", []).append(data)
        else:
            self.config["accounts"][replace_index] = data
        save_config(self.config)
        self.refresh()

    def delete_account(self):
        idx = self.get_selected_index()
        if idx is None:
            return
        acc = self.config["accounts"][idx]
        if messagebox.askyesno("Удалить", f"Удалить аккаунт '{acc['label']}'?"):
            del self.config["accounts"][idx]
            save_config(self.config)
            self.refresh()

    def open_nebula(self):
        path = self.config.get("settings", {}).get("nebula_auth_path") or ""
        if not path:
            messagebox.showinfo("NebulaAuth", "Путь к NebulaAuth не задан. Открой 'Настройки'.")
            return
        try:
            launch_nebula(path)
            self.set_status("NebulaAuth запущен")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def open_settings(self):
        SettingsDialog(self.root, self.config, on_save=self._on_settings_saved)

    def _on_settings_saved(self, settings):
        self.config["settings"] = settings
        save_config(self.config)
        self.set_status("Настройки сохранены")


class AccountDialog:
    def __init__(self, parent, on_save, initial=None):
        self.on_save = on_save

        win = tk.Toplevel(parent)
        win.title("Аккаунт")
        win.geometry("520x380")
        win.transient(parent)
        win.grab_set()
        self.win = win

        initial = initial or {}

        def add_row(row, label, widget):
            ttk.Label(win, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=6)
            widget.grid(row=row, column=1, padx=10, pady=6, sticky="ew")

        win.columnconfigure(1, weight=1)

        self.label_var = tk.StringVar(value=initial.get("label", ""))
        add_row(0, "Название:", ttk.Entry(win, textvariable=self.label_var))

        self.login_var = tk.StringVar(value=initial.get("login", ""))
        add_row(1, "Логин Steam:", ttk.Entry(win, textvariable=self.login_var))

        self.password_var = tk.StringVar(value=initial.get("password", ""))
        pwd_entry = ttk.Entry(win, textvariable=self.password_var, show="*")
        add_row(2, "Пароль:", pwd_entry)

        # mafile с кнопкой обзора
        mafile_frame = ttk.Frame(win)
        self.mafile_var = tk.StringVar(value=initial.get("mafile") or "")
        ttk.Entry(mafile_frame, textvariable=self.mafile_var).pack(side="left", fill="x", expand=True)
        ttk.Button(mafile_frame, text="...", command=self._browse_mafile, width=3).pack(side="left", padx=3)
        add_row(3, "Путь к .maFile:", mafile_frame)

        self.source_var = tk.StringVar(value=initial.get("guard_source", "mafile"))
        source_combo = ttk.Combobox(
            win,
            textvariable=self.source_var,
            values=["mafile", "nebula"],
            state="readonly",
        )
        add_row(4, "Источник 2FA:", source_combo)

        self.nebula_name_var = tk.StringVar(value=initial.get("nebula_account_name") or "")
        add_row(5, "Имя в NebulaAuth:", ttk.Entry(win, textvariable=self.nebula_name_var))

        hint = ttk.Label(
            win,
            text=(
                "mafile — код генерируется автоматически.\n"
                "nebula — клик по аккаунту и коду делается автоматом.\n"
                "Имя в NebulaAuth — оставь пустым если совпадает с логином Steam."
            ),
            foreground="gray",
            justify="left",
        )
        hint.grid(row=6, column=0, columnspan=2, padx=10, pady=5, sticky="w")

        btns = ttk.Frame(win)
        btns.grid(row=7, column=0, columnspan=2, pady=15)
        ttk.Button(btns, text="Сохранить", command=self._save).pack(side="left", padx=5)
        ttk.Button(btns, text="Отмена", command=win.destroy).pack(side="left", padx=5)

    def _browse_mafile(self):
        path = filedialog.askopenfilename(
            title="Выбери .maFile",
            filetypes=[("Steam mobile authenticator", "*.maFile *.mafile"), ("Все файлы", "*.*")],
            parent=self.win,
        )
        if not path:
            return
        try:
            rel = Path(path).relative_to(BASE_DIR)
            self.mafile_var.set(str(rel).replace("\\", "/"))
        except ValueError:
            self.mafile_var.set(path)

    def _save(self):
        if not self.label_var.get().strip():
            messagebox.showwarning("Внимание", "Введи название", parent=self.win)
            return
        if not self.login_var.get().strip():
            messagebox.showwarning("Внимание", "Введи логин Steam", parent=self.win)
            return
        data = {
            "label": self.label_var.get().strip(),
            "login": self.login_var.get().strip(),
            "password": self.password_var.get(),
            "mafile": self.mafile_var.get().strip() or None,
            "guard_source": self.source_var.get(),
            "nebula_account_name": self.nebula_name_var.get().strip() or None,
        }
        self.on_save(data)
        self.win.destroy()


class SettingsDialog:
    def __init__(self, parent, config, on_save):
        self.on_save = on_save
        settings = config.get("settings", {})

        win = tk.Toplevel(parent)
        win.title("Настройки")
        win.geometry("560x180")
        win.transient(parent)
        win.grab_set()
        self.win = win

        win.columnconfigure(1, weight=1)

        ttk.Label(win, text="Папка профилей Chrome:").grid(row=0, column=0, sticky="w", padx=10, pady=6)
        self.profiles_var = tk.StringVar(value=settings.get("chrome_profiles_dir", "chrome_profiles"))
        ttk.Entry(win, textvariable=self.profiles_var).grid(row=0, column=1, padx=10, pady=6, sticky="ew")

        ttk.Label(win, text="Путь к NebulaAuth.exe:").grid(row=1, column=0, sticky="w", padx=10, pady=6)
        nebula_frame = ttk.Frame(win)
        self.nebula_var = tk.StringVar(value=settings.get("nebula_auth_path", ""))
        ttk.Entry(nebula_frame, textvariable=self.nebula_var).pack(side="left", fill="x", expand=True)
        ttk.Button(nebula_frame, text="...", command=self._browse_nebula, width=3).pack(side="left", padx=3)
        nebula_frame.grid(row=1, column=1, padx=10, pady=6, sticky="ew")

        btns = ttk.Frame(win)
        btns.grid(row=2, column=0, columnspan=2, pady=15)
        ttk.Button(btns, text="Сохранить", command=self._save).pack(side="left", padx=5)
        ttk.Button(btns, text="Отмена", command=win.destroy).pack(side="left", padx=5)

    def _browse_nebula(self):
        path = filedialog.askopenfilename(
            title="NebulaAuth.exe",
            filetypes=[("Программы", "*.exe"), ("Все файлы", "*.*")],
            parent=self.win,
        )
        if path:
            self.nebula_var.set(path)

    def _save(self):
        self.on_save({
            "chrome_profiles_dir": self.profiles_var.get().strip() or "chrome_profiles",
            "nebula_auth_path": self.nebula_var.get().strip(),
        })
        self.win.destroy()


def _safe_filename(text):
    bad = '<>:"/\\|?*'
    return "".join("_" if c in bad else c for c in text).strip() or "default"


def main():
    if not CONFIG_PATH.exists():
        save_config(load_config())
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
