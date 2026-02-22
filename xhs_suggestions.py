"""
小红书搜索候选词采集工具
使用 Playwright 控制浏览器，打开小红书首页，
扫码登录后依次输入关键词并采集搜索框弹出的候选提示词。

用法:
    # ① 首次登录（只需运行一次，登录后按 Enter 保存状态）
    python xhs_suggestions.py --login

    # ② 后续采集（自动复用登录状态，无需再扫码）
    python xhs_suggestions.py                     # 默认读取 keywords.txt
    python xhs_suggestions.py -f my_keywords.txt  # 指定关键词文件
    python xhs_suggestions.py -k 美食 穿搭 旅行    # 直接传入关键词

    # ③ 强制重新登录
    python xhs_suggestions.py --login
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout


# ────────────────────────── 配置区 ──────────────────────────
XHS_URL = "https://www.xiaohongshu.com/"
LOGIN_WAIT_TIMEOUT = 300_000       # 扫码登录最长等待 5 分钟（毫秒）
SEARCH_INPUT_DELAY = 120           # 每个字符输入间隔（毫秒），模拟人工
SUGGESTION_WAIT = 3000             # 等待候选词弹出的超时（毫秒）
BETWEEN_KEYWORDS_SLEEP = 2        # 每个关键词之间的间隔（秒）
OUTPUT_DIR = "output"
AUTH_STATE_FILE = "auth_state.json"   # 登录状态持久化文件


# ────────────────────────── 工具函数 ──────────────────────────

def load_keywords(filepath: str) -> list[str]:
    """从文本文件加载关键词，每行一个，忽略空行和 # 开头的注释行。"""
    keywords = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                keywords.append(line)
    return keywords


def save_results(results: dict, output_dir: str):
    """将结果同时保存为 JSON 和 CSV。"""
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── JSON ──
    json_path = os.path.join(output_dir, f"suggestions_{ts}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n✅ JSON 已保存: {json_path}")

    # ── CSV ──
    csv_path = os.path.join(output_dir, f"suggestions_{ts}.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["关键词", "候选词序号", "候选词"])
        for kw, suggestions in results.items():
            for idx, s in enumerate(suggestions, 1):
                writer.writerow([kw, idx, s])
    print(f"✅ CSV 已保存: {csv_path}")


def dismiss_overlay(page):
    """关闭登录后可能出现的弹窗遮罩。"""
    page.keyboard.press("Escape")
    time.sleep(0.5)
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
    try:
        page.wait_for_selector('.reds-mask', state='hidden', timeout=5000)
    except Exception:
        pass
    time.sleep(0.5)


def wait_for_login(page):
    """等待用户扫码登录完成。通过检测页面上出现搜索框来判断已登录。"""
    print("\n🔑 请在浏览器中扫码登录小红书...")
    print(f"   （最长等待 {LOGIN_WAIT_TIMEOUT // 1000} 秒）\n")

    # 登录成功后搜索框会出现，用它作为登录完成的标志
    try:
        page.wait_for_selector("#search-input", timeout=LOGIN_WAIT_TIMEOUT)
    except PwTimeout:
        # 尝试备用选择器
        try:
            page.wait_for_selector('input[placeholder*="搜索"]', timeout=10_000)
        except PwTimeout:
            print("⚠️  等待登录超时，尝试继续执行...")
            return

    print("✅ 登录成功！\n")
    time.sleep(2)  # 等页面完全稳定
    dismiss_overlay(page)  # 确保弹窗已关闭


def clear_search_box(page):
    """清空搜索框内容。"""
    dismiss_overlay(page)  # 每次操作前确保无遮罩
    search_input = page.locator("#search-input")
    if not search_input.is_visible():
        search_input = page.locator('input[placeholder*="搜索"]')

    search_input.click(force=True)
    time.sleep(0.3)
    # 全选并删除
    page.keyboard.press("Meta+a" if sys.platform == "darwin" else "Control+a")
    page.keyboard.press("Backspace")
    time.sleep(0.5)


def collect_suggestions(page, keyword: str) -> list[str]:
    """
    在搜索框中输入关键词，等待候选词弹出，采集并返回候选词列表。
    """
    print(f"  🔍 输入关键词: 「{keyword}」")

    # 1. 清空搜索框
    clear_search_box(page)

    # 2. 定位搜索框并逐字输入
    search_input = page.locator("#search-input")
    if not search_input.is_visible():
        search_input = page.locator('input[placeholder*="搜索"]')

    search_input.click(force=True)
    time.sleep(0.3)

    # 逐字符输入以触发联想
    search_input.type(keyword, delay=SEARCH_INPUT_DELAY)

    # 3. 等待候选词下拉框出现（真实选择器：.sug-item）
    suggestions = []

    time.sleep(2.0)  # 等待请求返回并渲染

    try:
        # 直接等待候选项出现
        page.wait_for_selector(".sug-item", timeout=SUGGESTION_WAIT)
        elements = page.locator(".sug-item")
        count = elements.count()
        for i in range(count):
            text = elements.nth(i).inner_text().strip()
            if text and text not in suggestions:
                suggestions.append(text)
    except Exception:
        pass

    # 备用：从整个 sug-box 容器提取文本行
    if not suggestions:
        try:
            box = page.locator(".sug-box, .sug-container, .sug-wrapper")
            if box.count() > 0:
                lines = [l.strip() for l in box.first.inner_text().split("\n") if l.strip()]
                suggestions = lines
        except Exception:
            pass

    if suggestions:
        print(f"     ✅ 获取到 {len(suggestions)} 个候选词")
        for idx, s in enumerate(suggestions, 1):
            print(f"        {idx}. {s}")
    else:
        print(f"     ⚠️  未获取到候选词")

    return suggestions


# ────────────────────────── 浏览器工厂 ──────────────────────────

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]


