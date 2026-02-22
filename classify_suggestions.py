"""
小红书候选词数据清洗与分类工具
输入: output/ 目录下的 suggestions_*.json
输出: output/ 目录下的 classified_*.json 和 classified_*.csv

流程:
  Step 1 → 噪声过滤 (Noise Filter)
  Step 2 → 五维度分类 (Token Classification)
"""

import csv
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

# ═══════════════════════════════════════════════════════════
#  Step 1: 噪声过滤规则
# ═══════════════════════════════════════════════════════════

# 规则1: 品类纠偏 — 非宠物语义黑名单（任意一词命中即过滤）
CATEGORY_BLACKLIST = [
    "咖啡", "银耳", "水果", "草莓", "山楂", "糖葫芦", "柠檬",
    "巧克力", "丝巾", "装修", "存款", "衣服", "眼膜", "烫伤",
    "牛排", "手机", "会所", "医疗险",
    # 扩展：明显无关的人类美容/食品词
    "冻干片", "冻干粉", "冻干粉平替", "冻干眼膜", "冻干粉排行",
    "奥伦纳素", "妍熙蔻", "必扬", "可逐", "嗨蔻", "polomix",
    "左旋", "beyoane", "米诺", "淡化斑点", "淡化黑眼圈",
    "祛黄", "滋润", "修复冻干", "阻击色斑", "轻薄冻干",
    "温和款", "冻干眼膜",
    "spa", "会所", "医疗", "险",
    "烫伤", "冷冻除疣", "冷冻疣",
    "榴莲", "扇贝", "汤圆", "水饺", "带鱼", "母乳",
    # 人类使用场景
    "人吃", "图片", "年代", "怀旧", "回忆", "pvp",
    "大寿", "行李箱", "码衣", "丝巾", "气垫", "粉底",
    "室内", "一厅",
    # 上班族无关词
    "减肥法", "带饭", "食谱", "美甲", "通勤", "减脂早餐", "快速早餐",
    "怎么减肥", "早餐", "蔬跃",
    # 黑巧魔方（人类食品）
    "黑巧",
    # 学术类无关词
    "考研", "历史", "政治", "地理", "学科", "证书", "课程", "笔记",
    # 非宠物食品类
    "蔬荇", "蓄云菜",
]

# 规则2: 主体纠偏 — 非犬猫动物
SUBJECT_BLACKLIST = ["鹦鹉", "仓鼠", "爬宠"]

# 规则3: 通用无意义词（单字/极短词）
GENERIC_NOISE = ["冻干"]  # 仅"冻干"两字本身无分类价值，但保留组合词


def is_noise(text: str) -> bool:
    """返回 True 表示该词应被过滤掉。"""
    # 规则1: 品类黑名单
    for word in CATEGORY_BLACKLIST:
        if word in text:
            return True
    # 规则2: 主体黑名单
    for word in SUBJECT_BLACKLIST:
        if word in text:
            return True
    # 规则3: 纯"冻干"两字（无附加信息）
    if text.strip() == "冻干":
        return True
    return False


# ═══════════════════════════════════════════════════════════
#  Step 2: 五维度分类规则（优先级从高到低）
# ═══════════════════════════════════════════════════════════

#  Bucket 5: 对比/鉴别词（优先级最高，语义最明确）
COMPARISON_RULES = [
    "区别", "对比", "哪个好", "差异", "平替",
    "和.*的区别", "好还是", "和普通", "和膨化", "和烘焙",
    "和主食冻干", "和冻肉",
]

#  Bucket 4: 品牌/竞品词
BRAND_RULES = [
    "朗诺", "生生不息", "帕特", "麦富迪", "网易严选", "网易", "诚实一口",
    "鲜朗", "蓝氏", "渴望", r"K9", r"\bVE\b", "喔喔", "WoWo",
    "光合魔方", "一只喜欢", "珍珠匠", "坦克小希", "TIRUI", "提瑞",
    "夏浪", "PouPou", "Feline Natural", "OKOPET",
    "派可兹", "PETKIDS", "初因子", "吞肉兽", "爪内",
    "膳小松", "牧场来信", "猫踪", "嗷屋", "魔宝",
    "简焙", "酥醒",
    "皇家", "希尔思", "爱肯拿",
    "地狱厨房", "最选", "beyoane",
]

