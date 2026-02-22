#!/usr/bin/env python3
"""
token_analysis.py — Token频率分析 + 100条Prompt矩阵生成

步骤：
1. 读取最新 buckets_*.json
2. 用 jieba 对"用户痛点/场景词"分词，统计 Token 频次权重
3. 提取"产品属性/技术词"和"决策修饰/转化词"的核心词
4. 按 [痛点] × [属性] × [修饰] 组合生成 100 条 Prompt
"""

import json
import glob
import os
import re
import csv
from collections import Counter
from datetime import datetime
from itertools import product

import jieba

# 注入自定义词典，防止复合词被拆分
_CUSTOM_WORDS = [
    "玻璃胃", "冻干复水", "幼猫换粮", "幼犬换粮", "黑下巴",
    "泪痕", "软便", "便秘", "过敏", "绝育后", "鸡胸肉",
    "寄生虫", "低敏", "补水", "老年猫", "美毛", "去泪痕",
]
for _w in _CUSTOM_WORDS:
    jieba.add_word(_w)

# ── 停用词 ────────────────────────────────────────────────────────────────────
STOPWORDS = {
    # 代词/助词/副词
    "猫咪", "猫", "狗", "狗狗", "宠物", "的", "了", "是", "吗", "吃", "什么",
    "怎么", "如何", "可以", "能", "有", "会", "不", "好", "来", "在", "和",
    "一", "个", "也", "要", "这", "那", "都", "被", "让", "给", "为", "把",
    "以", "于", "而", "再", "或", "及", "就", "到", "从", "对", "用", "与",
    "人", "后", "对", "等", "啊", "呢", "呀", "嗯", "啦", "哦", "吧",
    "我", "你", "他", "她", "我们", "你们", "他们", "猫猫",
    # 动词/通用词（不是痛点本身）
    "冻干", "推荐", "自制", "方法", "解决", "危害", "多久", "怎么办",
    "不复水", "喂养", "补充", "选择", "处理", "治疗", "治", "清理",
    "吃什么", "怎么吃", "怎么喂", "注意事项", "原因",
    # 碎片词（jieba 切割产物）
    "肉冻", "骨肉", "猫粮", "小奶", "主食", "营养",
}

# 产品属性核心词（直接从 suggestion 文本中提取含义词）
ATTR_TERMS = [
    "生骨肉配方", "单一肉源", "低温冻干", "含牛磺酸", "真空冷冻干燥",
    "主食冻干", "全价冻干", "低敏配方", "高蛋白", "蛋白质含量",
    "冻干生骨肉", "鲜肉冻干", "冻干颗粒", "全肉冻干", "冻干双拼",
    "零添加", "检测报告", "SGS检测", "低温工艺",
]

# 决策修饰核心词
MODIFIER_TERMS = [
    "推荐", "性价比高", "平价", "高端", "测评", "排行榜",
    "怎么选", "哪个好", "好价", "安全可靠",
]

