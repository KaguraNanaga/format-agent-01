# 演示界面 —— Agent 控制台版。
# 设计目标：像 Agent 不像工具——编号引导输入、流水线步骤条实时可视、日志最新置顶。
# 设计语言：#f5f5f7 灰底 / 白色圆角卡片 / #0071e3 主色 / 无 emoji / 状态用色点与动画表达。
# 运行: streamlit run app.py

import json
import os
import tempfile
import time

import streamlit as st

from core.agent import Agent
from core.history import list_runs, save_run
from core.llm import load_dotenv
from core.schema import validate_spec

# 每次页面重跑都以 .env 最新内容为准（长驻进程改配置不用重启）
load_dotenv(override=True)

st.set_page_config(page_title="格式排版 Agent", layout="wide", initial_sidebar_state="collapsed")

# ---------------- 样式 ----------------
st.markdown("""
<style>
html, body, [data-testid="stAppViewContainer"] {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI",
                 "PingFang SC", "Microsoft YaHei", sans-serif;
    background-color: #f5f5f7;
    color: #1d1d1f;
}
[data-testid="stHeader"], #MainMenu, footer { visibility: hidden; }
.block-container { padding-top: 1.6rem; max-width: 1080px; }

h1 { font-weight: 700; letter-spacing: -0.02em; color: #1d1d1f; }
h2, h3 { font-weight: 600; letter-spacing: -0.01em; color: #1d1d1f; }

/* 卡片：白色、大圆角、轻投影、入场动画 */
.card {
    background: #ffffff;
    border-radius: 18px;
    padding: 26px 30px;
    margin-bottom: 18px;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.04);
    animation: fadeUp .45s ease both;
}
@keyframes fadeUp { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }

.card-title {
    font-size: 13px; font-weight: 600; letter-spacing: 0.08em;
    text-transform: uppercase; color: #86868b; margin-bottom: 4px;
}
.card-sub { font-size: 13px; color: #86868b; margin-top: -6px; margin-bottom: 14px; }

/* 步骤编号徽标 */
.step-badge {
    display: inline-block; width: 24px; height: 24px; line-height: 24px;
    border-radius: 50%; background: #0071e3; color: #fff; text-align: center;
    font-size: 13px; font-weight: 600; margin-right: 8px;
}

/* 主按钮：Apple 蓝药丸 */
.stButton > button[kind="primary"] {
    background: #0071e3; color: #fff; border: none; border-radius: 980px;
    padding: 14px 48px; font-size: 18px; font-weight: 600;
    box-shadow: 0 6px 18px rgba(0, 113, 227, 0.35);
    transition: all 0.2s ease;
}
.stButton > button[kind="primary"]:hover { background: #0077ed; transform: scale(1.03); }
.stButton > button[kind="primary"]:disabled {
    background: #d2d2d7; box-shadow: none; color: #6e6e73; transform: none;
}
.stDownloadButton > button {
    border-radius: 980px; border: 1px solid #d2d2d7; background: #fff;
    color: #0071e3; font-weight: 500; padding: 8px 26px;
    transition: all 0.2s ease;
}
.stDownloadButton > button:hover { border-color: #0071e3; }

.stTextArea textarea, .stTextInput input {
    border-radius: 12px; border: 1px solid #d2d2d7; background: #fff;
}
.stTextArea textarea:focus, .stTextInput input:focus {
    border-color: #0071e3; box-shadow: 0 0 0 3px rgba(0, 113, 227, 0.15);
}
[data-testid="stFileUploader"] { background: #fff; border-radius: 12px; padding: 4px 10px; }
[data-testid="stFileUploader"] section { border: 1px dashed #c7c7cc; border-radius: 12px; }
[data-testid="stExpander"] { background: #fff; border-radius: 14px; border: 1px solid #e8e8ed; }

/* ---------- 流水线步骤条 ---------- */
.pipeline { display: flex; align-items: flex-start; justify-content: space-between;
            margin: 6px 0 16px 0; padding: 0 4px; }
.stage { flex: 1; text-align: center; position: relative; }
.stage:not(:last-child)::after {
    content: ""; position: absolute; top: 17px; left: calc(50% + 24px);
    width: calc(100% - 48px); height: 2px; background: #e8e8ed;
}
.stage.done:not(:last-child)::after { background: #34c759; transition: background .4s ease; }
.circle {
    width: 34px; height: 34px; border-radius: 50%; margin: 0 auto;
    display: flex; align-items: center; justify-content: center;
    font-size: 14px; font-weight: 600; position: relative; z-index: 1;
    transition: all .3s ease;
}
.stage.wait .circle { background: #e8e8ed; color: #86868b; }
.stage.run .circle { background: #0071e3; color: #fff;
    box-shadow: 0 0 0 6px rgba(0,113,227,.18); animation: pulse 1.2s ease-in-out infinite; }
.stage.done .circle { background: #34c759; color: #fff; animation: pop .35s ease; }
.stage.err .circle { background: #ff3b30; color: #fff; animation: shake .4s ease; }
.stage.skip .circle { background: #f2f2f4; color: #c7c7cc; font-weight: 400; }
.stage .label { margin-top: 8px; font-size: 13px; color: #86868b; transition: color .3s; }
.stage.run .label { color: #0071e3; font-weight: 600; }
.stage.done .label { color: #1d1d1f; }
.stage.err .label { color: #ff3b30; font-weight: 600; }
.stage.skip .label { color: #c7c7cc; text-decoration: line-through; }

/* 进行中转圈：纯 CSS，Python 阻塞时浏览器照样转——用于区分"运行中"与"卡死" */
.spinner { width: 14px; height: 14px; border-radius: 50%;
    border: 2px solid rgba(255,255,255,.35); border-top-color: #fff;
    animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes pulse { 0%,100% { box-shadow: 0 0 0 5px rgba(0,113,227,.20); }
                   50% { box-shadow: 0 0 0 9px rgba(0,113,227,.10); } }
@keyframes pop { 0% { transform: scale(.4); } 70% { transform: scale(1.18); } 100% { transform: scale(1); } }
@keyframes shake { 0%,100% { transform: translateX(0); } 25% { transform: translateX(-4px); }
                   75% { transform: translateX(4px); } }

/* 日志：限高滚动、最新置顶 */
.log-scroll { max-height: 240px; overflow-y: auto; padding-right: 6px; }
.log-line { display: flex; align-items: baseline; gap: 10px; padding: 7px 0;
            border-bottom: 1px solid #f2f2f4; font-size: 14px; animation: fadeUp .3s ease both; }
.log-line:last-child { border-bottom: none; }
.dot { flex: none; width: 9px; height: 9px; border-radius: 50%; margin-top: 1px; }
.dot-run  { background: #0071e3; animation: pulse 1.2s ease-in-out infinite; }
.dot-ok   { background: #34c759; }
.dot-warn { background: #ff9500; }
.dot-err  { background: #ff3b30; }
.log-step { flex: none; min-width: 72px; font-size: 12px; font-weight: 600;
            color: #86868b; letter-spacing: 0.04em; }
.log-msg { color: #1d1d1f; white-space: pre-wrap; }

[data-testid="stJson"], .stTable { border-radius: 12px; }
.stTabs [data-baseweb="tab-list"] { gap: 8px; }
.stTabs [data-baseweb="tab"] { border-radius: 980px; padding: 6px 18px; }
[data-testid="stImage"] img { border-radius: 14px; box-shadow: 0 6px 28px rgba(0,0,0,0.08); }
[data-testid="stAlert"] { border-radius: 12px; }
</style>
""", unsafe_allow_html=True)

