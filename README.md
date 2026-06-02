# Steam Account Switcher

🇨🇳 简体中文 | [🇬🇧 English](README_EN.md)

一个用于快速切换不同 Steam 账号的本地工具。程序会自动在浏览器中填写登录名/密码，获取 Steam Guard 验证码（来自 `.maFile` 或 NebulaAuth），并完成 Steam 登录。每个账号使用独立的 Chrome 配置目录，避免会话互相影响。

---

## 功能特性

- **基于 tkinter 的 GUI** —— 账号列表，双击即可登录。
- **两种登录方式：**
  - **登录（浏览器）** —— 通过自动化 Chrome 登录 Steam 网站。
  - **登录客户端** —— 登录 Steam 桌面客户端：程序会关闭当前 Steam，重新启动并自动输入 Steam Guard 验证码。
- **两种 2FA 验证码来源：**
  - `mafile` —— 程序会从 `.maFile` 的 `shared_secret` 自动生成 Steam Guard 验证码（与 NebulaAuth/SDA 使用相同 TOTP 算法）。
  - `nebula` —— 程序通过 Windows UI Automation 自动定位 NebulaAuth 窗口，点击对应账号并点击验证码，将其复制到剪贴板后自动填入 Steam 表单。
- **隔离的 Chrome 配置目录** —— 每个账号独立使用 `chrome_profiles/<名称>`，Steam 会话互不冲突。
- **自动点击“Enter a code instead”** —— 当 Steam 显示“通过手机应用确认”页面时，程序会自动点击切换到验证码输入（通过兼容 React 的鼠标事件模拟）。
- **优雅退出** —— 如果你手动关闭 Chrome 窗口，程序不会报错崩溃，而是静默更新状态栏。
- **桌面快捷方式** —— 通过 `pythonw.exe` 启动 GUI，无黑色控制台窗口。

---

## 项目结构

```
E:\proj1\
├── main.py                # GUI（入口）
├── mafile.py              # .maFile 解析 + TOTP 生成
├── nebula.py              # 启动 NebulaAuth、自动点击、读取剪贴板
├── steam_browser.py       # Selenium 驱动的 Chrome 自动化
├── debug_enter_code.py    # Steam UI 问题排查脚本
├── create_shortcut.ps1    # 在桌面创建“Steam Switcher”快捷方式
├── requirements.txt       # Python 依赖
├── accounts.example.json  # 配置示例
├── accounts.json          # 实际配置（自动创建）
├── icon.ico               # 快捷方式图标
├── mafiles/               # 放置你的 .maFile 文件
└── chrome_profiles/       # 自动创建，每个账号独立 Chrome 配置
```

---

## 环境要求

- **Python 3.10+**（在 3.14 上测试过）。
- **Google Chrome**（任意较新版本；Selenium Manager 会自动下载兼容的 chromedriver）。
- **Windows 10/11** —— 与 NebulaAuth 的 `pywinauto` 集成仅支持 Windows。
- **NebulaAuth**（可选）—— 仅在使用 `guard_source: nebula` 时需要。

> **NebulaAuth** 是 achies 开发的第三方应用。
> 本项目不包含、也不分发 NebulaAuth，仅通过 Windows UI Automation API 和剪贴板与其交互。

---

## 安装

### 1. 下载项目

