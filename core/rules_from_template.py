# 模板 docx → FormatSpec（格式源第二种，确定性读取，不依赖 VLM）。
# 思路：给定模板的 RoleMap，为每个角色找代表段落，用 effective_props 读生效
# 字体/字号/加粗，用 python-docx 读对齐/行距/缩进，页面级读 section 页边距和行网格。
# 未知/读不到的字段不编——留给 LLM 规范抽取或人肉 JSON 补。

from docx import Document
from docx.enum.text import WD_LINE_SPACING
from docx.oxml.ns import qn

from core.effective_props import effective_props
from core.schema import validate_spec

_ALIGN_MAP = {0: "left", 1: "center", 2: "right", 3: "justify"}


def _para_alignment(p):
    a = p.alignment
    if a is None:
        return None
    return _ALIGN_MAP.get(int(a))


def _para_line_spacing(p):
    pf = p.paragraph_format
    rule = pf.line_spacing_rule
    if rule is None or pf.line_spacing is None:
        return None
    if rule == WD_LINE_SPACING.EXACTLY:
        return {"type": "exact", "pt": round(pf.line_spacing.pt, 1)}
    if rule == WD_LINE_SPACING.MULTIPLE:
        # 多倍行距：line_spacing 是浮点倍数
        return {"type": "multiple", "pt": round(float(pf.line_spacing), 2)}
    return None


def _para_indent_chars(p, size_pt):
    """首行缩进字符数：优先读 XML firstLineChars，否则用磅值/字号反推。"""
    ppr = p._p.pPr
    if ppr is not None:
        ind = ppr.find(qn("w:ind"))
        if ind is not None:
            flc = ind.get(qn("w:firstLineChars"))
            if flc:
                return round(int(flc) / 100, 1)
    fl = p.paragraph_format.first_line_indent
    if fl is not None and size_pt:
        return round(fl.pt / size_pt, 1)
    return None


def _page_section(doc):
    page = {}
    s = doc.sections[0]
    margin = {
        "top_mm": round(s.top_margin.mm, 1),
        "bottom_mm": round(s.bottom_margin.mm, 1),
        "left_mm": round(s.left_margin.mm, 1),
        "right_mm": round(s.right_margin.mm, 1),
    }
    if all(v is not None for v in margin.values()):
        page["margin"] = margin
    doc_grid = s._sectPr.find(qn("w:docGrid"))
    if doc_grid is not None and doc_grid.get(qn("w:linePitch")):
        page["line_grid"] = {"line_pt": round(int(doc_grid.get(qn("w:linePitch"))) / 20, 1)}
    return page


def extract_rules_from_template(template_path, rolemap):
    """模板 docx + RoleMap → FormatSpec（经 schema 校验）。
    rolemap: {idx: role}。每个角色取第一个代表段落读格式。
    要求 rolemap 里至少有 body 角色，否则抛 ValueError。
    """
    doc = Document(template_path)
    paras = doc.paragraphs
    roles = {}
    for idx, role in sorted(rolemap.items()):
        if role in roles or idx >= len(paras):
            continue  # 每个角色只取第一个代表段
        p = paras[idx]
        props = effective_props(p)
        eastasia = props.get("eastasia") or "宋体"
        size_pt = props.get("size_pt") or 10.5
        rule = {"font_eastasia": eastasia, "size_pt": size_pt,
                "bold": bool(props.get("bold"))}
        if props.get("ascii"):
            rule["font_ascii"] = props["ascii"]
        a = _para_alignment(p)
        if a:
            rule["alignment"] = a
        ls = _para_line_spacing(p)
        if ls:
            rule["line_spacing"] = ls
        flc = _para_indent_chars(p, size_pt)
        if flc:
            rule["first_line_indent_chars"] = flc
        pf = p.paragraph_format
        if pf.space_before is not None:
            rule["space_before_pt"] = round(pf.space_before.pt, 1)
        if pf.space_after is not None:
            rule["space_after_pt"] = round(pf.space_after.pt, 1)
        roles[role] = rule

    if "body" not in roles:
        raise ValueError("模板中没有标注 body 角色的段落，无法确定正文格式")
    # schema 要求每个角色至少有 alignment；读不到时给合理默认
    for role, rule in roles.items():
        rule.setdefault("alignment", "justify" if role == "body" else "left")

    spec = {"page": _page_section(doc), "roles": roles}
    # 行网格一致性：模板里的 docGrid 常是 Word 默认值（如 15.6pt），与正文实际
    # 固定行距不一致时，网格会干扰排版。正文有明确固定行距时，以正文行距为准。
    body_ls = (roles.get("body") or {}).get("line_spacing") or {}
    if body_ls.get("type") == "exact" and body_ls.get("pt"):
        grid = spec["page"].setdefault("line_grid", {})
        if grid.get("line_pt") != body_ls["pt"]:
            grid["line_pt"] = body_ls["pt"]
    validate_spec(spec)
    return spec


if __name__ == "__main__":
    import json
    import sys
    with open(sys.argv[2], encoding="utf-8") as f:
        rolemap = {int(k): v for k, v in json.load(f).items()}
    spec = extract_rules_from_template(sys.argv[1], rolemap)
    print(json.dumps(spec, ensure_ascii=False, indent=2))
