import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from steam_browser import make_driver  # noqa: E402

driver = make_driver(profile_dir=str(Path(__file__).parent / "chrome_profiles" / "_debug"))
driver.get("https://store.steampowered.com/login/")

print()
print("=" * 70)
print("1. 在 Chrome 窗口中输入登录名和密码")
print("2. 等到出现 'Use the Steam Mobile App to confirm your sign in' 页面")
print("3. 回到这里并按 Enter")
print("=" * 70)
input()

js = r"""
const phrases = ['enter a code', '输入代码', '请输入代码'];

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

print("\n正在查找包含 'Enter a code' 文本的元素...\n")
results = driver.execute_script(js)
if not results:
    print("未找到任何结果。你可能不在正确的页面。")
else:
    for i, r in enumerate(results):
        print(f"--- 结果 {i + 1} ---")
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

print("按 Enter 关闭浏览器")
input()
driver.quit()
