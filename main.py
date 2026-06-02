"""Steam Account Switcher —— 用于快速登录 Steam 账号的 GUI。

登录名/密码/mafile 路径保存在与 main.py 同目录的 accounts.json 中。
Steam Guard 代码可来自 mafile（TOTP）或 NebulaAuth（通过剪贴板）。
每个账号使用独立的 Chrome 配置目录，避免会话冲突。
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
from steam_client import find_steam_exe, login_steam_client


BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "accounts.json"


def load_config():
    if not CONFIG_PATH.exists():
        return {
            "accounts": [],
            "settings": {
                "chrome_profiles_dir": "chrome_profiles",
                "nebula_auth_path": "",
                "steam_exe_path": "",
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
        root.geometry("900x460")

        self.config = load_config()
        self._active_drivers = []

        main = ttk.Frame(root, padding=10)
        main.pack(fill="both", expand=True)

        cols = ("label", "login", "source", "mafile")
        self.tree = ttk.Treeview(main, columns=cols, show="headings", height=14)
        self.tree.heading("label", text="名称")
        self.tree.heading("login", text="登录名")
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
        ttk.Button(btns, text="登录（浏览器）", command=self.login_selected).pack(side="left", padx=3)
        ttk.Button(btns, text="登录客户端", command=self.login_client_selected).pack(side="left", padx=3)
        ttk.Button(btns, text="添加", command=self.add_account).pack(side="left", padx=3)
        ttk.Button(btns, text="编辑", command=self.edit_account).pack(side="left", padx=3)
        ttk.Button(btns, text="删除", command=self.delete_account).pack(side="left", padx=3)
        ttk.Button(btns, text="打开 NebulaAuth", command=self.open_nebula).pack(side="left", padx=3)
        ttk.Button(btns, text="设置", command=self.open_settings).pack(side="left", padx=3)
        ttk.Button(btns, text="刷新", command=self.refresh).pack(side="left", padx=3)

        self.status = ttk.Label(root, text="就绪", anchor="w", padding=5, relief="sunken")
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
            messagebox.showwarning("提示", "请在列表中选择账号")
            return
        threading.Thread(target=self._do_login, args=(acc,), daemon=True).start()

    def login_client_selected(self):
        acc = self.get_selected()
        if not acc:
            messagebox.showwarning("提示", "请在列表中选择账号")
            return
        threading.Thread(target=self._do_login_client, args=(acc,), daemon=True).start()

    def _build_get_code(self, acc):
        """返回账号对应的 get_code() 函数（mafile 或 nebula）。

        浏览器登录和客户端登录都会复用该函数。
        """
        source = acc.get("guard_source", "mafile")

        if source == "mafile":
            mafile_path = acc.get("mafile")
            if not mafile_path:
                raise ValueError("当 guard_source=mafile 时，必须提供 .maFile 路径")
            full_path = mafile_path if Path(mafile_path).is_absolute() else BASE_DIR / mafile_path
            if not Path(full_path).exists():
                raise FileNotFoundError(f"未找到 mafile: {full_path}")

            def get_code():
                secs = seconds_until_next_code()
                if secs < 5:
                    self.set_status(f"[{acc['label']}] 等待新验证码（{secs}秒）...")
                    time.sleep(secs + 1)
                return code_from_mafile(full_path)

            return get_code

        if source == "nebula":
            nebula_path = self.config.get("settings", {}).get("nebula_auth_path") or ""
            if nebula_path and Path(nebula_path).exists():
                self.set_status(f"[{acc['label']}] 正在打开 NebulaAuth...")
                try:
                    launch_nebula(nebula_path)
                    time.sleep(1.5)  # 窗口启动需要一点时间
                except Exception as e:
                    self.set_status(f"NebulaAuth 启动失败: {e}")

            # NebulaAuth 列表中的账号名：可单独指定，否则使用 Steam 登录名
            nebula_account = (acc.get("nebula_account_name") or "").strip() or acc["login"]

            def get_code():
                self.set_status(f"[{acc['label']}] 正在从 NebulaAuth 获取代码...")
                try:
                    return get_code_from_nebula(nebula_account, timeout=15)
                except Exception as e:
                    # 自动流程失败时，允许手动复制代码
                    self.set_status(
                        f"[{acc['label']}] 自动流程失败（{e}）。"
                        f"请手动复制代码（60秒）..."
                    )
                    return get_code_from_clipboard(timeout=60)

            return get_code

        raise ValueError(f"未知 guard_source: {source}")

    def _do_login(self, acc):
        try:
            self.set_status(f"[{acc['label']}] 准备中...")
            get_code = self._build_get_code(acc)

            profiles_root = self.config.get("settings", {}).get("chrome_profiles_dir", "chrome_profiles")
            profile = BASE_DIR / profiles_root / _safe_filename(acc["label"])

            self.set_status(f"[{acc['label']}] 正在启动 Chrome...")
            driver = make_driver(profile_dir=str(profile))
            self._active_drivers.append(driver)

            login(
                driver,
                acc["login"],
                acc["password"],
                get_code,
                status_callback=lambda t: self.set_status(f"[{acc['label']}] {t}"),
            )
            self.set_status(f"[{acc['label']}] 完成")
        except Exception as e:
            if _is_window_closed_error(e):
                self.set_status(f"[{acc['label']}] 浏览器窗口已关闭")
                return
            self.set_status(f"错误: {e}")
            messagebox.showerror("错误", f"{acc.get('label','?')}: {e}")

    def _do_login_client(self, acc):
        try:
            self.set_status(f"[{acc['label']}] 准备中（Steam 客户端）...")
            steam_exe = find_steam_exe(
                self.config.get("settings", {}).get("steam_exe_path")
            )
            if not steam_exe:
                raise FileNotFoundError(
                    "未找到 steam.exe。请在“设置”中指定 Steam 路径。"
                )

            get_code = self._build_get_code(acc)

            login_steam_client(
                steam_exe,
                acc["login"],
                acc["password"],
                get_code,
                status_callback=lambda t: self.set_status(f"[{acc['label']}] {t}"),
            )
            self.set_status(f"[{acc['label']}] 客户端登录已完成")
        except Exception as e:
            self.set_status(f"错误: {e}")
            messagebox.showerror("错误", f"{acc.get('label','?')}: {e}")

    def add_account(self):
        AccountDialog(self.root, on_save=self._on_account_saved)

    def edit_account(self):
        idx = self.get_selected_index()
        if idx is None:
            messagebox.showwarning("提示", "请选择账号")
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
        if messagebox.askyesno("删除", f"要删除账号“{acc['label']}”吗？"):
            del self.config["accounts"][idx]
            save_config(self.config)
            self.refresh()

    def open_nebula(self):
        path = self.config.get("settings", {}).get("nebula_auth_path") or ""
        if not path:
            messagebox.showinfo("NebulaAuth", "尚未设置 NebulaAuth 路径。请打开“设置”。")
            return
        try:
            launch_nebula(path)
            self.set_status("NebulaAuth 已启动")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def open_settings(self):
        SettingsDialog(self.root, self.config, on_save=self._on_settings_saved)

    def _on_settings_saved(self, settings):
        self.config["settings"] = settings
        save_config(self.config)
        self.set_status("设置已保存")


class AccountDialog:
    def __init__(self, parent, on_save, initial=None):
        self.on_save = on_save

        win = tk.Toplevel(parent)
        win.title("账号")
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
        add_row(0, "名称：", ttk.Entry(win, textvariable=self.label_var))

        self.login_var = tk.StringVar(value=initial.get("login", ""))
        add_row(1, "Steam 登录名：", ttk.Entry(win, textvariable=self.login_var))

        self.password_var = tk.StringVar(value=initial.get("password", ""))
        pwd_entry = ttk.Entry(win, textvariable=self.password_var, show="*")
        add_row(2, "密码：", pwd_entry)

        # mafile 路径 + 浏览按钮
        mafile_frame = ttk.Frame(win)
        self.mafile_var = tk.StringVar(value=initial.get("mafile") or "")
        ttk.Entry(mafile_frame, textvariable=self.mafile_var).pack(side="left", fill="x", expand=True)
        ttk.Button(mafile_frame, text="...", command=self._browse_mafile, width=3).pack(side="left", padx=3)
        add_row(3, ".maFile 路径：", mafile_frame)

        self.source_var = tk.StringVar(value=initial.get("guard_source", "mafile"))
        source_combo = ttk.Combobox(
            win,
            textvariable=self.source_var,
            values=["mafile", "nebula"],
            state="readonly",
        )
        add_row(4, "2FA 来源：", source_combo)

        self.nebula_name_var = tk.StringVar(value=initial.get("nebula_account_name") or "")
        add_row(5, "NebulaAuth 中的名称：", ttk.Entry(win, textvariable=self.nebula_name_var))

        hint = ttk.Label(
            win,
            text=(
                "mafile —— 自动生成代码。\n"
                "nebula —— 自动点击账号并复制代码。\n"
                "若 NebulaAuth 中名称与 Steam 登录名一致，此项可留空。"
            ),
            foreground="gray",
            justify="left",
        )
        hint.grid(row=6, column=0, columnspan=2, padx=10, pady=5, sticky="w")

        btns = ttk.Frame(win)
        btns.grid(row=7, column=0, columnspan=2, pady=15)
        ttk.Button(btns, text="保存", command=self._save).pack(side="left", padx=5)
        ttk.Button(btns, text="取消", command=win.destroy).pack(side="left", padx=5)

    def _browse_mafile(self):
        path = filedialog.askopenfilename(
            title="选择 .maFile",
            filetypes=[("Steam mobile authenticator", "*.maFile *.mafile"), ("所有文件", "*.*")],
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
            messagebox.showwarning("提示", "请输入名称", parent=self.win)
            return
        if not self.login_var.get().strip():
            messagebox.showwarning("提示", "请输入 Steam 登录名", parent=self.win)
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
        win.title("设置")
        win.geometry("560x230")
        win.transient(parent)
        win.grab_set()
        self.win = win

        win.columnconfigure(1, weight=1)

        ttk.Label(win, text="Chrome 配置目录：").grid(row=0, column=0, sticky="w", padx=10, pady=6)
        self.profiles_var = tk.StringVar(value=settings.get("chrome_profiles_dir", "chrome_profiles"))
        ttk.Entry(win, textvariable=self.profiles_var).grid(row=0, column=1, padx=10, pady=6, sticky="ew")

        ttk.Label(win, text="NebulaAuth.exe 路径：").grid(row=1, column=0, sticky="w", padx=10, pady=6)
        nebula_frame = ttk.Frame(win)
        self.nebula_var = tk.StringVar(value=settings.get("nebula_auth_path", ""))
        ttk.Entry(nebula_frame, textvariable=self.nebula_var).pack(side="left", fill="x", expand=True)
        ttk.Button(nebula_frame, text="...", command=self._browse_nebula, width=3).pack(side="left", padx=3)
        nebula_frame.grid(row=1, column=1, padx=10, pady=6, sticky="ew")

        ttk.Label(win, text="steam.exe 路径：").grid(row=2, column=0, sticky="w", padx=10, pady=6)
        steam_frame = ttk.Frame(win)
        self.steam_var = tk.StringVar(value=settings.get("steam_exe_path", ""))
        ttk.Entry(steam_frame, textvariable=self.steam_var).pack(side="left", fill="x", expand=True)
        ttk.Button(steam_frame, text="...", command=self._browse_steam, width=3).pack(side="left", padx=3)
        steam_frame.grid(row=2, column=1, padx=10, pady=6, sticky="ew")

        hint = ttk.Label(
            win,
            text="steam.exe 路径留空时，将在注册表和默认目录中自动查找。",
            foreground="gray",
        )
        hint.grid(row=3, column=0, columnspan=2, padx=10, pady=2, sticky="w")

        btns = ttk.Frame(win)
        btns.grid(row=4, column=0, columnspan=2, pady=15)
        ttk.Button(btns, text="保存", command=self._save).pack(side="left", padx=5)
        ttk.Button(btns, text="取消", command=win.destroy).pack(side="left", padx=5)

    def _browse_nebula(self):
        path = filedialog.askopenfilename(
            title="NebulaAuth.exe",
            filetypes=[("程序", "*.exe"), ("所有文件", "*.*")],
            parent=self.win,
        )
        if path:
            self.nebula_var.set(path)

    def _browse_steam(self):
        path = filedialog.askopenfilename(
            title="steam.exe",
            filetypes=[("程序", "*.exe"), ("所有文件", "*.*")],
            parent=self.win,
        )
        if path:
            self.steam_var.set(path)

    def _save(self):
        self.on_save({
            "chrome_profiles_dir": self.profiles_var.get().strip() or "chrome_profiles",
            "nebula_auth_path": self.nebula_var.get().strip(),
            "steam_exe_path": self.steam_var.get().strip(),
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
