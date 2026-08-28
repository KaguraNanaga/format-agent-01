# 执行器接线（PLAN.md 第 7 节）：
# apply_format(docx_path, spec, rolemap, out_path) -> changelog
# 对每个段落按 RoleMap 取角色、从 FormatSpec 取规则，调用 core/executor.py 的
# 确定性函数改 XML；页边距/行网格走 section 级别。LLM 不碰 docx。

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Mm

from core.executor import (
    set_doc_grid,
    set_first_line_indent_chars,
    set_paragraph_fixed_spacing,
    set_run_fonts,
)

_ALIGNMENT = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
}


def _apply_role_to_paragraph(p, rule):
    """把一个角色的规则套到段落上，返回实际改动的字段列表。"""
    changed = []
    # 1) 字体/字号/加粗：套到每个 run（没有 run 的空段落跳过字体设置）
    font_kwargs = {}
    if rule.get("font_eastasia"):
        font_kwargs["eastasia"] = rule["font_eastasia"]
    if rule.get("font_ascii"):
        font_kwargs["ascii_font"] = rule["font_ascii"]
    if rule.get("size_pt") is not None:
        font_kwargs["size_pt"] = rule["size_pt"]
    if rule.get("bold") is not None:
        font_kwargs["bold"] = rule["bold"]
    if font_kwargs and p.runs:
        for run in p.runs:
            set_run_fonts(run, **font_kwargs)
        changed.extend(k for k in ("font_eastasia", "font_ascii", "size_pt", "bold") if rule.get(k) is not None)
    # 2) 对齐
    if rule.get("alignment") in _ALIGNMENT:
        p.alignment = _ALIGNMENT[rule["alignment"]]
        changed.append("alignment")
    # 3) 行距
    ls = rule.get("line_spacing")
    if isinstance(ls, dict) and ls.get("pt") is not None:
        if ls.get("type") == "exact":
            set_paragraph_fixed_spacing(p, line_pt=ls["pt"])
        else:  # multiple：python-docx 原生多倍行距
            p.paragraph_format.line_spacing = float(ls["pt"])
        changed.append("line_spacing")
    # 4) 首行缩进（按字符）
    if rule.get("first_line_indent_chars") is not None:
        set_first_line_indent_chars(p, rule["first_line_indent_chars"])
        changed.append("first_line_indent_chars")
    return changed


def apply_format(docx_path, spec, rolemap, out_path):
    """应用 FormatSpec × RoleMap，输出 docx，返回 changelog list[dict]。
    rolemap: {idx: role}（idx 对应 extract.py 的段落序号）。
    未知角色按 other 处理（有 other 规则则套用，否则保留原格式）。
    表格内段落（idx >= len(doc.paragraphs)）v1 跳过。
    """
    doc = Document(docx_path)
    roles = spec.get("roles", {})
    fallback = roles.get("other")

    # ---- 页面级 ----
    page = spec.get("page") or {}
    margin = page.get("margin") or {}
    section = doc.sections[0]
    if margin.get("top_mm") is not None:
        section.top_margin = Mm(margin["top_mm"])
    if margin.get("bottom_mm") is not None:
        section.bottom_margin = Mm(margin["bottom_mm"])
    if margin.get("left_mm") is not None:
        section.left_margin = Mm(margin["left_mm"])
    if margin.get("right_mm") is not None:
        section.right_margin = Mm(margin["right_mm"])
    line_grid = page.get("line_grid") or {}
    if line_grid.get("line_pt") is not None:
        set_doc_grid(doc, line_pt=line_grid["line_pt"])

    # ---- 段落级 ----
    changelog = []
    for idx, p in enumerate(doc.paragraphs):
        role = rolemap.get(idx)
        if role is None:
            continue  # 未被标注的段落不动
        rule = roles.get(role, fallback)
        if rule is None:
            continue  # unknown role 且无 other 规则：保留原格式
        changed = _apply_role_to_paragraph(p, rule)
        changelog.append({
            "idx": idx,
            "role": role,
            "text": p.text.strip()[:30],
            "changed_fields": changed,
        })

    doc.save(out_path)
    return changelog


def write_report(changelog, spec, report_path):
    """把 changelog 写成 markdown 修改对照报告。"""
    lines = ["# 排版修改对照报告", ""]
    page = spec.get("page") or {}
    if page:
        lines.append("## 页面设置")
        margin = page.get("margin") or {}
        if margin:
            lines.append(
                f"- 页边距（mm）：上 {margin.get('top_mm', '-')} / 下 {margin.get('bottom_mm', '-')}"
                f" / 左 {margin.get('left_mm', '-')} / 右 {margin.get('right_mm', '-')}")
        lg = page.get("line_grid") or {}
        if lg.get("line_pt"):
            lines.append(f"- 行网格：{lg['line_pt']} 磅/行")
        lines.append("")
    lines.append("## 段落修改明细")
    lines.append("")
    lines.append("| 段落 | 角色 | 改动字段 | 内容摘要 |")
    lines.append("|---|---|---|---|")
    for c in changelog:
        fields = ", ".join(c["changed_fields"]) if c["changed_fields"] else "（无字段改动）"
        lines.append(f"| {c['idx']} | {c['role']} | {fields} | {c['text']} |")
    lines.append("")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return report_path