def make_browser_context(p, *, headless: bool = False, storage_state: Optional[str] = None):
    """创建浏览器 + context，可选加载已保存的登录状态。"""
    browser = p.chromium.launch(headless=headless, args=LAUNCH_ARGS)
    ctx_kwargs = dict(viewport={"width": 1280, "height": 800}, user_agent=UA)
    if storage_state and os.path.exists(storage_state):
        ctx_kwargs["storage_state"] = storage_state
    context = browser.new_context(**ctx_kwargs)
    return browser, context


# ────────────────────────── 登录模式 ──────────────────────────

def cmd_login(args):
    """打开浏览器，等待用户扫码登录，保存登录状态后退出。"""
    auth_file = args.auth
    print("=" * 50)
    print("  小红书登录状态保存工具")
    print("=" * 50)
    print(f"  登录状态将保存到: {auth_file}")
    print("=" * 50)

    with sync_playwright() as p:
        browser, context = make_browser_context(p)
        page = context.new_page()

        print(f"\n🌐 正在打开 {XHS_URL} ...")
        page.goto(XHS_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        wait_for_login(page)

        # 保存登录状态（Cookie + localStorage）
        context.storage_state(path=auth_file)
        print(f"💾 登录状态已保存到: {auth_file}")
        print("\n✅ 后续运行将自动复用此登录状态，无需再扫码。")
        print("   若需重新登录，重新运行 --login 即可。\n")

        browser.close()


# ────────────────────────── 采集模式 ──────────────────────────

def cmd_collect(args, keywords: list[str]):
    """加载登录状态并依次采集候选词。"""
    auth_file = args.auth
    has_auth = os.path.exists(auth_file)

    print("=" * 50)
    print("  小红书搜索候选词采集工具")
    print("=" * 50)
    if has_auth:
        print(f"  🔓 使用已保存的登录状态: {auth_file}")
    else:
        print("  ⚠️  未找到登录状态，将进行扫码登录并自动保存")
    print(f"  待采集关键词 ({len(keywords)} 个):")
    for i, kw in enumerate(keywords, 1):
        print(f"    {i}. {kw}")
    print("=" * 50)

    results = {}

    with sync_playwright() as p:
        browser, context = make_browser_context(
            p,
            headless=args.headless,
            storage_state=auth_file if has_auth else None,
        )
        page = context.new_page()

        print(f"\n🌐 正在打开 {XHS_URL} ...")
        page.goto(XHS_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        if not has_auth:
            # 首次使用：引导扫码并保存状态
            wait_for_login(page)
            context.storage_state(path=auth_file)
            print(f"💾 登录状态已保存到: {auth_file}（下次运行自动复用）\n")
        else:
            # 已有登录状态：验证是否仍然有效
            print("🔄 验证登录状态...")
            try:
                page.wait_for_selector("#search-input", timeout=15_000)
                print("✅ 登录状态有效，开始采集...\n")
                dismiss_overlay(page)
            except PwTimeout:
                print("⚠️  登录状态已失效，请重新运行 --login 登录后再试")
                browser.close()
                sys.exit(1)

        # 依次采集关键词候选词
        for idx, keyword in enumerate(keywords, 1):
            print(f"\n[{idx}/{len(keywords)}]", end="")
            suggestions = collect_suggestions(page, keyword)
            results[keyword] = suggestions

            if idx < len(keywords):
                time.sleep(BETWEEN_KEYWORDS_SLEEP)

        # 保存结果
        save_results(results, args.output)

        # 汇总
        print("\n" + "=" * 50)
        print("  采集汇总")
        print("=" * 50)
        total_suggestions = 0
        for kw, sugs in results.items():
            count = len(sugs)
            total_suggestions += count
            print(f"  「{kw}」: {count} 个候选词")
        print(f"\n  共采集 {len(keywords)} 个关键词，{total_suggestions} 个候选词")
        print("=" * 50)

        browser.close()

    print("\n🎉 采集完成！")


# ────────────────────────── 主入口 ──────────────────────────

def main():
    parser = argparse.ArgumentParser(description="小红书搜索候选词采集工具")
    parser.add_argument(
        "--login", action="store_true",
        help="登录模式：打开浏览器扫码登录并保存状态，之后采集无需再登录"
    )
    parser.add_argument(
        "--auth", default=AUTH_STATE_FILE,
        help=f"登录状态文件路径（默认: {AUTH_STATE_FILE}）"
    )
    parser.add_argument("-f", "--file", default="keywords.txt", help="关键词文件路径（每行一个关键词）")
    parser.add_argument("-k", "--keywords", nargs="+", help="直接指定关键词列表")
    parser.add_argument("--headless", action="store_true", help="无头模式（仅采集模式可用，需已有登录状态）")
    parser.add_argument("-o", "--output", default=OUTPUT_DIR, help="输出目录")
    args = parser.parse_args()

    # ── 登录模式 ──
    if args.login:
        cmd_login(args)
        return

    # ── 采集模式：加载关键词 ──
    if args.keywords:
        keywords = args.keywords
    else:
        kw_file = args.file
        if not os.path.exists(kw_file):
            kw_file = os.path.join(os.path.dirname(__file__), args.file)
        if not os.path.exists(kw_file):
            print(f"❌ 关键词文件不存在: {args.file}")
            print("   请创建 keywords.txt 或使用 -k 参数直接传入关键词")
            sys.exit(1)
        keywords = load_keywords(kw_file)

    if not keywords:
        print("❌ 没有找到任何关键词，请检查输入")
        sys.exit(1)

    cmd_collect(args, keywords)


if __name__ == "__main__":
    main()
