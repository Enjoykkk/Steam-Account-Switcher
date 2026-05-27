"""Запусти этот скрипт, дойди руками до экрана 'Use the Steam Mobile App',
останови программу клавишей Enter в консоли — она напечатает HTML
ссылки 'Enter a code instead'. Скинь вывод, пойму почему она не кликается."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from steam_browser import make_driver  # noqa: E402

driver = make_driver(profile_dir=str(Path(__file__).parent / "chrome_profiles" / "_debug"))
driver.get("https://store.steampowered.com/login/")

print()
print("=" * 70)
print("1. Введи логин и пароль в окне Chrome")
print("2. Дождись экрана с 'Use the Steam Mobile App to confirm your sign in'")
print("3. Вернись сюда и нажми Enter")
print("=" * 70)
input()

js = r"""
const phrases = ['enter a code', 'введите код', 'ввести код'];

function directText(el) {
    let s = '';
    for (const n of el.childNodes) {
        if (n.nodeType === 3) s += n.textContent || '';
    }
    return s.trim();
}

const results = [];
const all = document.querySelectorAll('*');
for (const el of all) {
    const t = directText(el).toLowerCase();
    if (!t || t.length > 100) continue;
    if (!phrases.some(p => t.includes(p))) continue;
    const rect = el.getBoundingClientRect();
    results.push({
        tag: el.tagName,
        text: directText(el),
        outerHTML: el.outerHTML.slice(0, 500),
        parentHTML: el.parentElement ? el.parentElement.outerHTML.slice(0, 500) : null,
        rect: {w: rect.width, h: rect.height, x: rect.x, y: rect.y},
        role: el.getAttribute('role'),
        href: el.getAttribute('href'),
        className: el.className,
        hasOnclick: !!el.onclick,
    });
}
return results;
"""

print("\nИщу элементы с текстом 'Enter a code'...\n")
results = driver.execute_script(js)
if not results:
    print("НИЧЕГО НЕ НАЙДЕНО. Возможно ты не на нужном экране.")
else:
    for i, r in enumerate(results):
        print(f"--- Результат {i + 1} ---")
        print(f"  tag:       {r['tag']}")
        print(f"  text:      {r['text']!r}")
        print(f"  role:      {r['role']}")
        print(f"  href:      {r['href']}")
        print(f"  className: {r['className']}")
        print(f"  onclick:   {r['hasOnclick']}")
        print(f"  rect:      {r['rect']}")
        print(f"  outerHTML: {r['outerHTML']}")
        if r['parentHTML']:
            print(f"  parentHTML:{r['parentHTML'][:300]}")
        print()

print("Нажми Enter чтобы закрыть браузер")
input()
driver.quit()
