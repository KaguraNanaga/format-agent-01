# 演示界面：Agent 工作日志实时直播版。
# 演示故事："理解归 AI，动手归代码，中间用 JSON 交接" ——
# 界面直播 Agent 的每一步（理解规范→解析文档→标注角色→执行→视觉自检），
# 包括 LLM 输出校验失败后的自我修正过程。
# 运行: streamlit run app.py

import json
import os
import tempfile

import streamlit as st

from core.agent import Agent
from core.schema import validate_spec

st.set_page_config(page_title="通用格式排版 Agent", layout="wide")
st.title("🤖 通用格式排版 Agent")
st.caption("理解归 AI，动手归代码，中间用 JSON 交接")

_STATUS_ICON = {"run": "⏳", "ok": "✅", "warn": "⚠️", "err": "❌"}


def _llm_available():
    return bool(os.environ.get("LLM_BASE_URL") and os.environ.get("LLM_API_KEY")
                and os.environ.get("LLM_MODEL"))


def _save_upload(uploaded, suffix):
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(uploaded.getbuffer())
    return path


# ---------- 输入区 ----------
_DEMO_AVAILABLE = (os.path.exists("assets/spec.txt") and os.path.exists("assets/messy.docx"))
use_demo = st.checkbox("⚡ 用内置示例一键演示（assets/spec.txt + assets/messy.docx）",
                       value=False, disabled=not _DEMO_AVAILABLE)

col1, col2 = st.columns(2)
with col1:
    st.subheader("① 格式来源")
    spec_mode = st.radio("来源类型", ["规范文字", "模板 docx", "FormatSpec JSON"],
                         horizontal=True, disabled=use_demo)
    spec_text, template_file, spec_json_file = None, None, None
    if use_demo:
        with open("assets/spec.txt", encoding="utf-8") as f:
            spec_text = f.read()
        st.text_area("规范文字（内置示例）", value=spec_text, height=180, disabled=True)
    elif spec_mode == "规范文字":
        spec_text = st.text_area("粘贴排版规范文字", height=180)
    elif spec_mode == "模板 docx":
        template_file = st.file_uploader("上传模板 docx", type=["docx"], key="tpl")
    else:
        spec_json_file = st.file_uploader("上传 FormatSpec JSON", type=["json"], key="specjson")
with col2:
    st.subheader("② 待排版文档")
    target_file = None if use_demo else st.file_uploader("上传目标 docx", type=["docx"], key="target")
    if use_demo:
        st.info("目标文档：内置示例 assets/messy.docx")
    rolemap_json_file = st.file_uploader("（可选）直接给 RoleMap JSON，跳过角色标注",
                                         type=["json"], key="rolemapjson")
    verify = st.checkbox("排版后视觉自检（需视觉模型 LLM_VISION_MODEL）", value=False)

if not _llm_available():
    st.warning("未检测到 LLM 环境变量（LLM_BASE_URL/LLM_API_KEY/LLM_MODEL）。"
               "LLM 环节不可用，请改用 FormatSpec JSON / RoleMap JSON 走确定性降级链路。")

run = st.button("🚀 开始排版", type="primary",
                disabled=(target_file is None and not use_demo))

if run and (target_file is not None or use_demo):
    # ---------- Agent 工作日志（实时） ----------
    st.subheader("🧠 Agent 工作日志")
    log_lines = []
    log_box = st.empty()

    def on_event(event):
        icon = _STATUS_ICON.get(event["status"], "•")
        log_lines.append(f"{icon} **[{event['step']}]** {event['message']}")
        log_box.markdown("\n\n".join(log_lines))

    target_path = "assets/messy.docx" if use_demo else _save_upload(target_file, ".docx")
    out_dir = tempfile.mkdtemp()
    out_path = os.path.join(out_dir, "formatted.docx")
    report_path = os.path.join(out_dir, "report.md")

    try:
        kwargs = {"target_path": target_path, "out_path": out_path,
                  "report_path": report_path, "verify": verify}
        if spec_mode == "FormatSpec JSON":
            if spec_json_file is None:
                st.error("请上传 FormatSpec JSON")
                st.stop()
            kwargs["spec"] = json.loads(spec_json_file.getvalue().decode("utf-8"))
            validate_spec(kwargs["spec"])
        elif spec_mode == "模板 docx":
            if template_file is None:
                st.error("请上传模板 docx")
                st.stop()
            kwargs["template_path"] = _save_upload(template_file, ".docx")
        else:
            if not spec_text or not spec_text.strip():
                st.error("请粘贴规范文字")
                st.stop()
            kwargs["spec_text"] = spec_text
        if rolemap_json_file is not None:
            kwargs["rolemap"] = {int(k): v for k, v in
                                 json.loads(rolemap_json_file.getvalue().decode("utf-8")).items()}

        result = Agent(on_event=on_event).run(**kwargs)
    except Exception as e:  # noqa: BLE001 —— 演示界面兜底展示错误
        log_lines.append(f"❌ **[失败]** {e}")
        log_box.markdown("\n\n".join(log_lines))
        st.stop()

    # ---------- 中间产物（让评委看见"理解"） ----------
    st.subheader("📦 Agent 的思考产物（两个 JSON 交接）")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**FormatSpec —— AI 从格式来源读出的规则**")
        st.json(result["spec"])
    with c2:
        st.markdown("**RoleMap —— AI 标注的段落角色**")
        st.table([{"段落": p["idx"], "角色": result["rolemap"].get(p["idx"], "（表格/未标注）"),
                   "内容": p["text"][:40]} for p in result["paragraphs"]])

    if result["issues"]:
        st.markdown("**视觉自检问题清单**")
        st.table(result["issues"])

    # ---------- 结果 ----------
    st.subheader("📄 排版结果")
    with open(result["report_path"], encoding="utf-8") as f:
        st.markdown(f.read())
    with open(result["out_path"], "rb") as f:
        st.download_button("下载排版后 docx", f.read(), "formatted.docx")

    # ---------- 前后对比 ----------
    with st.spinner("渲染前后对比图（Word COM，约十几秒）..."):
        from core.render import render_docx_to_png
        before_pages = render_docx_to_png(target_path, os.path.join(out_dir, "before"))
        after_pages = render_docx_to_png(result["out_path"], os.path.join(out_dir, "after"))
    st.subheader("🖼️ 前后对比")
    c1, c2 = st.columns(2)
    for i in range(min(len(before_pages), len(after_pages))):
        with c1:
            st.image(before_pages[i], caption=f"排版前 第{i + 1}页")
        with c2:
            st.image(after_pages[i], caption=f"排版后 第{i + 1}页")
