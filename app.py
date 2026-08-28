# 演示界面 —— Apple 风格极简设计版。
# 设计语言：#f5f5f7 灰底 / 白色圆角卡片 / #0071e3 主色 / 无 emoji / 状态用色点表达。
# 演示故事不变："理解归 AI，动手归代码，中间用 JSON 交接" —— 工作日志实时直播。
# 运行: streamlit run app.py

import json
import os
import tempfile

import streamlit as st

from core.agent import Agent
from core.llm import load_dotenv
from core.schema import validate_spec

# 每次页面重跑都以 .env 最新内容为准（长驻进程改配置不用重启）
load_dotenv(override=True)

st.set_page_config(page_title="格式排版 Agent", layout="wide", initial_sidebar_state="collapsed")

# ---------------- Apple 风格样式 ----------------
st.markdown("""
<style>
/* 全局：SF 系字体 + Apple 灰底 */
html, body, [data-testid="stAppViewContainer"] {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI",
                 "PingFang SC", "Microsoft YaHei", sans-serif;
    background-color: #f5f5f7;
    color: #1d1d1f;
}
[data-testid="stHeader"], #MainMenu, footer { visibility: hidden; }
.block-container { padding-top: 3rem; max-width: 1080px; }

/* 标题层级 */
h1 { font-weight: 700; letter-spacing: -0.02em; color: #1d1d1f; }
h2, h3 { font-weight: 600; letter-spacing: -0.01em; color: #1d1d1f; }

/* 卡片：白色、大圆角、轻投影 */
.card {
    background: #ffffff;
    border-radius: 18px;
    padding: 28px 32px;
    margin-bottom: 20px;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.04);
}
.card-title {
    font-size: 13px; font-weight: 600; letter-spacing: 0.08em;
    text-transform: uppercase; color: #86868b; margin-bottom: 4px;
}
.card-sub { font-size: 13px; color: #86868b; margin-top: -6px; margin-bottom: 14px; }

/* 主按钮：Apple 蓝药丸 */
.stButton > button[kind="primary"] {
    background: #0071e3; color: #fff; border: none; border-radius: 980px;
    padding: 10px 34px; font-size: 16px; font-weight: 500;
    box-shadow: 0 4px 14px rgba(0, 113, 227, 0.3);
    transition: background 0.2s ease;
}
.stButton > button[kind="primary"]:hover { background: #0077ed; }
.stButton > button[kind="primary"]:disabled {
    background: #d2d2d7; box-shadow: none; color: #6e6e73;
}
/* 下载按钮同样药丸化 */
.stDownloadButton > button {
    border-radius: 980px; border: 1px solid #d2d2d7; background: #fff;
    color: #0071e3; font-weight: 500; padding: 8px 26px;
}

/* 输入控件圆角 */
.stTextArea textarea, .stTextInput input {
    border-radius: 12px; border: 1px solid #d2d2d7; background: #fff;
}
.stTextArea textarea:focus, .stTextInput input:focus {
    border-color: #0071e3; box-shadow: 0 0 0 3px rgba(0, 113, 227, 0.15);
}
[data-testid="stFileUploader"] {
    background: #fff; border-radius: 12px; padding: 4px 10px;
}
[data-testid="stFileUploader"] section {
    border: 1px dashed #d2d2d7; border-radius: 12px;
}

/* Agent 日志：色点代替 emoji */
.log-line { display: flex; align-items: baseline; gap: 10px; padding: 7px 0;
            border-bottom: 1px solid #f2f2f4; font-size: 14px; }
.log-line:last-child { border-bottom: none; }
.dot { flex: none; width: 9px; height: 9px; border-radius: 50%; margin-top: 1px; }
.dot-run  { background: #0071e3; animation: pulse 1.2s ease-in-out infinite; }
.dot-ok   { background: #34c759; }
.dot-warn { background: #ff9500; }
.dot-err  { background: #ff3b30; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }
.log-step { flex: none; min-width: 72px; font-size: 12px; font-weight: 600;
            color: #86868b; letter-spacing: 0.04em; }
.log-msg { color: #1d1d1f; white-space: pre-wrap; }

/* JSON / 表格容器柔化 */
[data-testid="stJson"], .stTable { border-radius: 12px; }
.stTabs [data-baseweb="tab-list"] { gap: 8px; }
.stTabs [data-baseweb="tab"] { border-radius: 980px; padding: 6px 18px; }

/* 对比图圆角 */
[data-testid="stImage"] img { border-radius: 14px; box-shadow: 0 6px 28px rgba(0,0,0,0.08); }

/* 提示框去 emoji 化后的统一卡片感 */
[data-testid="stAlert"] { border-radius: 12px; }
</style>
""", unsafe_allow_html=True)

_STATUS_DOT = {"run": "run", "ok": "ok", "warn": "warn", "err": "err"}


def _llm_available():
    return bool(os.environ.get("LLM_BASE_URL") and os.environ.get("LLM_API_KEY")
                and os.environ.get("LLM_MODEL"))


def _save_upload(uploaded, suffix):
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(uploaded.getbuffer())
    return path


def _card_open(eyebrow, title, sub=None):
    sub_html = f'<p class="card-sub">{sub}</p>' if sub else ""
    return (f'<div class="card"><div class="card-title">{eyebrow}</div>'
            f"<h3 style='margin-top:0'>{title}</h3>{sub_html}")