_STATUS_DOT = {"run": "run", "ok": "ok", "warn": "warn", "err": "err"}
_STAGES = ["理解规范", "解析文档", "标注角色", "执行排版", "视觉自检"]


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


def _pipeline_html(stage_state, current_msg, elapsed):
    """生成流水线步骤条 HTML。stage_state: {阶段名: wait|run|done|err|skip}"""
    items = ['<div class="pipeline">']
    for i, name in enumerate(_STAGES):
        state = stage_state.get(name, "wait")
        if state == "run":
            icon = '<div class="spinner"></div>'
        elif state == "done":
            icon = "✓"
        elif state == "err":
            icon = "✕"
        elif state == "skip":
            icon = "—"
        else:
            icon = str(i + 1)
        items.append(
            f'<div class="stage {state}"><div class="circle">{icon}</div>'
            f'<div class="label">{name}</div></div>')
    items.append("</div>")
    status_line = (f'<div style="text-align:center; font-size:13px; color:#0071e3; '
                   f'margin-bottom:10px;">{current_msg} · 已用 {elapsed:.0f} 秒</div>'
                   if current_msg else "")
    return status_line + "".join(items)


# ---------------- 页头（紧凑，把首屏留给操作） ----------------
st.markdown("""
<div style="text-align:center; margin: 8px 0 4px 0;">
  <div style="font-size:12px; font-weight:600; letter-spacing:0.12em;
              text-transform:uppercase; color:#0071e3;">Format Agent</div>
  <h1 style="font-size:34px; margin:4px 0;">格式排版 Agent</h1>
  <p style="font-size:14px; color:#6e6e73; margin:0;">
    理解归 AI，动手归代码，中间用 JSON 交接。
  </p>
</div>
""", unsafe_allow_html=True)