#  Bucket 1: 用户痛点/场景词
PAIN_POINT_RULES = {
    "身体状况": [
        "软便", "拉稀", "拉肚", "过敏", "结痂", "下巴", "毛囊炎",
        "便秘", "长肉", "牙齿不好", "血丝", "拉血", "呕吐", "吐了",
        "腹泻", "泪痕", "黑下巴", "毛球", "洁齿", "关节",
        "细菌", "寄生虫", "有营养", "有假", "辨别", "好坏",
    ],
    "喂养困惑": [
        "怎么喂", "泡水", "搭配", "当主食", "骗水", "过渡",
        "风险", "频率", "复水", "怎么吃", "一天吃多少",
        "可以一直喂", "怎么保存", "放多久", "喂多少",
        "直接喂", "危害",
        "怎么做", "自制", "自己做", "可以代替", "能代替",
        "可以吃吗", "能吃吗", "复水",
    ],
    "生命阶段": [
        "幼猫", "幼犬", "老年猫", "小奶猫", "绝育", "多猫家庭",
        "奶猫", "小猫", "成猫", "换粮",
        "多猫食堂",  # 多猫场景
    ],
    "猫咪健康场景": [
        "美毛", "玻璃胃", "补水", "低敏",
        "怎么养狗", "怎么养猫",
    ],
}

#  Bucket 2: 产品属性/技术词
PRODUCT_FEATURE_RULES = {
    "核心指标": [
        "蛋白质", "牛磺酸", "添加", "无谷", "单一肉源",
        "复水", "水分", "含量", "配方", "成分", "生骨肉",
        "全价", "主食", "零食冻干", "肉含量",
        "肉粒", "肉干", "肉零食", "颗粒", "猫粮", "狗粮",
        "猫咪", "猫猫", "狗狗",  # 宠物主体词（作为产品受众标签）
    ],
    "生产工艺": [
        "冷冻干燥", "真空", "升华", "辐照", "灭菌", "锁鲜",
        "生产工艺", "低温", "原切", "工艺",
    ],
    "权威背书": [
        "SGS", "检测", "报告", "自主生产", "自有工厂", "50亩",
        "宗师", "ISO", "认证", "透明工厂", "代工", "工厂",
        "实验室",
    ],
    "知识科普": [
        "营养学", "基础知识", "怎么学", "书籍", "专业",
    ],
}

#  Bucket 3: 决策修饰/转化词
DECISION_MODIFIER_RULES = {
    "评价意图": [
        "推荐", "好不好", "怎么样", "测评", "排行榜", "口碑",
        "口感", "靠谱", "有没有必要", "正常吗", "好吗",
        "实测", "哪家", "哪个牌子", "什么牌子", "买什么",
        "怎么样", "好还是", "怎么选", "怎么选择",
    ],
    "价值倾向": [
        "性价比", "平价", "便宜", "高端", "好价", "囤货", "清单",
        "好物", "攻略", "平替", "高性价比", "国产", "价格",
    ],
    "避雷意图": ["避雷"],
    "时间敏感": ["2025", "2026", "双11", "最新", "新年"],
}

# 分类标签映射
BUCKET_LABELS = {
    "pain_point":       "用户痛点/场景词",
    "product_feature":  "产品属性/技术词",
    "decision_modifier":"决策修饰/转化词",
    "brand":            "品牌/竞品词",
    "comparison":       "对比/鉴别词",
    "unclassified":     "未分类",
}


def match_any(text: str, patterns: list[str]) -> bool:
    """文本中包含 patterns 中任意一个（支持正则）。"""
    for p in patterns:
        try:
            if re.search(p, text):
                return True
        except re.error:
            if p in text:
                return True
    return False


def match_dict_rules(text: str, rule_dict: dict) -> bool:
    """文本命中 rule_dict 中任意子类的任意规则。"""
    for patterns in rule_dict.values():
        if match_any(text, patterns):
            return True
    return False


def classify(text: str) -> str:
    """
    对单条候选词做分类，返回 bucket 键名。
    优先级: comparison > brand > pain_point > product_feature > decision_modifier > unclassified
    """
    if match_any(text, COMPARISON_RULES):
        return "comparison"
    if match_any(text, BRAND_RULES):
        return "brand"
    if match_dict_rules(text, PAIN_POINT_RULES):
        return "pain_point"
    if match_dict_rules(text, PRODUCT_FEATURE_RULES):
        return "product_feature"
    if match_dict_rules(text, DECISION_MODIFIER_RULES):
        return "decision_modifier"
    return "unclassified"


# ═══════════════════════════════════════════════════════════
#  主处理函数
# ═══════════════════════════════════════════════════════════

