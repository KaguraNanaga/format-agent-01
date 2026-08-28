# docx → 段落清单（PLAN.md 第 7 节）。
# 每段输出 {idx, text(截前80字), size_pt, bold, alignment, style_name, in_table}。
# size_pt/bold 用 effective_props 读"生效属性"而非样式名。
# in_table=True 的段落 v1 不参与重排，但仍列出（供角色标注参考上下文）。

from docx import Document

from core.effective_props import get_paragraph_effective_font

_ALIGN_MAP = {0: "left", 1: "center", 2: "right", 3: "justify"}


def _alignment_name(paragraph):
    a = paragraph.alignment
    if a is None:
        return None
    return _ALIGN_MAP.get(int(a), str(a))


def extract_paragraphs(docx_path):
    """返回段落清单 list[dict]，idx 为全文段落序号（含表格内段落）。"""
    doc = Document(docx_path)
    out = []
    for idx, p in enumerate(doc.paragraphs):
        eastasia, size_pt, bold = get_paragraph_effective_font(p)
        out.append({
            "idx": idx,
            "text": p.text.strip()[:80],
            "size_pt": size_pt,
            "bold": bold,
            "alignment": _alignment_name(p),
            "style_name": p.style.name if p.style is not None else None,
            "in_table": False,
        })
    # 表格段落追加在末尾（doc.paragraphs 不含表格内段落，单独列出）
    idx = len(out)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    eastasia, size_pt, bold = get_paragraph_effective_font(p)
                    out.append({
                        "idx": idx,
                        "text": p.text.strip()[:80],
                        "size_pt": size_pt,
                        "bold": bold,
                        "alignment": _alignment_name(p),
                        "style_name": p.style.name if p.style is not None else None,
                        "in_table": True,
                    })
                    idx += 1
    return out


if __name__ == "__main__":
    import json
    import sys
    paras = extract_paragraphs(sys.argv[1])
    print(json.dumps(paras, ensure_ascii=False, indent=2))
