#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_tells.py — 中文 AI 写作痕迹扫描器
humanizer-zh-pro v3.0.0 配套工具 ｜ 零依赖（仅标准库，Python 3.8+）

用途：扫描中文文本，给出 14 项指标的实测值 / 阈值 / PASS·WARN·FAIL。
定位：**筛查器，不是判决器**。它只能发现"可能有"，不能判定"一定是"。
     数字全 PASS 的文本仍可能是 AI 味十足的编辑腔。

三条使用纪律
  1. 这是筛查器，不是判决器 —— 人工复扫不可省。
  2. 「破折号」「三段式」两项**只提示、不判决** —— 是否算病取决于功能（见 SKILL.md §3 B 组）。
     脚本给 WARN 也不代表要改；这两项不计入总判定。
  3. 文体不适用时不要跑（公文 / 法律 / 学术 / 规范）—— 会得到一屏全是误报的 FAIL。

用法
  python check_tells.py 文章.md
  cat 文章.md | python check_tells.py -
  python check_tells.py 文章.md --only fail
  python check_tells.py 文章.md --json
  python check_tells.py 文章.md --quiet
"""

import argparse
import json
import re
import statistics
import sys
from collections import Counter

# ---------------------------------------------------------------- 词表

# 条目 7：过度使用的 AI 词汇（单个不算病，一段里 3 个以上才警觉）
AI_WORDS = [
    "此外", "与……保持一致", "保持一致", "至关重要", "深入探讨", "强调",
    "持久的", "增强", "培养", "获得", "突出", "相互作用", "复杂性", "复杂",
    "关键的", "关键性", "格局", "展示", "织锦", "证明", "宝贵的", "充满活力的",
    "彰显", "凸显", "赋能", "助力", "打造", "深耕", "闭环", "抓手", "底层逻辑",
]

# 条目 22：填充短语
FILLERS = [
    "为了实现这一目标", "由于下雨的事实", "在这个时间点", "在您需要帮助的情况下",
    "系统具有处理的能力", "值得注意的是数据显示", "值得注意的是",
    "需要指出的是", "不可否认的是", "众所周知", "综上所述", "总而言之",
    "从某种意义上说", "在很大程度上", "在一定程度上", "不难看出",
    "显而易见", "毫无疑问",
]

# 条目 19 / 20 / 21：对话残留
RESIDUE = [
    "希望这对您有帮助", "希望这对你有帮助", "希望有帮助", "请告诉我",
    "好问题", "您说得完全正确", "你说得完全正确", "当然！", "一定！",
    "如果您想让我", "如果你想让我", "以下是", "这是一个",
]
RESIDUE_RE = [
    r"截至\s*\d{4}\s*年", r"根据我最后的训练", r"根据我的训练数据",
    r"虽然[^。]{0,20}(有限|稀缺|不多)", r"基于(现有|可用)信息",
]

# 条目 23：过度限定
HEDGES = ["可能", "也许", "或许", "大概", "似乎", "貌似", "据推测", "想必"]

# 条目 24：通用积极结论
HAPPY_END = [
    "光明", "未来可期", "激动人心", "迈出重要一步", "迈出了重要一步",
    "追求卓越", "值得期待", "翻开新篇章", "注入新活力", "开启新篇章",
    "必将", "贡献力量", "添砖加瓦",
]

# 条目 8：系动词回避
COPULA_AVOID = [
    r"标志着", r"充当了", r"堪称", r"作为[^，。；]{0,8}的(证明|体现|象征|代表)",
    r"拥有[^，。；]{0,10}的(特点|特征|优势)",
]

# 条目 9：否定式排比
NEG_PARALLEL = [
    r"不仅[^。；]{1,40}(而且|还|更|也)",
    r"不只是?[^。；]{1,40}而是",
    r"不是[^。；]{1,30}而是",
    r"既是[^。；]{1,30}也是",
]

EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF"
    "\U00002190-\U000021FF\U00002B00-\U00002BFF\uFE0F]"
)
SENT_SPLIT = re.compile(r"[。！？!?；;\n]+")


def _sentences(text):
    return [s.strip() for s in SENT_SPLIT.split(text) if len(s.strip()) >= 2]


def _per_k(pat, text, chars):
    """每千字密度"""
    n = len(re.findall(pat, text))
    return n, round(n * 1000.0 / max(chars, 1), 2)


def _count_list(words, text):
    hits = Counter()
    total = 0
    for w in words:
        c = text.count(w)
        if c:
            hits[w] = c
            total += c
    return total, hits


def analyze(raw):
    text = raw
    chars = len(re.findall(r"[^\s]", text))
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    res = []
    meta = {"chars": chars, "cjk": cjk, "sentences": len(_sentences(text))}

    def add(key, item, value, display, level, note, advisory=False):
        res.append({
            "key": key, "item": item, "value": value, "display": display,
            "level": level, "note": note, "advisory": advisory,
        })

    # ---- 1. 破折号（条目 13）— 只提示 ----
    n_dash, dens = _per_k(r"——|—", text, chars)
    lvl = "FAIL" if dens > 5 else "WARN" if dens > 2 else "PASS"
    add("dash", "13 破折号密度", dens, f"{n_dash} 处 / 千字 {dens}",
        lvl if lvl != "FAIL" else "WARN",
        "每千字 >2 提示复核；>5 多为过度使用。**改标点 ≠ 删内容**，逐处看是否替代了逗号/句号。", True)

    # ---- 2. 三段式（条目 10）— 只提示 ----
    tri = 0
    for s in _sentences(text):
        if s.count("、") == 2:
            tri += 1
        elif re.search(r"[^、，]{2,12}[、，][^、，]{2,12}(和|及|以及)[^、，]{2,12}", s):
            tri += 1
    lvl = "WARN" if tri >= 3 else "PASS"
    add("triple", "10 三段式疑似", tri, f"{tri} 句",
        lvl,
        "并列项恰为 3 的句子数。**三项本身不是错**——各有独立信息就保留，只删凑数项。", True)

    # ---- 3. 否定式排比（条目 9）----
    neg = sum(len(re.findall(p, text)) for p in NEG_PARALLEL)
    lvl = "FAIL" if neg >= 4 else "WARN" if neg >= 2 else "PASS"
    add("negpara", "9 否定式排比", neg, f"{neg} 处", lvl,
        "「不仅…而且」「不只是…而是」。问：前后真在说两件事吗？只是重复 → 删半句。")

    # ---- 4. AI 词频（条目 7）----
    ai_total, ai_hits = _count_list(AI_WORDS, text)
    ai_dens = round(ai_total * 1000.0 / max(chars, 1), 2)
    lvl = "FAIL" if ai_dens > 8 else "WARN" if ai_dens > 3 else "PASS"
    top = "、".join(f"{w}×{c}" for w, c in ai_hits.most_common(5))
    add("aiwords", "7 AI 词汇密度", ai_dens, f"{ai_total} 次 / 千字 {ai_dens}"
        + (f"（{top}）" if top else ""), lvl,
        "单个词不算病，**一段里 3 个以上**才要处理。看它是概念还是装饰。")

    # ---- 5. 粗体密度（条目 14）----
    n_bold = len(re.findall(r"\*\*[^*\n]{1,60}\*\*", text))
    bold_dens = round(n_bold * 1000.0 / max(chars, 1), 2)
    lvl = "FAIL" if bold_dens > 6 else "WARN" if bold_dens > 3 else "PASS"
    add("bold", "14 粗体密度", bold_dens, f"{n_bold} 处 / 千字 {bold_dens}", lvl,
        "看加粗位置是「重点」还是「名词」。是名词 → 取消加粗。")

    # ---- 6. 内联标题列表（条目 15）----
    n_inline = len(re.findall(r"(?m)^\s{0,4}[-*+]\s+\*\*[^*\n]{1,20}[:：]\*\*", text))
    lvl = "FAIL" if n_inline >= 5 else "WARN" if n_inline >= 3 else "PASS"
    add("inline", "15 内联标题列表", n_inline, f"{n_inline} 项", lvl,
        "`- **标题：** 内容`。项间有逻辑关系（流程/因果）→ 保留；只是并列优点 → 改成一段话。")

    # ---- 7. 表情符号（条目 17）----
    n_emoji = len(EMOJI_RE.findall(text))
    lvl = "WARN" if n_emoji >= 8 else "PASS"
    add("emoji", "17 表情符号", n_emoji, f"{n_emoji} 个", lvl,
        "**看渠道**：公众号/小红书是正常手段；正式文档/邮件/报告 → 删。")

    # ---- 8. 引号一致性（条目 18）----
    q_ascii = text.count('"') + text.count("'")
    q_cn = text.count("“") + text.count("”")
    q_jp = text.count("「") + text.count("」")
    lvl = "FAIL" if (cjk > chars * 0.4 and q_ascii > 2) else "WARN" if q_ascii > 0 else "PASS"
    add("quotes", "18 引号一致性", q_ascii,
        f'直引号 {q_ascii} ｜ 中文引号 {q_cn} ｜ 直角引号 {q_jp}', lvl,
        "中文正文里出现直引号 \" ' 通常是英文残留。统一为一种中文引号（“”或「」），**不要混**。")

    # ---- 9. 系动词回避（条目 8）----
    n_cop = sum(len(re.findall(p, text)) for p in COPULA_AVOID)
    lvl = "FAIL" if n_cop >= 4 else "WARN" if n_cop >= 2 else "PASS"
    add("copula", "8 系动词回避", n_cop, f"{n_cop} 处", lvl,
        "「作为/充当/标志着」替代「是/有」。换回后更清楚就换；在强调角色转换则保留。")

    # ---- 10. 填充短语（条目 22）----
    fill_total, fill_hits = _count_list(FILLERS, text)
    lvl = "FAIL" if fill_total >= 5 else "WARN" if fill_total >= 2 else "PASS"
    ftop = "、".join(f"{w}×{c}" for w, c in fill_hits.most_common(4))
    add("filler", "22 填充短语", fill_total,
        f"{fill_total} 处" + (f"（{ftop}）" if ftop else ""), lvl,
        "删掉后句子还通吗？通 → 删；不通 → 只改写，不删信息。")

    # ---- 11. 过度限定（条目 23）----
    n_hedge = 0
    for s in _sentences(text):
        c = sum(s.count(h) for h in HEDGES)
        if c >= 2:
            n_hedge += 1
    lvl = "FAIL" if n_hedge >= 4 else "WARN" if n_hedge >= 2 else "PASS"
    add("hedge", "23 过度限定", n_hedge, f"{n_hedge} 句叠加限定", lvl,
        "**限定词 >1 砍到 1，但不要砍到 0**。真实的不确定性必须保留（底线 2）。")

    # ---- 12. 对话残留（条目 19/20/21）----
    res_total, res_hits = _count_list(RESIDUE, text)
    for p in RESIDUE_RE:
        res_total += len(re.findall(p, text))
    lvl = "FAIL" if res_total >= 3 else "WARN" if res_total >= 1 else "PASS"
    rtop = "、".join(f"{w}×{c}" for w, c in res_hits.most_common(4))
    add("residue", "19/20/21 对话残留", res_total,
        f"{res_total} 处" + (f"（{rtop}）" if rtop else ""), lvl,
        "「希望这对您有帮助」「截至…」「好问题」。**删前检查**：它是否在承担「我查不到」的功能？")

    # ---- 13. 通用积极结论（条目 24）----
    tail = text[-300:]
    hits = [w for w in HAPPY_END if w in tail]
    lvl = "FAIL" if len(hits) >= 2 else "WARN" if hits else "PASS"
    add("happy", "24 通用积极结论", len(hits),
        ("命中：" + "、".join(hits)) if hits else "末段未命中", lvl,
        "结论说了任何具体的事吗？没有 → 删掉整段，让最后一个具体事实当结尾。")

    # ---- 14. 句长节奏 ----
    sents = _sentences(text)
    lens = [len(re.findall(r"[\u4e00-\u9fff]", s)) for s in sents]
    lens = [x for x in lens if x > 0]
    if len(lens) >= 6:
        mean = statistics.mean(lens)
        sd = statistics.pstdev(lens)
        cv = sd / mean if mean else 0
        lvl = "FAIL" if cv < 0.30 else "WARN" if cv < 0.45 else "PASS"
        add("rhythm", "节奏·句长变异", round(cv, 2),
            f"均值 {mean:.1f} 字 ｜ 标准差 {sd:.1f} ｜ 变异系数 {cv:.2f}", lvl,
            "变异系数 <0.30 说明句子长度高度均一，是节奏机械的信号。")
    else:
        add("rhythm", "节奏·句长变异", None, f"句数不足（{len(sents)}），跳过", "PASS",
            "样本太短，无法评估节奏。")

    # ---- 总判定（不计 advisory 项）----
    judged = [r for r in res if not r["advisory"]]
    fails = [r for r in judged if r["level"] == "FAIL"]
    warns = [r for r in judged if r["level"] == "WARN"]
    if fails:
        verdict, vlevel = f"需复核：{len(fails)} 项 FAIL、{len(warns)} 项 WARN", "FAIL"
    elif warns:
        verdict, vlevel = f"轻微提示：{len(warns)} 项 WARN", "WARN"
    else:
        verdict, vlevel = "未发现明显 AI 痕迹", "PASS"

    return {"meta": meta, "results": res, "verdict": verdict, "vlevel": vlevel}


# ---------------------------------------------------------------- 输出

ICON = {"PASS": "PASS", "WARN": "WARN", "FAIL": "FAIL"}


def render(rep, only=None, quiet=False):
    m = rep["meta"]
    out = []
    if not quiet:
        out.append("=" * 74)
        out.append("中文 AI 痕迹扫描  ·  humanizer-zh-pro v3.0.0")
        out.append(f"字数 {m['chars']}（中文 {m['cjk']}） ｜ 句数 {m['sentences']}")
        out.append("=" * 74)
        out.append(f"{'指标':<26}{'实测':<40}{'判定'}")
        out.append("-" * 74)

    for r in rep["results"]:
        if only == "fail" and r["level"] != "FAIL":
            continue
        if only == "warn" and r["level"] == "PASS":
            continue
        mark = ICON[r["level"]] + ("*" if r["advisory"] else " ")
        disp = r["display"]
        if len(disp) > 38:
            disp = disp[:37] + "…"
        out.append(f"{r['item']:<26}{disp:<40}{mark}")

    if not quiet:
        out.append("-" * 74)
        out.append(f"总判定：{rep['verdict']}   [{rep['vlevel']}]")
        out.append("")
        out.append("带 * 的项为提示项（破折号 / 三段式）：**给 WARN 也不代表要改**，")
        out.append("是否算病取决于它是否承担功能，见 SKILL.md §3 B 组。已排除在总判定之外。")
        out.append("")
        out.append("提醒：这是筛查器，不是判决器。全 PASS 仍可能是「干净但无主」的编辑腔 ——")
        out.append("      交付前请做 §4「保存你的声音」回填，并核对 §0 三条底线。")
        out.append("")
        out.append("详细说明（按需复看）：")
        for r in rep["results"]:
            if r["level"] == "PASS":
                continue
            out.append(f"  · {r['item']}：{r['note']}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(
        description="中文 AI 写作痕迹扫描器（humanizer-zh-pro v3.0.0 配套，零依赖）")
    ap.add_argument("path", help="文本文件路径，或 - 表示从标准输入读取")
    ap.add_argument("--only", choices=["all", "fail", "warn"], default="all",
                    help="只显示 FAIL / WARN 项")
    ap.add_argument("--json", dest="as_json", action="store_true", help="输出 JSON")
    ap.add_argument("--quiet", action="store_true", help="不打印表头与说明")
    args = ap.parse_args()

    # Windows 控制台 UTF-8 兜底
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if args.path == "-":
        raw = sys.stdin.read()
    else:
        try:
            with open(args.path, "r", encoding="utf-8", errors="replace") as f:
                raw = f.read()
        except OSError as e:
            print(f"读取失败：{e}", file=sys.stderr)
            print("提示：路径含空格请加引号；也可用管道 cat 文件 | python check_tells.py -",
                  file=sys.stderr)
            return 2

    if not raw.strip():
        print("输入为空，无内容可扫描。", file=sys.stderr)
        return 2

    rep = analyze(raw)

    if args.as_json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print(render(rep, only=None if args.only == "all" else args.only,
                     quiet=args.quiet))

    return 1 if rep["vlevel"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