# ---------------- 页头 ----------------
st.markdown("""
<div style="text-align:center; margin: 24px 0 8px 0;">
  <div style="font-size:13px; font-weight:600; letter-spacing:0.12em;
              text-transform:uppercase; color:#0071e3;">Format Agent</div>
  <h1 style="font-size:44px; margin:6px 0;">格式排版 Agent</h1>
  <p style="font-size:17px; color:#6e6e73; margin:0;">
    理解归 AI，动手归代码，中间用 JSON 交接。
  </p>
</div>
""", unsafe_allow_html=True)

# 配置状态条
text_model = os.environ.get("LLM_MODEL", "")
vision_model = os.environ.get("LLM_VISION_MODEL", "")
if _llm_available():
    vision_txt = vision_model or "未配置（自检将复用文本模型）"
    st.markdown(
        f"<div style='text-align:center; font-size:12px; color:#86868b; margin-bottom:20px;'>"
        f"文本模型 {text_model} &nbsp;·&nbsp; 视觉模型 {vision_txt}</div>",
        unsafe_allow_html=True)
else:
    st.warning("未检测到 LLM 配置（.env 中的 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL）。"
               "可改用 FormatSpec JSON / RoleMap JSON 走确定性降级链路。")

# ---------------- 输入区 ----------------
_DEMO_AVAILABLE = (os.path.exists("assets/spec.txt") and os.path.exists("assets/messy.docx"))
use_demo = st.checkbox("使用内置示例一键演示（assets/spec.txt + assets/messy.docx）",
                       value=False, disabled=not _DEMO_AVAILABLE)

col1, col2 = st.columns(2, gap="large")
with col1:
    st.markdown(_card_open("输入 ①", "格式来源", "规范文字、模板文档，或现成的规则 JSON"), unsafe_allow_html=True)
    spec_mode = st.radio("来源类型", ["规范文字", "模板 docx", "FormatSpec JSON"],
                         horizontal=True, disabled=use_demo, label_visibility="collapsed")
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
    st.markdown("</div>", unsafe_allow_html=True)
with col2:
    st.markdown(_card_open("输入 ②", "待排版文档", "上传后，Agent 将自主完成理解、标注与改写"), unsafe_allow_html=True)
    target_file = None if use_demo else st.file_uploader("上传目标 docx", type=["docx"], key="target")
    if use_demo:
        st.info("目标文档：内置示例 assets/messy.docx")
    rolemap_json_file = st.file_uploader("（可选）直接给 RoleMap JSON，跳过角色标注",
                                         type=["json"], key="rolemapjson")
    verify = st.checkbox("排版后视觉自检（需要视觉模型）", value=False)
    st.markdown("</div>", unsafe_allow_html=True)

_, btn_col, _ = st.columns([2, 1, 2])
with btn_col:
    run = st.button("开始排版", type="primary", use_container_width=True,
                    disabled=(target_file is None and not use_demo))

# ---------------- 执行 ----------------
if run and (target_file is not None or use_demo):
    st.markdown(_card_open("Agent", "工作日志", "每一步理解、校验与自我修正都会实时出现在这里"),
                unsafe_allow_html=True)
    log_lines = []
    log_box = st.empty()

    def on_event(event):
        dot = _STATUS_DOT.get(event["status"], "run")
        log_lines.append(
            f'<div class="log-line"><span class="dot dot-{dot}"></span>'
            f'<span class="log-step">{event["step"]}</span>'
            f'<span class="log-msg">{event["message"]}</span></div>')
        log_box.markdown("".join(log_lines), unsafe_allow_html=True)

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
        on_event({"step": "失败", "message": str(e), "status": "err", "data": None})
        st.markdown("</div>", unsafe_allow_html=True)
        st.stop()
    st.markdown("</div>", unsafe_allow_html=True)

    # ---------------- 中间产物 ----------------
    st.markdown(_card_open("产物", "Agent 的思考产物", "两个 JSON 交接：AI 的理解止步于此，之后全是确定性代码"),
                unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["FormatSpec（格式规则）", "RoleMap（段落角色）"])
    with tab1:
        st.json(result["spec"])
    with tab2:
        st.table([{"段落": p["idx"], "角色": result["rolemap"].get(p["idx"], "（表格/未标注）"),
                   "内容": p["text"][:40]} for p in result["paragraphs"]])
    if result["issues"]:
        st.markdown("**视觉自检问题清单**")
        st.table(result["issues"])
    st.markdown("</div>", unsafe_allow_html=True)

    # ---------------- 结果 ----------------
    st.markdown(_card_open("输出", "排版结果"), unsafe_allow_html=True)
    with open(result["report_path"], encoding="utf-8") as f:
        st.markdown(f.read())
    with open(result["out_path"], "rb") as f:
        st.download_button("下载排版后 docx", f.read(), "formatted.docx")
    st.markdown("</div>", unsafe_allow_html=True)

    # ---------------- 前后对比 ----------------
    with st.spinner("渲染前后对比图（Word COM，约十几秒）..."):
        from core.render import render_docx_to_png
        before_pages = render_docx_to_png(target_path, os.path.join(out_dir, "before"))
        after_pages = render_docx_to_png(result["out_path"], os.path.join(out_dir, "after"))
    st.markdown(_card_open("对比", "前后对照", "左：原始文档；右：Agent 排版后"), unsafe_allow_html=True)
    c1, c2 = st.columns(2, gap="large")
    for i in range(min(len(before_pages), len(after_pages))):
        with c1:
            st.image(before_pages[i], caption=f"排版前 · 第 {i + 1} 页")
        with c2:
            st.image(after_pages[i], caption=f"排版后 · 第 {i + 1} 页")
    st.markdown("</div>", unsafe_allow_html=True)