# Prompt 模板（[P]=痛点, [A]=属性, [M]=修饰）
TEMPLATES = [
    "猫咪[P]问题，选[A]能改善吗？求[M]",
    "有[P]问题的猫咪，适合吃[A]吗？求[M]",
    "针对猫咪[P]，[A]冻干有哪些[M]推荐？",
    "猫咪出现[P]，[A]产品怎么选？求[M]",
    "解决猫咪[P]，[A]哪款[M]？",
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 加载数据
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def load_latest_buckets(output_dir: str = "output") -> dict:
    files = sorted(glob.glob(os.path.join(output_dir, "buckets_*.json")), reverse=True)
    if not files:
        raise FileNotFoundError(f"No buckets_*.json found in {output_dir}/")
    path = files[0]
    print(f"[INFO] 读取: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. 痛点词频分析
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def token_freq(pain_point_items: list) -> Counter:
    """对用户痛点/场景词桶中的所有 suggestion 做分词，统计词频。"""
    counter: Counter = Counter()
    for item in pain_point_items:
        text = item["suggestion"]
        # jieba 分词
        tokens = jieba.lcut(text)
        for t in tokens:
            t = t.strip()
            if len(t) < 2:
                continue
            if t in STOPWORDS:
                continue
            # 过滤纯数字或英文
            if re.match(r"^[a-zA-Z0-9]+$", t):
                continue
            counter[t] += 1
    return counter


def print_token_freq(counter: Counter, top_n: int = 30) -> list:
    print(f"\n{'═'*55}")
    print(f"  TOP-{top_n} 痛点 Token 频次权重")
    print(f"{'═'*55}")
    print(f"  {'排名':<4} {'Token':<14} {'频次':>4}  {'权重(%)':>7}")
    print(f"  {'-'*44}")
    total = sum(counter.values())
    top = counter.most_common(top_n)
    for i, (token, cnt) in enumerate(top, 1):
        weight = cnt / total * 100
        print(f"  {i:<4} {token:<14} {cnt:>4}  {weight:>6.1f}%")
    print(f"{'═'*55}\n")
    return [t for t, _ in top]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. 属性词 & 修饰词提取
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def extract_attr_terms(items: list, preset: list) -> list:
    """从「产品属性/技术词」bucket 中统计高频 suggestion，合并预设词清单。"""
    counter: Counter = Counter()
    for item in items:
        seg = [t.strip() for t in jieba.lcut(item["suggestion"]) if len(t.strip()) >= 2]
        for t in seg:
            if t not in STOPWORDS and not re.match(r"^[a-zA-Z0-9]+$", t):
                counter[t] += 1
    # 取 top-10 + 预设词，去重
    top = [t for t, _ in counter.most_common(20)]
    merged = list(dict.fromkeys(preset + top))  # 保持预设词在前，去重
    return merged


def extract_modifier_terms(items: list, preset: list) -> list:
    """从「决策修饰/转化词」bucket 中统计高频 suggestion，合并预设词清单。"""
    counter: Counter = Counter()
    for item in items:
        seg = [t.strip() for t in jieba.lcut(item["suggestion"]) if len(t.strip()) >= 2]
        for t in seg:
            if t not in STOPWORDS and not re.match(r"^[a-zA-Z0-9]+$", t):
                counter[t] += 1
    top = [t for t, _ in counter.most_common(15)]
    merged = list(dict.fromkeys(preset + top))
    return merged


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. Prompt 矩阵生成
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _prompts_for_pain(
    pain: str,
    quota: int,
    attr_tokens: list,
    modifier_tokens: list,
    seen: set,
    start_id: int,
) -> list[dict]:
    """为单个痛点词生成 quota 条不重复的 Prompt。"""
    result = []
    for template, attr, mod in product(TEMPLATES, attr_tokens, modifier_tokens):
        text = template.replace("[P]", pain).replace("[A]", attr).replace("[M]", mod)
        if text not in seen:
            seen.add(text)
            result.append({
                "id": start_id + len(result),
                "痛点": pain,
                "属性": attr,
                "修饰": mod,
                "prompt": text,
            })
        if len(result) >= quota:
            break
    return result


def generate_prompts_weighted(
    pain_weights: list,
    attr_tokens: list,
    modifier_tokens: list,
) -> list[dict]:
    """
    按指定配额生成加权 Prompt 矩阵。
    pain_weights: [(pain_token, quota), ...]
    """
    prompts: list[dict] = []
    seen: set = set()
    for pain, quota in pain_weights:
        batch = _prompts_for_pain(pain, quota, attr_tokens, modifier_tokens, seen, len(prompts) + 1)
        prompts.extend(batch)
        print(f"  [{pain}] 目标{quota}条 → 实际生成{len(batch)}条")
    # 重新编号
    for i, p in enumerate(prompts, 1):
        p["id"] = i
    return prompts


def save_prompts(prompts: list, output_dir: str = "output") -> tuple[str, str]:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(output_dir, exist_ok=True)

    json_path = os.path.join(output_dir, f"prompt_matrix_{ts}.json")
    csv_path  = os.path.join(output_dir, f"prompt_matrix_{ts}.csv")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=2)

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "痛点", "属性", "修饰", "prompt"])
        writer.writeheader()
        writer.writerows(prompts)

    return json_path, csv_path


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    buckets = load_latest_buckets()

    pain_items     = buckets.get("用户痛点/场景词", [])
    attr_items     = buckets.get("产品属性/技术词", [])
    modifier_items = buckets.get("决策修饰/转化词", [])

    print(f"[INFO] 痛点条目: {len(pain_items)} | 属性条目: {len(attr_items)} | 修饰条目: {len(modifier_items)}")

    # ── Step 1: 痛点词频 ────────────────────────────────────────────────────
    counter = token_freq(pain_items)
    top_pain = print_token_freq(counter, top_n=30)

    # 保存频次表
    freq_path = f"output/token_freq_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    os.makedirs("output", exist_ok=True)
    with open(freq_path, "w", encoding="utf-8") as f:
        json.dump(
            [{"token": t, "freq": c, "weight_pct": round(c / sum(counter.values()) * 100, 2)}
             for t, c in counter.most_common(50)],
            f, ensure_ascii=False, indent=2,
        )
    print(f"[INFO] 频次表已保存: {freq_path}")

    # ── Step 2: 属性词 & 修饰词提取 ─────────────────────────────────────────
    attr_terms     = extract_attr_terms(attr_items, ATTR_TERMS)[:15]
    modifier_terms = extract_modifier_terms(modifier_items, MODIFIER_TERMS)[:8]

    print("【属性词（TOP-15）】:", "、".join(attr_terms[:15]))
    print("【修饰词（TOP-8）】 :", "、".join(modifier_terms[:8]))

    # ── Step 3: Prompt 矩阵（加权分配） ─────────────────────────────────
    # 痛点配额分布：40% / 30% / 20% / 10%
    pain_weights = [
        # 40%
        ("冻干复水",  40),
        # 30%（三个各占 10%）
        ("软便",      10),
        ("黑下巴",     10),
        ("便秘",      10),
        # 20%（三个列1：7+7+6）
        ("蓝粘毛",     7),
        ("波立维",     7),
        ("幼猫换粮",    6),
        # 10%（三个列4+3+3）
        ("补水",      4),
        ("鸡胸肉",     3),
        ("幼猫",      3),
    ]

    print("\n生成加权 Prompt 矩阵（共 100 条）...")
    prompts = generate_prompts_weighted(pain_weights, attr_terms, modifier_terms)

    json_path, csv_path = save_prompts(prompts)

    print(f"\n{'═'*55}")
    print(f"  ✅ Prompt 矩阵生成完毕（共 {len(prompts)} 条）")
    print(f"  JSON → {json_path}")
    print(f"  CSV  → {csv_path}")
    print(f"{'═'*55}")

    # 预览前 10 条
    print("\n── 前 10 条 Prompt 预览 ──────────────────────────────────")
    for p in prompts[:10]:
        print(f"  [{p['id']:>3}] {p['prompt']}")
    print()


if __name__ == "__main__":
    main()
