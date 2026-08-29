# 视觉验证（PLAN.md 6.3 + 第 9 节第 1 条）：
# render.py 渲染输出 docx → 6.3 prompt 送视觉模型 → 结构化问题清单
# [{role, field, pass, observed, expected}] → 代码只改 FormatSpec 对应字段，重跑一次。
# 不做开放循环：最多一轮定向修复。

import json
import os
import re

from core.render import render_docx_to_png
from core.schema import SpecValidationError, validate_spec

PROMPT_TEMPLATE = """你是排版质检员。对照检查清单逐条检查这份文档的渲染图。
检查清单（来自排版规范）：
{checklist}
输出严格 JSON: [{{"role": "...", "field": "...", "pass": true/false,
"observed": "图上看到的实际值", "expected": "清单要求值"}}]。只输出有把握判断的项。"""

# 可自动修复的数值字段：issue.field -> (spec 内的取值路径, 合法范围)
_FIXABLE_NUMERIC = {
    "size_pt": (8, 72),
    "line_spacing.pt": (8, 72),
    "first_line_indent_chars": (0, 8),
}
_FIXABLE_ALIGN = {"left", "center", "right", "justify"}


def _build_checklist(spec):
    """把 FormatSpec 展开成人话检查清单。"""
    lines = []
    page = spec.get("page") or {}
    margin = page.get("margin") or {}
    if margin:
        lines.append(
            f"- 页面: 页边距 上{margin.get('top_mm')}/下{margin.get('bottom_mm')}"
            f"/左{margin.get('left_mm')}/右{margin.get('right_mm')} 毫米")
    lg = page.get("line_grid") or {}
    if lg.get("line_pt"):
        lines.append(f"- 页面: 行网格每行 {lg['line_pt']} 磅")
    for role, rule in (spec.get("roles") or {}).items():
        parts = []
        if rule.get("font_eastasia"):
            parts.append(f"中文字体 {rule['font_eastasia']}")
        if rule.get("size_pt"):
            parts.append(f"字号 {rule['size_pt']} 磅")
        if rule.get("bold") is not None:
            parts.append("加粗" if rule["bold"] else "不加粗")
        if rule.get("alignment"):
            parts.append(f"对齐 {rule['alignment']}")
        if rule.get("first_line_indent_chars"):
            parts.append(f"首行缩进 {rule['first_line_indent_chars']} 字符")
        if rule.get("space_before_pt"):
            parts.append(f"段前 {rule['space_before_pt']} 磅")
        if rule.get("space_after_pt"):
            parts.append(f"段后 {rule['space_after_pt']} 磅")
        ls = rule.get("line_spacing") or {}
        if ls.get("pt"):
            parts.append(f"行距 {'固定值' if ls.get('type') == 'exact' else '倍数'} {ls['pt']} 磅")
        if parts:
            lines.append(f"- 角色 {role}: " + "，".join(parts))
    return "\n".join(lines)


def _validate_issues(items):
    """宽松校验 VLM 输出：只留结构完整的条目。"""
    out = []
    if not isinstance(items, list):
        return out
    for it in items:
        if isinstance(it, dict) and "role" in it and "field" in it and "pass" in it:
            out.append({
                "role": str(it["role"]),
                "field": str(it["field"]),
                "pass": bool(it["pass"]),
                "observed": str(it.get("observed", "")),
                "expected": str(it.get("expected", "")),
            })
    return out


def verify_visual(docx_path, spec, llm, png_dir):
    """渲染 + VLM 质检，返回结构化问题清单（全部检查项，含 pass=true）。"""
    pages = render_docx_to_png(docx_path, png_dir)
    prompt = PROMPT_TEMPLATE.format(checklist=_build_checklist(spec))
    items = llm.chat_vision_json(prompt, pages)
    return _validate_issues(items)


def _parse_number(text):
    m = re.search(r"-?\d+(?:\.\d+)?", str(text))
    return float(m.group()) if m else None


def apply_fixes(spec, issues):
    """定向修复：只改 FormatSpec 里与失败项对应的字段，且仅在 observed 可解析、
    数值在合法范围内时动手。返回 (修复后的 spec, 实际应用的修复列表)。
    修完过一遍 schema 校验，修坏了就放弃自动修复、返回原 spec。
    """
    fixed = json.loads(json.dumps(spec))  # deep copy
    applied = []
    for it in issues:
        if it["pass"]:
            continue
        role, field = it["role"], it["field"]
        rule = (fixed.get("roles") or {}).get(role)
        if rule is None:
            continue
        if field in _FIXABLE_NUMERIC:
            lo, hi = _FIXABLE_NUMERIC[field]
            v = _parse_number(it["observed"])
            if v is None or not (lo <= v <= hi):
                continue
            if field == "line_spacing.pt":
                ls = rule.get("line_spacing")
                if isinstance(ls, dict):
                    ls["pt"] = v
                else:
                    continue
            else:
                rule[field] = v
            applied.append(it)
        elif field == "alignment" and it["observed"] in _FIXABLE_ALIGN:
            rule["alignment"] = it["observed"]
            applied.append(it)
    if applied:
        try:
            validate_spec(fixed)
        except SpecValidationError:
            return spec, []  # 修坏了，回退
    return fixed, applied


if __name__ == "__main__":
    import sys
    from core.llm import LLMClient
    with open(sys.argv[2], encoding="utf-8") as f:
        spec = json.load(f)
    issues = verify_visual(sys.argv[1], spec, LLMClient(), png_dir="out/verify_render")
    print(json.dumps(issues, ensure_ascii=False, indent=2))
