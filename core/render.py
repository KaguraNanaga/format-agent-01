# 渲染管线冒烟脚本 —— 在本机先跑通, 别到现场才试。
# 你的机器: Word COM 可用 (Office16), LibreOffice 不可用 -> 走 Word COM。
# 输出: docx -> PDF -> PNG, 供视觉验证/视觉读模板用。
#
# 环境要求: pywin32 (pip install pywin32)。python-docx 1.2.0 已装。
# 若现场没有 Word, 退回 LibreOffice headless, 需提前在赛前机器装好。
# 本脚本在 "python" 下纯 python-docx + win32com, 只依赖 docx + comtypes/pywin32。

import os
import sys
import tempfile


def docx_to_pdf_word_com(docx_path, pdf_path):
    """用 Word COM 导出 PDF。这是 Windows 上最可靠的路径。"""
    import win32com.client
    # DispatchEx 强制启动新的 Word 实例——绝不附着到用户正在用的 Word,
    # 否则 finally 里的 Quit() 会把用户自己打开的文档一起关掉。
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = False
    try:
        doc = word.Documents.Open(
            os.path.abspath(docx_path), ReadOnly=True, ConfirmConversions=False
        )
        # 导出为 PDF (wdFormatPDF = 17)
        doc.SaveAs2(os.path.abspath(pdf_path), FileFormat=17)
        doc.Close()
    finally:
        word.Quit()
    return pdf_path


def pdf_to_png(pdf_path, png_dir, dpi=150):
    """PDF 转 PNG (逐页)。用 fitz (PyMuPDF) 或 pymupdf。备选: pdfium / pdf2image。
    优先 fitz, 没装则降级为 pymupdf。
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        try:
            import pymupdf as fitz
        except ImportError:
            raise RuntimeError("需要安装 PyMuPDF: pip install PyMuPDF")
    pages = []
    pdf = fitz.open(pdf_path)
    for i, page in enumerate(pdf):
        pix = page.get_pixmap(dpi=dpi)
        png_path = os.path.join(png_dir, f"page_{i:02d}.png")
        pix.save(png_path)
        pages.append(png_path)
    pdf.close()
    return pages


def render_docx_to_png(docx_path, png_dir, dpi=150):
    """一键: docx -> pdf -> png 列表。"""
    os.makedirs(png_dir, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "out.pdf")
        docx_to_pdf_word_com(docx_path, pdf_path)
        return pdf_to_png(pdf_path, png_dir, dpi)


if __name__ == "__main__":
    # 冒烟: 用你手边任意一个 docx 试跑, 无误再进主流程。
    if len(sys.argv) < 2:
        print("用法: python hackathon-render.py <某个docx路径>")
        sys.exit(1)
    src = sys.argv[1]
    png_dir = "recon_render_test"
    pages = render_docx_to_png(src, png_dir)
    print(f"渲染成功: {len(pages)} 页 -> {png_dir}/page_*.png")