if not _llm_available():
    st.warning("未检测到 LLM 配置（.env 中的 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL）。")

# ---------------- 引导式输入 ----------------
col1, col2 = st.columns(2, gap="large")
with col1:
    st.markdown(_card_open("第一步", "上传要排版的文档"), unsafe_allow_html=True)
    target_file = st.file_uploader("拖入或选择 docx 文件", type=["docx"], key="target")
    st.markdown("</div>", unsafe_allow_html=True)
with col2:
    st.markdown(_card_open("第二步", "给它格式规范", "把单位/学校/期刊的格式要求原文粘贴进来即可"),
                unsafe_allow_html=True)
    spec_mode = st.radio("来源类型", ["规范文字", "模板 docx"],
                         horizontal=True, label_visibility="collapsed")
    spec_text, template_file = None, None
    if spec_mode == "规范文字":
        spec_text = st.text_area("粘贴排版规范文字", height=150,
                                 placeholder="例如：标题用黑体二号居中，正文仿宋三号、首行缩进 2 字符……")
    else:
        template_file = st.file_uploader("上传模板 docx", type=["docx"], key="tpl")
    st.markdown("</div>", unsafe_allow_html=True)

# 高级选项：JSON 直传（开发者用，普通用户不需要知道 JSON 是什么）
with st.expander("高级选项（开发者：直接给 JSON 规则 / 角色标注）"):
    spec_json_file = st.file_uploader("FormatSpec JSON（上传后优先于上面的格式来源）",
                                      type=["json"], key="specjson")
    rolemap_json_file = st.file_uploader("RoleMap JSON（跳过角色标注）",
                                         type=["json"], key="rolemapjson")

# ---------------- 第三步：开始 ----------------
st.markdown(
    "<div style='text-align:center; margin: 6px 0 2px 0;'>"
    "<span class='step-badge'>3</span>"
    "<span style='font-size:15px; font-weight:600;'>点击开始，之后全部交给 Agent</span></div>",
    unsafe_allow_html=True)
_, btn_col, _ = st.columns([2, 1, 2])
with btn_col:
    run = st.button("开始排版", type="primary", use_container_width=True,
                    disabled=(target_file is None))
c1, c2, c3 = st.columns([2, 1, 2])
with c2:
    verify = st.checkbox("排版后视觉自检", value=False)
    demo_available = os.path.exists("assets/spec.txt") and os.path.exists("assets/messy.docx")
    use_demo = st.checkbox("用内置示例", value=False, disabled=(not demo_available) or not _llm_available())