前往 [Releases](https://github.com/alabaster246/Steam-Account-Switcher/releases/latest) 页面，下载 `Steam.Account.Switcher.zip`，解压到任意目录（例如 `E:\proj1\`）。

或使用 git 克隆仓库：
```powershell
git clone https://github.com/alabaster246/Steam-Account-Switcher.git E:\proj1
```

### 2. 安装 Python 和依赖

确认已安装 **Python 3.10+**（[python.org](https://python.org/downloads)）。
然后安装依赖：
```powershell
pip install -r E:\proj1\requirements.txt
```

### 3. 创建桌面快捷方式

运行 PowerShell 脚本，它会在桌面创建 **Steam Switcher** 快捷方式，启动程序时不显示黑色控制台窗口：
```powershell
powershell -ExecutionPolicy Bypass -File E:\proj1\create_shortcut.ps1
```

或者直接运行程序：
```powershell
python E:\proj1\main.py
```

---

## 首次运行

1. 运行 `python E:\proj1\main.py`（或通过快捷方式）。
2. 首次启动会自动创建空的 `accounts.json`。
3. 点击 **设置**，如果计划使用 nebula 模式，请填写 `NebulaAuth.exe` 路径。
4. 点击 **添加** 并填写：
   - **名称** —— 列表中显示的标签。
   - **Steam 登录名** —— 你的 Steam 账号。
   - **密码** —— Steam 密码。
   - **`.maFile` 路径** —— 可用 `...` 按钮选择；`mafile` 模式必填。
   - **2FA 来源** —— `mafile` 或 `nebula`。
   - **NebulaAuth 中的名称** —— 仅 `nebula` 模式使用；当 NebulaAuth 列表名称与 Steam 登录名不一致时填写，否则留空。
5. 在列表中双击账号即可登录。

---

## `accounts.json` 格式

```json
{
  "accounts": [
    {
      "label": "主号",
      "login": "my_steam_login",
      "password": "my_password",
      "mafile": "mafiles/main.maFile",
      "guard_source": "mafile",
      "nebula_account_name": null
    },
    {
      "label": "交易号",
      "login": "trader_login",
      "password": "trader_password",
      "mafile": null,
      "guard_source": "nebula",
      "nebula_account_name": null
    }
  ],
  "settings": {
    "chrome_profiles_dir": "chrome_profiles",
    "nebula_auth_path": "C:\\Program Files\\NebulaAuth\\NebulaAuth.exe",
    "steam_exe_path": ""
  }
}
```

### 账号字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `label` | string | 程序列表中的显示名称 |
| `login` | string | Steam 登录名 |
| `password` | string | Steam 密码（明文存储！） |
| `mafile` | string \| null | `.maFile` 路径（绝对路径或相对 `main.py`） |
| `guard_source` | `"mafile"` \| `"nebula"` | Steam Guard 验证码来源 |
| `nebula_account_name` | string \| null | NebulaAuth 列表中的账号名；`null` 时使用 `login` |

### 设置字段

| 字段 | 说明 |
| --- | --- |
| `chrome_profiles_dir` | Chrome 配置目录（默认 `chrome_profiles`） |
| `nebula_auth_path` | `NebulaAuth.exe` 完整路径 |
| `steam_exe_path` | `steam.exe` 路径；留空则通过注册表和默认目录自动查找 |

---

## 工作原理

### `mafile` 模式

1. 程序读取 `.maFile` 并提取 `shared_secret`。
2. 基于当前时间计算 TOTP（HMAC-SHA1 + Steam Guard 字符集 `23456789BCDFGHJKMNPQRTVWXY`）。
3. 如果距离验证码轮换不足 5 秒，会等待下一个验证码，避免输入时过期。
4. 将验证码填入 Steam 页面。

### `nebula` 模式

1. 启动 `NebulaAuth.exe`（如果设置中配置了路径）。
2. 通过 `pywinauto`（UI Automation）定位 `NebulaAuth*` 窗口。
3. 在左侧列表按名称前缀匹配账号（兼容 `...` 截断）。
4. 点击账号，等待右侧出现 5 位验证码。
5. 点击验证码，NebulaAuth 会复制到剪贴板。
6. 程序读取剪贴板并填入 Steam。

如果自动化失败（例如 NebulaAuth 界面发生变化），会回退到手动流程：程序提示你在 60 秒内手动复制验证码，并从剪贴板读取。

### 浏览器部分

- Selenium 4.6+ 会通过 Selenium Manager 自动下载兼容 chromedriver。
- 每个账号使用独立 `--user-data-dir`。
- 启动前会清理配置目录中的 `SingletonLock`（避免上次 Chrome 崩溃导致锁残留）。
- 使用 `--disable-blink-features=AutomationControlled` 等参数降低自动化检测风险。
- `detach=True`：程序结束后 Chrome 保持打开。

---

## 安全说明

**重要：** 密码以明文保存在 `accounts.json`。这是为了本地使用便捷而做的取舍。因此请注意：

- 不要在公共电脑上保留 `accounts.json`。
- 不要把 `accounts.json`、`mafiles/`、`chrome_profiles/` 提交到 git。
- 如果电脑多人共用，建议改造配置模块，改为带主密码的加密存储。

推荐 `.gitignore`：

```
accounts.json
mafiles/
chrome_profiles/
__pycache__/
*.pyc
```

---

## 常见问题

### `Chrome instance exited`
可能是 chromedriver 缓存过旧，清理 Selenium Manager 缓存：
```powershell
Remove-Item "$env:LOCALAPPDATA\.cache\selenium" -Recurse -Force
```

### `No such element: //input[@type='password']`
说明 Steam 登录表单结构发生变化。运行 `debug_enter_code.py` 并提供输出，以便更新选择器。

### `未找到 NebulaAuth 窗口`
- NebulaAuth 未启动。请在设置中填写 `nebula_auth_path`，或在点击“登录”前手动打开 NebulaAuth。
- 窗口最小化到了托盘，请从托盘恢复。

### `在 NebulaAuth 列表中未找到账号 '<name>'`
NebulaAuth 中的名称与 Steam 登录名不一致。请通过“编辑”打开账号并填写 **NebulaAuth 中的名称** 为列表中的实际名称。

### 登录时出现 `Captcha`
Steam 在怀疑自动化时可能出现验证码。浏览器窗口会保持打开——手动完成验证码后，脚本会继续输入 Steam Guard 代码。

### 快捷方式图标不更新
这是 Explorer 缓存问题。运行 `ie4uinit.exe -show` 或重新登录系统。

---

## 依赖

| 包 | 用途 |
| --- | --- |
| `selenium` | Chrome 自动化 |
| `pyperclip` | NebulaAuth 集成所需的剪贴板读写 |
| `pywinauto` | NebulaAuth 集成所需的 UI Automation |

`tkinter` 属于 Python 标准库，无需额外安装。

---

## 许可证

个人项目，请自行承担使用风险。程序仅处理你自己的 Steam 账号，以及你通过 Steam Mobile Authenticator / NebulaAuth 生成的 `.maFile` 文件。
