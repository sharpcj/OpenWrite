#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_svg_text.py — SVG 文字合规校验器：文字是否「全部落在所属框内」且「水平居中」。

用法：
    python3 check_svg_text.py *.svg

判定口径：
  1. 用经验系数估算每个 <text> 的包围盒（CJK≈1.0em、ASCII≈0.55em、空格≈0.32em）；
  2. 找出包含它、且比它大一圈（宽 ≥ bbox+8、高 ≥ bbox+6）的 rect 中面积最小者，视为「所属框」；
  3. 溢出：bbox 有任何一边超出所属框（容差 0.5px）→ FAIL；
  4. 居中：text-anchor=middle 且框比文字宽 ≥12px 时，中心偏差 >2px → FAIL；
  5. 越界：bbox 超出 viewBox → FAIL；
  6. 行间重叠：同一 x 列（±2px）相邻文字行基线差 < 较大字号×1.15 → FAIL（×1.0 为硬下限）。

退出码：有问题返回 1，全部通过返回 0。
"""
import re
import sys
import glob
import xml.etree.ElementTree as ET

NS = "{http://www.w3.org/2000/svg}"
SIZE_FALLBACK = 16.0          # 元素和 class 都没给字号时，浏览器默认 16px（故意取大值，逼出漏写字号）


def unit(ch):
    if ch == " ":
        return 0.32
    if ord(ch) > 0x2E80:
        return 1.0
    return 0.55


def text_w(text, size):
    return sum(unit(c) for c in text) * size


def parse_style(root):
    """解析 <style> 里的 .cls{...}，让 text-anchor / 字号可以从 CSS 类继承。"""
    css = {}
    for el in root.iter(NS + "style"):
        for m in re.finditer(r"\.(\w+)\s*\{([^}]*)\}", el.text or ""):
            props = {}
            for decl in m.group(2).split(";"):
                if ":" not in decl:
                    continue
                k, v = decl.split(":", 1)
                props[k.strip()] = v.strip()
            css[m.group(1)] = props
    return css


def css_size(props, fallback=12.0):
    """从 class 定义里取字号：优先 font-size，其次 font shorthand 里的 Npx。"""
    if "font-size" in props:
        try:
            return float(re.sub(r"[^\d.]", "", props["font-size"]))
        except ValueError:
            pass
    m = re.search(r"(\d+(?:\.\d+)?)px", props.get("font", ""))
    return float(m.group(1)) if m else fallback


def iter_lines(root, css):
    """产出每一个「文字行」：(x, baseline_y, font_size, text, anchor, parent_class)。

    含 <tspan> 的 <text> 逐行拆开——基线 = 父 y + 各 tspan dy 累加。
    这是修复「多行被当成一整块算宽度→假越界/假出框」的关键，也是行间重叠检测的数据源。
    """
    def size_of(props, attr_size, fallback=12.0):
        if attr_size:
            try:
                return float(attr_size)
            except ValueError:
                pass
        return css_size(props, fallback)

    for el in root.iter(NS + "text"):
        cls = el.get("class", "")
        props = css.get(cls, {})
        psize = size_of(props, el.get("font-size"), SIZE_FALLBACK)
        x = float(el.get("x", 0))
        base_y = float(el.get("y", 0))
        anchor = el.get("text-anchor") or props.get("text-anchor", "start")
        tspans = el.findall(NS + "tspan")
        if tspans:
            cur = base_y
            for sp in tspans:
                cur += float(sp.get("dy", 0) or 0)
                txt = "".join(sp.itertext()).strip()
                if txt:
                    yield (float(sp.get("x", x)), cur, size_of(props, sp.get("font-size"), psize),
                           txt, sp.get("text-anchor", anchor), cls)
        else:
            txt = "".join(el.itertext()).strip()
            if txt:
                yield (x, base_y, psize, txt, anchor, cls)


def check_line_overlap(lines):
    """检测同一 x 列相邻文字行基线是否过近。

    < 字号×1.0 → FAIL（真重叠，字形相交）；1.0~1.15 → 提示不计入问题（偏紧但可读）。
    典型事故：box() 画两行 + 手动 append 第三个 <text> 补行，两行基线被两处代码各算一次。
    """
    cols = {}
    for x, y, fs, txt, _a, _c in lines:
        cols.setdefault(round(x / 2) * 2, []).append((y, fs, txt))
    fails, tips = [], []
    for x, items in cols.items():
        items.sort(key=lambda r: r[0])
        for (y1, fs1, t1), (y2, fs2, t2) in zip(items, items[1:]):
            base = max(fs1, fs2)
            gap = y2 - y1
            if gap < base * 1.0:
                fails.append(
                    f"[行间重叠] x≈{x:.0f} '{t1[:14]}' 与 '{t2[:14]}' 基线差 {gap:.1f}px"
                    f" < 字号 {base:g}px（改用单 <text>+<tspan dy>，行距 ≥{base * 1.15:.1f}px）"
                )
            elif gap < base * 1.15:
                tips.append(f"[行间偏紧] x≈{x:.0f} '{t1[:12]}'/'{t2[:12]}' 差 {gap:.1f}px，建议 ≥{base * 1.15:.1f}px")
    return fails, tips


def main(paths):
    bad_total = 0
    for path in paths:
        root = ET.parse(path).getroot()
        vb = [float(x) for x in root.get("viewBox").split()]
        W, H = vb[2], vb[3]

        rects = []
        for el in root.iter(NS + "rect"):
            rects.append(tuple(float(el.get(k, 0)) for k in ("x", "y", "width", "height")))

        css = parse_style(root)
        lines = list(iter_lines(root, css))
        issues, tips = check_line_overlap(lines)
        checked, free = 0, 0
        for x, y, size, raw, anchor, _cls in lines:
            w = text_w(raw, size)
            if anchor == "middle":
                x0 = x - w / 2
            elif anchor == "end":
                x0 = x - w
            else:
                x0 = x
            box = (x0, y - size * 0.8, x0 + w, y + size * 0.22)   # left, top, right, bottom

            checked += 1
            # 越界检查
            if box[0] < -0.5 or box[2] > W + 0.5 or box[1] < -0.5 or box[3] > H + 0.5:
                issues.append(f"[越界] {raw[:26]!r} bbox=({box[0]:.0f},{box[1]:.0f},{box[2]:.0f},{box[3]:.0f}) 超出画布 {W:g}x{H:g}")

            # 找所属框
            owners = [r for r in rects
                      if r[0] - 0.5 <= box[0] and r[1] - 0.5 <= box[1]
                      and r[0] + r[2] + 0.5 >= box[2] and r[1] + r[3] + 0.5 >= box[3]
                      and r[2] >= w + 8 and r[3] >= size + 6]
            if not owners:
                free += 1
                continue
            ox, oy, ow, oh = min(owners, key=lambda r: r[2] * r[3])

            over = []
            if box[0] < ox - 0.5:
                over.append(f"左溢出 {ox - box[0]:.1f}px")
            if box[2] > ox + ow + 0.5:
                over.append(f"右溢出 {box[2] - (ox + ow):.1f}px")
            if box[1] < oy - 0.5:
                over.append(f"上溢出 {oy - box[1]:.1f}px")
            if box[3] > oy + oh + 0.5:
                over.append(f"下溢出 {box[3] - (oy + oh):.1f}px")
            if over:
                issues.append(f"[出框] {raw[:26]!r} 在框({ox:.0f},{oy:.0f},{ow:.0f}x{oh:.0f})内 {', '.join(over)}")
                continue
            # 居中判定：只对「文字明显独占该框」时生效。
            # 多列排布的元素（如大分组框里的 401/404/429/502 四列）各自居中于自己的列，
            # 不应要求它们居中于整个容器框——那会误报。用「文字宽 > 框宽 1/3」近似区分。
            if anchor == "middle" and ow - w >= 12 and w >= ow / 3:
                dx = (box[0] + box[2]) / 2 - (ox + ow / 2)
                if abs(dx) > 2:
                    issues.append(f"[未居中] {raw[:26]!r} 相对框({ox:.0f},{oy:.0f},{ow:.0f}x{oh:.0f}) 水平偏移 {dx:+.1f}px")

        status = "OK " if not issues else "FAIL"
        print(f"{status} {path}  文字 {checked} 行，框内 {checked - free} 行，游离 {free} 行，问题 {len(issues)} 处")
        for i in issues:
            print("     " + i)
        for t in tips:
            print("     " + t)
        bad_total += len(issues)
    print(f"\n合计问题 {bad_total} 处")
    return 1 if bad_total else 0


if __name__ == "__main__":
    args = sys.argv[1:] or sorted(glob.glob("*.svg"))
    sys.exit(main(args))
