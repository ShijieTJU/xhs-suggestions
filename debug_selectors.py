"""
调试脚本：输入关键词后截图并输出搜索框附近的 DOM，用来确认候选词的真实选择器。
"""
import time
import os
from playwright.sync_api import sync_playwright

XHS_URL = "https://www.xiaohongshu.com/"
KEYWORD = "宠物冻干"

os.makedirs("debug", exist_ok=True)


def dismiss_overlay(page):
    """关闭页面上可能存在的弹窗遮罩。"""
    # 按 Escape 尝试关闭弹窗
    page.keyboard.press("Escape")
    time.sleep(0.5)
    # 如果还有遮罩，尝试点击关闭按钮
    for close_sel in [
        '[aria-label="关闭"]',
        '.close-button',
        '.modal-close',
        'button.close',
        '[class*="close"]',
    ]:
        try:
            btn = page.locator(close_sel).first
            if btn.is_visible():
                btn.click(timeout=2000)
                time.sleep(0.5)
                break
        except Exception:
            pass
    # 等遮罩消失
    try:
        page.wait_for_selector('.reds-mask', state='hidden', timeout=5000)
    except Exception:
        pass
    time.sleep(0.5)


with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    )
    page = context.new_page()
    page.goto(XHS_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    print("🔑 请扫码登录，等待搜索框出现...")
    # 等待搜索框
    for sel in ["#search-input", 'input[placeholder*="搜索"]', 'input[type="search"]']:
        try:
            page.wait_for_selector(sel, timeout=300_000)
            print(f"✅ 登录成功，搜索框选择器: {sel}")
            search_sel = sel
            break
        except Exception:
            continue

    time.sleep(2)

    # 关闭登录后可能出现的弹窗遮罩
    dismiss_overlay(page)

    # 点击搜索框并输入
    search = page.locator(search_sel)
    search.click(force=True)
    time.sleep(0.5)
    search.type(KEYWORD, delay=150)
    print(f"✅ 已输入关键词「{KEYWORD}」，等待候选词...")
    time.sleep(3.5)  # 给足时间等候选词弹出

    # 截图
    page.screenshot(path="debug/after_type.png", full_page=False)
    print("📸 截图已保存: debug/after_type.png")

    # 输出整个 body 的简化 HTML（只保留 class 和 tag，帮助定位）
    html_snippet = page.evaluate("""
        () => {
            let el = document.querySelector('#search-input') 
                  || document.querySelector('input[placeholder*="搜索"]');
            if (!el) return 'input not found';
            // 向上 8 层，获取更大范围
            let node = el;
            for (let i = 0; i < 8; i++) {
                if (node.parentElement) node = node.parentElement;
            }
            return node.outerHTML.substring(0, 20000);
        }
    """)
    with open("debug/search_dom.html", "w", encoding="utf-8") as f:
        f.write(html_snippet)
    print("📄 搜索框附近 DOM 已保存: debug/search_dom.html")

    # 同时保存完整 body HTML
    full_html = page.evaluate("() => document.body.outerHTML.substring(0, 100000)")
    with open("debug/full_body.html", "w", encoding="utf-8") as f:
        f.write(full_html)
    print("📄 完整 body HTML 已保存: debug/full_body.html")


    # 尝试打印所有候选词相关元素的文本和选择器（兼容 SVG 元素）
    candidates = page.evaluate("""
        () => {
            const results = [];
            const keywords = ['suggest', 'sug', 'dropdown', 'completion', 'hint', 'tip', 'autocomplete', 'search-rec', 'search_rec', 'rec-item', 'rec_item'];
            document.querySelectorAll('*').forEach(el => {
                // SVG 元素的 className 是 SVGAnimatedString，用 String() 转换
                const cls = (typeof el.className === 'string' ? el.className : String(el.className?.baseVal || '')).toLowerCase();
                if (keywords.some(k => cls.includes(k))) {
                    const txt = (el.innerText || el.textContent || '').trim();
                    if (txt && txt.length < 300) {
                        results.push({
                            tag: el.tagName,
                            class: typeof el.className === 'string' ? el.className : (el.className?.baseVal || ''),
                            text: txt.substring(0, 150),
                        });
                    }
                }
            });
            return results.slice(0, 80);
        }
    """)
    print("\n🔎 候选词相关元素:")
    if candidates:
        for c in candidates:
            print(f"  <{c['tag']} class=\"{c['class']}\">  {c['text']!r}")
    else:
        print("  ⚠️  未找到任何候选词相关元素")

    # 保存完整候选信息到文件
    import json
    with open("debug/candidates.json", "w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)
    print("\n📄 候选元素详情已保存: debug/candidates.json")

    input("\n按 Enter 关闭浏览器...")
    browser.close()

print("\n✅ 调试完成，请查看 debug/ 目录")