if use_demo:
    with open("assets/spec.txt", encoding="utf-8") as f:
        spec_text = f.read()
    spec_mode = "规范文字"

# ---------------- 执行 ----------------
if run and (target_file is not None or use_demo):
    st.markdown(_card_open("Agent", "正在工作", "每个阶段的进度实时可见；蓝色转圈 = 正在运行"),
                unsafe_allow_html=True)
    pipe_box = st.empty()
    log_lines = []
    log_box = st.empty()
    t0 = time.time()

    stage_state = {name: "wait" for name in _STAGES}
    if not verify:
        stage_state["视觉自检"] = "skip"

    def on_event(event):
        step, status = event["step"], event["status"]
        if step == "完成":
            for k in stage_state:
                if stage_state[k] == "run":
                    stage_state[k] = "done"
        elif step in stage_state and stage_state[step] != "skip":
            if status == "ok":
                stage_state[step] = "done"
            elif status == "err":
                stage_state[step] = "err"
            else:  # run / warn 都视为进行中
                stage_state[step] = "run"
        dot = _STATUS_DOT.get(status, "run")
        log_lines.insert(0,  # 最新置顶
            f'<div class="log-line"><span class="dot dot-{dot}"></span>'
            f'<span class="log-step">{step}</span>'
            f'<span class="log-msg">{event["message"]}</span></div>')
        running_msg = event["message"] if status in ("run", "warn") else ""
        pipe_box.markdown(_pipeline_html(stage_state, running_msg, time.time() - t0),
                          unsafe_allow_html=True)
        log_box.markdown(f'<div class="log-scroll">{"".join(log_lines)}</div>',
                         unsafe_allow_html=True)

    target_path = "assets/messy.docx" if use_demo else _save_upload(target_file, ".docx")
    out_dir = tempfile.mkdtemp()
    out_path = os.path.join(out_dir, "formatted.docx")
    report_path = os.path.join(out_dir, "report.md")

    try:
        kwargs = {"target_path": target_path, "out_path": out_path,
                  "report_path": report_path, "verify": verify}
        if spec_json_file is not None:
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
    for k in stage_state:
        if stage_state[k] == "run":
            stage_state[k] = "done"
    pipe_box.markdown(_pipeline_html(stage_state, "", time.time() - t0), unsafe_allow_html=True)
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

    # ---------------- 历史留档 ----------------
    save_run(result["out_path"], result["report_path"], {
        "source_name": "内置示例 messy.docx" if use_demo else target_file.name,
        "spec_mode": "内置示例" if use_demo else ("FormatSpec JSON" if spec_json_file else spec_mode),
        "issues_count": len(result.get("issues") or []),
    })

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

# ---------------- 历史记录 ----------------
_runs = list_runs()
if _runs:
    st.markdown(_card_open("留痕", "历史记录", "每次排版的产物都持久保存，随时回看与下载"),
                unsafe_allow_html=True)
    for _r in _runs:
        cols = st.columns([5, 2, 2, 2])
        with cols[0]:
            st.markdown(
                f"**{_r.get('source_name', '（未命名）')}**<br/>"
                f"<span style='color:#86868b;font-size:12px'>{_r.get('time', '')}</span>",
                unsafe_allow_html=True)
        with cols[1]:
            st.caption(_r.get("spec_mode", ""))
        with cols[2]:
            with open(_r["docx"], "rb") as f:
                st.download_button("下载 docx", f.read(),
                                   file_name="formatted_%s.docx" % _r["run_id"],
                                   key="dl_docx_" + _r["run_id"])
        with cols[3]:
            if os.path.isfile(_r["report"]):
                with open(_r["report"], "rb") as f:
                    st.download_button("下载报告", f.read(),
                                       file_name="report_%s.md" % _r["run_id"],
                                       key="dl_rep_" + _r["run_id"])
    st.markdown("</div>", unsafe_allow_html=True)
