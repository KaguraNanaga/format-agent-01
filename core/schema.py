# FormatSpec 校验器 —— 全系统的核心契约守门员。
# 规则（PLAN.md 第 4 节）：
#   - roles.body 必填；每个角色字段齐全（font_eastasia、size_pt、alignment 至少）
#   - 数值边界：size_pt ∈ [8,72]、margin ∈ [5,50]mm、first_line_indent_chars ∈ [0,8]
#   - 非法输出带校验错误回喂 LLM 重试（由调用方负责重试）

# 角色 Base 闭集；规范文字可自定义角色键（执行器对未知角色按 other 处理），
# 所以这里只对 Base 角色做提示，不拒绝未知键。
BASE_ROLES = [
    "title", "subtitle", "heading_1", "heading_2", "heading_3",
    "body", "signature", "date", "attachment_label", "attachment", "other",
]

ROLE_REQUIRED_FIELDS = ["font_eastasia", "size_pt", "alignment"]

ALIGNMENTS = {"left", "center", "right", "justify"}

SIZE_PT_RANGE = (8, 72)
MARGIN_MM_RANGE = (5, 50)
INDENT_CHARS_RANGE = (0, 8)


class SpecValidationError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("FormatSpec 校验失败:\n" + "\n".join(f"- {e}" for e in errors))


def validate_spec(spec):
    """校验 FormatSpec dict。合法返回 None；非法抛 SpecValidationError（带全部错误）。"""
    errors = []
    if not isinstance(spec, dict):
        raise SpecValidationError(["顶层必须是 JSON object"])

    # ---- page ----
    page = spec.get("page")
    if page is not None:
        if not isinstance(page, dict):
            errors.append("page 必须是 object")
        else:
            margin = page.get("margin")
            if margin is not None:
                if not isinstance(margin, dict):
                    errors.append("page.margin 必须是 object")
                else:
                    for k in ("top_mm", "bottom_mm", "left_mm", "right_mm"):
                        v = margin.get(k)
                        if v is None:
                            continue
                        if not _is_num(v) or not (MARGIN_MM_RANGE[0] <= v <= MARGIN_MM_RANGE[1]):
                            errors.append(
                                f"page.margin.{k}={v!r} 非法：必须是 {MARGIN_MM_RANGE[0]}~{MARGIN_MM_RANGE[1]} 毫米的数值")
            line_grid = page.get("line_grid")
            if line_grid is not None:
                if not isinstance(line_grid, dict):
                    errors.append("page.line_grid 必须是 object")
                else:
                    v = line_grid.get("line_pt")
                    if v is not None and (not _is_num(v) or not (8 <= v <= 72)):
                        errors.append(f"page.line_grid.line_pt={v!r} 非法：必须是 8~72 磅的数值")

    # ---- roles ----
    roles = spec.get("roles")
    if not isinstance(roles, dict) or not roles:
        errors.append("roles 必须是非空 object")
    else:
        if "body" not in roles:
            errors.append("roles.body 必填（正文角色是兜底）")
        for role, rule in roles.items():
            if not isinstance(rule, dict):
                errors.append(f"roles.{role} 必须是 object")
                continue
            for f in ROLE_REQUIRED_FIELDS:
                if f not in rule:
                    errors.append(f"roles.{role} 缺少必填字段 {f}")
            v = rule.get("size_pt")
            if v is not None and (not _is_num(v) or not (SIZE_PT_RANGE[0] <= v <= SIZE_PT_RANGE[1])):
                errors.append(f"roles.{role}.size_pt={v!r} 非法：必须是 {SIZE_PT_RANGE[0]}~{SIZE_PT_RANGE[1]} 磅")
            v = rule.get("alignment")
            if v is not None and v not in ALIGNMENTS:
                errors.append(f"roles.{role}.alignment={v!r} 非法：必须是 {sorted(ALIGNMENTS)} 之一")
            v = rule.get("first_line_indent_chars")
            if v is not None and (not _is_num(v) or not (INDENT_CHARS_RANGE[0] <= v <= INDENT_CHARS_RANGE[1])):
                errors.append(
                    f"roles.{role}.first_line_indent_chars={v!r} 非法：必须是 {INDENT_CHARS_RANGE[0]}~{INDENT_CHARS_RANGE[1]} 字符")
            ls = rule.get("line_spacing")
            if ls is not None:
                if not isinstance(ls, dict) or ls.get("type") not in ("exact", "multiple") or not _is_num(ls.get("pt")):
                    errors.append(f'roles.{role}.line_spacing 非法：必须是 {{"type": "exact"|"multiple", "pt": 数值}}')

    if errors:
        raise SpecValidationError(errors)


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)
