# Steam Account Switcher

🇷🇺 Русский | [🇬🇧 English](README_EN.md)

Локальная утилита для быстрого входа в разные Steam-аккаунты. Программа сама
заполняет логин/пароль в браузере, забирает Steam Guard код (из `.maFile` или
из NebulaAuth) и логинит тебя на странице Steam. Каждый аккаунт открывается в
своём профиле Chrome, чтобы сессии не пересекались.

---

## Возможности

- **GUI на tkinter** — список аккаунтов, двойной клик = вход.
- **Два способа входа:**
  - **Войти (браузер)** — логин на сайте Steam через автоматизированный Chrome.
  - **Войти в клиент** — вход в десктопный клиент Steam: программа закрывает
    текущий Steam, запускает его с `-login` (минуя экран "Кто играет?" и форму)
    и автоматически вводит Steam Guard код.
- **Два источника 2FA-кодов:**
  - `mafile` — программа сама генерирует Steam Guard код из `shared_secret`
    внутри `.maFile` (тот же TOTP-алгоритм, что и в NebulaAuth/SDA).
  - `nebula` — программа автоматически находит окно NebulaAuth через Windows
    UI Automation, кликает по нужному аккаунту в списке, кликает по коду —
    код попадает в буфер обмена и подставляется в форму Steam.
- **Изолированные профили Chrome** — каждому аккаунту своя папка
  `chrome_profiles/<название>`, сессии Steam не конфликтуют.
- **Авто-клик "Enter a code instead"** — если Steam показывает экран
  подтверждения через мобильное приложение, программа сама кликает ссылку
  для ввода кода (через React-совместимую эмуляцию событий мыши).
- **Корректное завершение** — если ты закроешь окно Chrome руками, программа
  не падает с ошибкой, а тихо пишет в статус-бар.
- **Ярлык на рабочем столе** — запуск GUI без чёрной консоли через `pythonw.exe`.

---

## Структура проекта

```
E:\proj1\
├── main.py                # GUI (точка входа)
├── mafile.py              # парсинг .maFile + TOTP-генерация
├── nebula.py              # запуск NebulaAuth, авто-клик, чтение буфера
├── steam_browser.py       # автоматизация Chrome через Selenium
├── debug_enter_code.py    # отладочный скрипт для проблем с UI Steam
├── create_shortcut.ps1    # создаёт ярлык "Steam Switcher" на рабочем столе
├── requirements.txt       # зависимости Python
├── accounts.example.json  # пример конфига
├── accounts.json          # реальный конфиг (создаётся автоматически)
├── icon.ico               # иконка ярлыка
├── mafiles/               # сюда положи свои .maFile
└── chrome_profiles/       # авто-создаётся, профили Chrome по аккаунтам
```

---

## Требования

- **Python 3.10+** (тестировалось на 3.14).
- **Google Chrome** (любая свежая версия; Selenium Manager сам качает совместимый chromedriver).
- **Windows 10/11** — `pywinauto` для интеграции с NebulaAuth работает только на Windows.
- **NebulaAuth** (опционально) — нужен только если используешь `guard_source: nebula`.

> **NebulaAuth** — стороннее приложение от achies.
> Этот проект не включает и не распространяет NebulaAuth — только автоматизирует
> взаимодействие с ним через Windows UI Automation API и буфер обмена.

---

## Установка

### 1. Скачать проект