def process(input_json: str, output_dir: str = "output"):
    with open(input_json, encoding="utf-8") as f:
        raw: dict = json.load(f)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(output_dir, exist_ok=True)

    # ── 统计容器 ──
    classified: dict = {}          # { keyword: { bucket: [words] } }
    noise_log: dict = {}           # { keyword: [filtered_words] }
    bucket_agg: dict = {k: [] for k in BUCKET_LABELS}  # 全局桶

    total_raw = 0
    total_filtered = 0
    total_classified = 0

    for keyword, suggestions in raw.items():
        classified[keyword] = {k: [] for k in BUCKET_LABELS}
        noise_log[keyword] = []

        for word in suggestions:
            total_raw += 1
            if is_noise(word):
                total_filtered += 1
                noise_log[keyword].append(word)
                continue

            bucket = classify(word)
            classified[keyword][bucket].append(word)
            bucket_agg[bucket].append({"keyword": keyword, "suggestion": word})
            total_classified += 1

    # ── 保存清洗+分类后的完整 JSON ──
    out_json = os.path.join(output_dir, f"classified_{ts}.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(classified, f, ensure_ascii=False, indent=2)

    # ── 保存桶聚合 JSON（按维度查看所有词）──
    out_bucket_json = os.path.join(output_dir, f"buckets_{ts}.json")
    bucket_out = {BUCKET_LABELS[k]: v for k, v in bucket_agg.items()}
    with open(out_bucket_json, "w", encoding="utf-8") as f:
        json.dump(bucket_out, f, ensure_ascii=False, indent=2)

    # ── 保存 CSV（宽表，每行: keyword | 维度 | 候选词）──
    out_csv = os.path.join(output_dir, f"classified_{ts}.csv")
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["关键词", "维度", "维度(英文)", "候选词"])
        for keyword, buckets in classified.items():
            for bucket_key, words in buckets.items():
                label = BUCKET_LABELS[bucket_key]
                for word in words:
                    writer.writerow([keyword, label, bucket_key, word])

    # ── 保存噪声日志 ──
    out_noise = os.path.join(output_dir, f"noise_log_{ts}.json")
    with open(out_noise, "w", encoding="utf-8") as f:
        json.dump(noise_log, f, ensure_ascii=False, indent=2)

    # ── 控制台汇总报告 ──
    print("\n" + "=" * 60)
    print("  候选词清洗 & 分类报告")
    print("=" * 60)
    print(f"  原始候选词总数   : {total_raw}")
    print(f"  噪声过滤后剔除   : {total_filtered}  ({total_filtered/total_raw*100:.1f}%)")
    print(f"  进入分类的有效词 : {total_classified}")
    print()
    print("  ── 维度分布 ──")
    for bucket_key, label in BUCKET_LABELS.items():
        count = len(bucket_agg[bucket_key])
        bar = "█" * (count // 2)
        print(f"  {label:<16} {count:>4} 个  {bar}")
    print()
    print(f"  JSON（分关键词）: {out_json}")
    print(f"  JSON（按维度）  : {out_bucket_json}")
    print(f"  CSV              : {out_csv}")
    print(f"  噪声日志         : {out_noise}")
    print("=" * 60)

    # ── 未分类词预览（方便迭代规则）──
    if bucket_agg["unclassified"]:
        print(f"\n  ⚠️  未分类词 ({len(bucket_agg['unclassified'])} 个) — 可用于迭代规则:")
        for item in bucket_agg["unclassified"][:30]:
            print(f"     [{item['keyword']}] → {item['suggestion']}")
        if len(bucket_agg["unclassified"]) > 30:
            print(f"     ... 共 {len(bucket_agg['unclassified'])} 个，详见 {out_json}")

    return classified, bucket_agg


# ═══════════════════════════════════════════════════════════
#  入口
# ═══════════════════════════════════════════════════════════

def find_latest_json(output_dir: str = "output") -> Optional[str]:
    files = sorted(Path(output_dir).glob("suggestions_*.json"), reverse=True)
    return str(files[0]) if files else None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="候选词清洗与分类")
    parser.add_argument("-i", "--input", help="输入 JSON 文件路径（默认使用最新 suggestions_*.json）")
    parser.add_argument("-o", "--output", default="output", help="输出目录")
    args = parser.parse_args()

    input_file = args.input or find_latest_json(args.output)
    if not input_file:
        print("❌ 未找到候选词 JSON 文件，请先运行 xhs_suggestions.py")
        exit(1)

    print(f"📂 输入文件: {input_file}")
    process(input_file, args.output)
