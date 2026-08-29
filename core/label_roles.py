# 段落清单 → RoleMap（PLAN.md 6.2 prompt）。
# label_roles(paragraphs, llm) -> dict[int, str]；每 40 段一批；
# 校验 role ∈ 枚举、idx 全覆盖；失败重试 <=2 次。

import json
import re

from core.schema import BASE_ROLES

BATCH_SIZE = 40

# 中文公文标题编号惯例（确定性识别，不走 LLM，解决二级标题识别不稳）：
#   一、    → heading_1    （一）  → heading_2    1. 或 1、 → heading_3
# 图表题注（论文/招股书类文档）：
#   图1 xxx / 图 2-1 xxx → figure_caption    表1 xxx / 表 2-1 xxx → table_caption
# 仅当行较短且不以句读结尾时才认定为标题（正文句也可能以"一、"开头）。
_HEADING_PATTERNS = [
    (re.compile(r"^图\s*\d+([-.]\d+)?"), "figure_caption"),
    (re.compile(r"^表\s*\d+([-.]\d+)?"), "table_caption"),
    (re.compile(r"^[一二三四五六七八九十百]+、"), "heading_1"),
    (re.compile(r"^[（(][一二三四五六七八九十]+[）)]"), "heading_2"),
    (re.compile(r"^\d{1,2}[.、]"), "heading_3"),
]
_HEADING_MAX_LEN = 40


def regex_role(text):
    """按编号惯例识别标题角色；无把握返回 None（交给 LLM）。"""
    t = text.strip()
    if not t or len(t) > _HEADING_MAX_LEN:
        return None
    if t.endswith(("。", "；", ";", "，", ",", "：", ":")):
        return None
    for pat, role in _HEADING_PATTERNS:
        if pat.match(t):
            return role
    return None

PROMPT_TEMPLATE = """你是文档结构标注器。给每一段标注角色，角色只能从枚举里选:
{roles}。
判断依据: 文字内容、位置顺序、当前格式提示。落款单位通常在末尾、署名感强;
日期含"年/月/日"; 标题通常在最前且独立成行。
中文标题层级惯例: "一、"开头多为一级标题(heading_1)，"（一）"开头多为二级标题
(heading_2)，"1."或"1、"开头多为三级标题(heading_3)；标题行通常较短且不以句号结尾。
"图1 xxx"/"图2-1 xxx"这类独立成行的是图片题注(figure_caption)，"表1 xxx"是表格题注
(table_caption)。
输入是 JSON 数组 [{{idx, text, size_pt, bold, alignment, space_before_pt,
space_after_pt}}]（后两个是段前/段后距磅值，null 表示未设置；标题段落常与正文之间
有明显间距，可作辅助判断），
输出严格为 {{"roles": [{{"idx": 0, "role": "title"}}, ...]}} 的 JSON 对象，
roles 数组必须覆盖所有输入 idx，不多不少。
段落清单：
{paragraphs}"""

RETRY_SUFFIX = """
你上一次的输出校验未通过，错误：{error}
请重新输出完整 JSON 数组，必须恰好覆盖这些 idx: {idx_list}。"""

_ROLE_SET = set(BASE_ROLES)


def _validate_rolemap(items, expected_idxs):
    """校验 LLM 输出：结构、role 合法、idx 恰好全覆盖。返回 dict[int,str] 或抛 ValueError。
    兼容两种形态：裸数组 [...]（老 prompt），或包一层对象 {"roles": [...]}（JSON 模式友好）。
    """
    if isinstance(items, dict):
        # 优先认 "roles" 键，其次取第一个 list 类型的值
        if isinstance(items.get("roles"), list):
            items = items["roles"]
        else:
            for v in items.values():
                if isinstance(v, list):
                    items = v
                    break
    if not isinstance(items, list):
        raise ValueError("输出必须是 JSON 数组或含数组的 JSON 对象")
    rolemap = {}
    for it in items:
        if not isinstance(it, dict) or "idx" not in it or "role" not in it:
            raise ValueError(f"数组元素必须是 {{idx, role}} 对象，收到: {it!r}")
        idx, role = it["idx"], it["role"]
        if role not in _ROLE_SET:
            raise ValueError(f"非法角色 {role!r}（idx={idx}）")
        rolemap[idx] = role
    got, want = set(rolemap), set(expected_idxs)
    if got != want:
        missing = sorted(want - got)
        extra = sorted(got - want)
        raise ValueError(f"idx 覆盖不符：缺少 {missing}，多出 {extra}")
    return rolemap


def _label_batch(batch, llm, max_retries=2, on_event=None):
    on_event = on_event or (lambda msg: None)
    expected = [p["idx"] for p in batch]
    payload = json.dumps(
        [{k: p[k] for k in ("idx", "text", "size_pt", "bold", "alignment",
                            "space_before_pt", "space_after_pt")} for p in batch],
        ensure_ascii=False)
    prompt = PROMPT_TEMPLATE.format(roles="/".join(BASE_ROLES), paragraphs=payload)
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            items = llm.chat_json(prompt)
            return _validate_rolemap(items, expected)
        except (ValueError, KeyError, TypeError) as e:
            last_err = e
            if attempt < max_retries:
                on_event(f"角色标注未通过校验（{e}），正在要求模型重标")
                prompt = (PROMPT_TEMPLATE.format(roles="/".join(BASE_ROLES), paragraphs=payload)
                          + RETRY_SUFFIX.format(error=e, idx_list=expected))
    raise ValueError(f"角色标注失败（重试 {max_retries} 次后放弃）: {last_err}")


def label_roles(paragraphs, llm, on_event=None):
    """整篇段落清单 → {idx: role}。表格内段落（in_table=True）不送标注，直接标 other。"""
    on_event = on_event or (lambda msg: None)
    rolemap = {}
    todo = []
    for p in paragraphs:
        if p.get("in_table"):
            rolemap[p["idx"]] = "other"
            continue
        hit = regex_role(p.get("text", ""))
        if hit:
            rolemap[p["idx"]] = hit  # 编号惯例命中的标题：确定性识别，不送 LLM
        else:
            todo.append(p)
    if rolemap:
        on_event(f"编号惯例直接识别 {len(rolemap)} 段（含表格跳过），其余 {len(todo)} 段送模型标注")
    n_batches = (len(todo) + BATCH_SIZE - 1) // BATCH_SIZE
    for i in range(0, len(todo), BATCH_SIZE):
        batch_no = i // BATCH_SIZE + 1
        if n_batches > 1:
            on_event(f"标注第 {batch_no}/{n_batches} 批段落（{len(todo[i:i + BATCH_SIZE])} 段）")
        rolemap.update(_label_batch(todo[i:i + BATCH_SIZE], llm, on_event=on_event))
    return rolemap


if __name__ == "__main__":
    import sys
    from core.extract import extract_paragraphs
    from core.llm import LLMClient
    paras = extract_paragraphs(sys.argv[1])
    rm = label_roles(paras, LLMClient())
    print(json.dumps(rm, ensure_ascii=False, indent=2))