Перейди на страницу [Releases](https://github.com/alabaster246/Steam-Account-Switcher/releases/latest),
скачай архив `Steam.Account.Switcher.zip`, распакуй в любую папку (например `E:\proj1\`).

Либо клонируй репозиторий через git:
```powershell
git clone https://github.com/alabaster246/Steam-Account-Switcher.git E:\proj1
```

### 2. Установить Python и зависимости

Убедись что установлен **Python 3.10+** ([python.org](https://python.org/downloads)).
Затем установи зависимости:
```powershell
pip install -r E:\proj1\requirements.txt
```

### 3. Создать ярлык на рабочем столе

Запусти PowerShell-скрипт — он создаст ярлык **Steam Switcher** на рабочем столе,
который запускает программу без чёрного окна консоли:
```powershell
powershell -ExecutionPolicy Bypass -File E:\proj1\create_shortcut.ps1
```

Или запускай программу напрямую:
```powershell
python E:\proj1\main.py
```

---

## Первый запуск

1. Запусти `python E:\proj1\main.py` (или через ярлык).
2. При первом старте создастся пустой `accounts.json`.
3. Нажми **Настройки** → укажи путь к `NebulaAuth.exe` если планируешь
   использовать nebula-режим.
4. Нажми **Добавить** → заполни поля:
   - **Название** — отображается в списке (любая метка).
   - **Логин Steam** — твой Steam-аккаунт.
   - **Пароль** — пароль от Steam.
   - **Путь к `.maFile`** — кнопка `...` для выбора файла. Нужен для режима `mafile`.
   - **Источник 2FA** — `mafile` или `nebula`.
   - **Имя в NebulaAuth** — только для `nebula`-режима, если имя в списке
     NebulaAuth отличается от логина Steam. Иначе оставь пустым.
5. Двойной клик по аккаунту в списке = вход.

---

## Формат `accounts.json`

```json
{
  "accounts": [
    {
      "label": "Основной",
      "login": "my_steam_login",
      "password": "my_password",
      "mafile": "mafiles/main.maFile",
      "guard_source": "mafile",
      "nebula_account_name": null
    },
    {
      "label": "Торговый",
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

### Поля аккаунта

| Поле | Тип | Описание |
| --- | --- | --- |
| `label` | string | Отображаемое имя в списке программы |
| `login` | string | Логин Steam |
| `password` | string | Пароль Steam (хранится открытым текстом!) |
| `mafile` | string \| null | Путь к `.maFile` (абсолютный или относительно `main.py`) |
| `guard_source` | `"mafile"` \| `"nebula"` | Откуда брать Steam Guard код |
| `nebula_account_name` | string \| null | Имя аккаунта как видно в списке NebulaAuth. `null` → используется `login` |

### Настройки

| Поле | Описание |
| --- | --- |
| `chrome_profiles_dir` | Папка для профилей Chrome (по умолчанию `chrome_profiles`) |
| `nebula_auth_path` | Полный путь к `NebulaAuth.exe` |
| `steam_exe_path` | Путь к `steam.exe`. Пусто → авто-поиск через реестр и стандартные папки |

---

## Как это работает

### Режим `mafile`

1. Программа открывает `.maFile`, извлекает `shared_secret`.
2. Считает TOTP-код по текущему времени (HMAC-SHA1 + кодировка Steam Guard
   из символов `23456789BCDFGHJKMNPQRTVWXY`).
3. Если до смены кода осталось меньше 5 секунд — ждёт следующий, чтобы код
   не протух пока вводится.
4. Подставляет код в поля Steam.

### Режим `nebula`

1. Запускает `NebulaAuth.exe` (если указан путь в настройках).
2. Через `pywinauto` (UI Automation) находит окно `NebulaAuth*`.
3. Ищет в левом списке аккаунт по префиксу имени (учитывая обрезание `...`).
4. Кликает по аккаунту → ждёт появления 5-символьного кода справа.
5. Кликает по коду → NebulaAuth копирует его в буфер обмена.
6. Программа читает буфер и подставляет код в Steam.

Если автоматика проваливается (например, изменился интерфейс NebulaAuth),
есть fallback: программа просит тебя скопировать код руками в течение 60
секунд, и поймает его из буфера.

### Браузер

- Selenium 4.6+ сам качает совместимый chromedriver через Selenium Manager.
- Каждый аккаунт открывается с отдельным `--user-data-dir`.
- Перед запуском чистится `SingletonLock` из папки профиля (на случай если
  предыдущий Chrome упал).
- Флаги `--disable-blink-features=AutomationControlled` и пр. маскируют
  Selenium от детектора автоматизации Steam.
- `detach=True` — Chrome не закрывается когда программа закончит работу с ним.

---

## Безопасность

**ВАЖНО:** пароли хранятся в `accounts.json` открытым текстом. Это
сознательное решение (простота локального использования). Соответственно:

- Не оставляй `accounts.json` на общедоступном ПК.
- Не коммить `accounts.json`, `mafiles/`, `chrome_profiles/` в git.
- Если ПК делишь — стоит переписать модуль конфига на зашифрованное
  хранилище с мастер-паролем.

`.gitignore` (если решишь добавить версионирование):

```
accounts.json
mafiles/
chrome_profiles/
__pycache__/
*.pyc
```

---

## Решение проблем

### `Chrome instance exited`
Старая версия chromedriver. Очисти кеш Selenium Manager:
```powershell
Remove-Item "$env:LOCALAPPDATA\.cache\selenium" -Recurse -Force
```

### `No such element: //input[@type='password']`
Steam изменил вёрстку формы. Запусти `debug_enter_code.py` и пришли вывод —
обновлю селекторы.

### `Окно NebulaAuth не найдено`
- NebulaAuth не запущен. Укажи `nebula_auth_path` в настройках, либо
  открой NebulaAuth до нажатия "Войти".
- Окно скрыто в трей. Восстанови из трея.

### `Аккаунт '<name>' не найден в списке NebulaAuth`
Имя в NebulaAuth отличается от Steam-логина. Открой аккаунт через
«Изменить» и заполни поле **Имя в NebulaAuth** тем, что видно в списке.

### `Captcha` при логине
Steam иногда показывает капчу при подозрении на бота. Окно браузера
остаётся открытым — реши капчу руками, дальше скрипт продолжит ввод кода.

### Иконка ярлыка не обновляется
Кеш Explorer. Запусти `ie4uinit.exe -show` или перезайди в систему.

---

## Зависимости

| Пакет | Зачем |
| --- | --- |
| `selenium` | Автоматизация Chrome |
| `pyperclip` | Чтение/запись буфера обмена для NebulaAuth |
| `pywinauto` | UI Automation для интеграции с NebulaAuth |

`tkinter` — стандартная библиотека Python, ставить не нужно.

---

## Лицензия

Личный pet-project, используй на свой страх и риск. Программа работает с
твоими собственными Steam-аккаунтами и `.maFile`, которые ты сам создал
через Steam Mobile Authenticator / NebulaAuth.
