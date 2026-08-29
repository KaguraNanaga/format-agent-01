"""Format Agent 的 Streamlit 工作台。

设计目标不是做一个“大号表单”，而是让用户清楚地感知：
1. 现在应该提供什么；2. Agent 正在做什么；3. 长耗时步骤是否仍在等待；
4. 完成后去哪里下载结果。运行：streamlit run app.py
"""

import html
import json
import os
import tempfile
import time
from datetime import datetime

import streamlit as st

from core.agent import Agent
from core.history import list_runs, save_run
from core.llm import load_dotenv
from core.render import renderer_status as _renderer_status
from core.schema import validate_spec


# 长驻 Streamlit 进程每次重跑都读取最新配置。
load_dotenv(override=True)

st.set_page_config(
    page_title="Format Agent · 文档排版智能体",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ---------------- 视觉系统 ----------------
# 主题：默认白色（Apple 风浅色），深色控制台为次级选择。
st.session_state.setdefault("ui_theme", "白色")
_THEME = st.session_state["ui_theme"]

_DARK_CSS = """
:root {
    --ink: #f7f8fc;
    --muted: #9ba6bd;
    --panel: rgba(16, 23, 40, 0.76);
    --panel-strong: rgba(20, 28, 48, 0.94);
    --line: rgba(166, 185, 225, 0.16);
    --cyan: #65e7ff;
    --violet: #9b8cff;
    --green: #58e6a9;
    --amber: #ffc86b;
    --red: #ff7c91;
}

html, body, [data-testid="stAppViewContainer"], .stApp {
    font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont,
                 "SF Pro Display", "PingFang SC", "Microsoft YaHei", sans-serif;
    color: var(--ink);
}
[data-testid="stAppViewContainer"], .stApp {
    background:
        radial-gradient(circle at 12% 4%, rgba(78, 106, 255, 0.18), transparent 28%),
        radial-gradient(circle at 88% 12%, rgba(50, 224, 220, 0.12), transparent 24%),
        radial-gradient(circle at 54% 110%, rgba(145, 94, 255, 0.14), transparent 38%),
        #070b14;
}
[data-testid="stHeader"], #MainMenu, footer { visibility: hidden; }
.block-container { max-width: 1180px; padding-top: 2rem; padding-bottom: 5rem; }

/* 首屏 Agent 身份 */
.agent-hero {
    position: relative; overflow: hidden; min-height: 286px;
    display: grid; grid-template-columns: 1fr 270px; align-items: center;
    padding: 42px 48px; margin: 8px 0 26px;
    border: 1px solid var(--line); border-radius: 30px;
    background: linear-gradient(135deg, rgba(22,31,55,.94), rgba(10,16,30,.80));
    box-shadow: 0 30px 90px rgba(0,0,0,.34), inset 0 1px rgba(255,255,255,.04);
    animation: rise-in .65s cubic-bezier(.2,.75,.2,1) both;
}
.agent-hero::before {
    content: ""; position: absolute; inset: -70%; pointer-events: none;
    background: conic-gradient(from 130deg, transparent 0 42%, rgba(101,231,255,.07), transparent 58%);
    animation: ambient-turn 18s linear infinite;
}
.hero-copy { position: relative; z-index: 1; }
.eyebrow { display: flex; align-items: center; gap: 9px; margin-bottom: 18px;
    color: var(--cyan); font-size: 12px; font-weight: 750; letter-spacing: .14em; text-transform: uppercase; }
.live-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green);
    box-shadow: 0 0 0 0 rgba(88,230,169,.55); animation: live-pulse 1.8s infinite; }
.agent-hero h1 { margin: 0 0 15px; max-width: 720px; color: #fff;
    font-size: clamp(38px, 5vw, 66px); line-height: 1.04; letter-spacing: -.052em; }
.agent-hero p { max-width: 660px; margin: 0; color: #b4bfd4; font-size: 17px; line-height: 1.75; }
.hero-note { display: inline-flex; gap: 10px; align-items: center; margin-top: 22px;
    color: #d7deed; font-size: 13px; }
.hero-note b { color: #fff; }

.agent-core { position: relative; width: 218px; height: 218px; margin: auto; }
.agent-core .ring { position: absolute; inset: 0; border-radius: 50%;
    border: 1px solid rgba(101,231,255,.24); animation: ring-spin 11s linear infinite; }
.agent-core .ring::before, .agent-core .ring::after {
    content: ""; position: absolute; border-radius: 50%; background: var(--cyan);
    box-shadow: 0 0 18px var(--cyan); }
.agent-core .ring::before { width: 7px; height: 7px; left: 23px; top: 26px; }
.agent-core .ring::after { width: 5px; height: 5px; right: 12px; bottom: 67px; }
.agent-core .ring.two { inset: 24px; border-style: dashed; border-color: rgba(155,140,255,.34);
    animation-duration: 16s; animation-direction: reverse; }
.agent-core .orb { position: absolute; inset: 54px; display: grid; place-items: center;
    border-radius: 38%; color: #fff; font-weight: 800; font-size: 35px;
    background: linear-gradient(145deg, rgba(101,231,255,.92), rgba(115,92,255,.92));
    box-shadow: 0 0 55px rgba(93,161,255,.35), inset 0 1px 12px rgba(255,255,255,.45);
    animation: core-breathe 3.2s ease-in-out infinite; }

/* 章节与原生组件 */
.section-kicker { margin-top: 10px; color: var(--cyan); font-size: 11px;
    font-weight: 760; letter-spacing: .15em; text-transform: uppercase; }
.section-title { margin: 5px 0 4px; color: #fff; font-size: 27px; font-weight: 720; letter-spacing: -.025em; }
.section-help { margin: 0 0 18px; color: var(--muted); font-size: 14px; }

[data-testid="stVerticalBlockBorderWrapper"] {
    border: 1px solid var(--line) !important; border-radius: 22px !important;
    background: linear-gradient(145deg, rgba(19,27,47,.88), rgba(12,18,32,.78)) !important;
    box-shadow: 0 18px 55px rgba(0,0,0,.20), inset 0 1px rgba(255,255,255,.035);
    transition: border-color .25s ease, transform .25s ease, box-shadow .25s ease;
}
[data-testid="stVerticalBlockBorderWrapper"]:hover {
    border-color: rgba(101,231,255,.28) !important;
    box-shadow: 0 20px 62px rgba(0,0,0,.26), 0 0 0 1px rgba(101,231,255,.035);
}
.input-head { display:flex; gap:14px; align-items:flex-start; margin-bottom:4px; }
.input-no { flex:none; display:grid; place-items:center; width:34px; height:34px; border-radius:12px;
    color:#07111c; background:linear-gradient(145deg, var(--cyan), #a6f3ff); font-weight:850; }
.input-title { color:#fff; font-size:17px; font-weight:700; margin-top:2px; }
.input-hint { color:var(--muted); font-size:12px; line-height:1.55; margin-top:3px; }

label, [data-testid="stWidgetLabel"] p, .stMarkdown p, .stCaption { color: #c7d0e2; }
[data-testid="stTextArea"] textarea, [data-testid="stTextInput"] input {
    color: #f4f7ff !important; background: rgba(5,10,20,.68) !important;
    border: 1px solid rgba(157,177,219,.20) !important; border-radius: 14px !important;
}
[data-testid="stTextArea"] textarea:focus, [data-testid="stTextInput"] input:focus {
    border-color: rgba(101,231,255,.70) !important;
    box-shadow: 0 0 0 3px rgba(101,231,255,.10) !important;
}
[data-testid="stFileUploader"] section {
    min-height: 112px; border: 1px dashed rgba(139,160,204,.30); border-radius: 15px;
    background: rgba(5,10,20,.45); transition: .25s ease;
}
[data-testid="stFileUploader"] section:hover { border-color: var(--cyan); background: rgba(34,66,90,.22); }
[data-testid="stFileUploaderDropzoneInstructions"] span { color: #edf3ff !important; }
[data-testid="stFileUploaderDropzoneInstructions"] small { color: var(--muted) !important; }
[data-baseweb="radio"] { background: transparent; }
[data-testid="stExpander"] { border: 1px solid var(--line); border-radius: 16px; background: rgba(12,18,32,.55); }
[data-testid="stExpander"] summary p { color: #d9e2f4 !important; font-weight: 600; }

/* 明确的主行动区 */
.readiness { display:flex; align-items:center; gap:11px; min-height:42px; }
.ready-icon { width:36px; height:36px; display:grid; place-items:center; border-radius:12px;
    font-size:15px; font-weight:800; }
.ready-icon.ok { color:#071a12; background:var(--green); box-shadow:0 0 24px rgba(88,230,169,.18); }
.ready-icon.wait { color:#251807; background:var(--amber); }
.ready-title { color:#fff; font-size:14px; font-weight:700; }
.ready-sub { color:var(--muted); font-size:12px; margin-top:2px; }
.stButton > button[kind="primary"] {
    position: relative; min-height: 54px; border: 0; border-radius: 16px;
    color: #06111b; background: linear-gradient(110deg, #66e9ff, #94a5ff 54%, #b896ff);
    font-size: 16px; font-weight: 800; letter-spacing: -.01em;
    box-shadow: 0 15px 38px rgba(92,160,255,.26); transition: .22s ease;
    animation: cta-glow 3s ease-in-out infinite;
}
.stButton > button[kind="primary"]:hover { transform: translateY(-2px); filter: brightness(1.08); }
.stButton > button[kind="primary"]:disabled {
    color: #778196; background: rgba(92,105,133,.20); box-shadow:none; animation:none;
}
.stDownloadButton > button { min-height:44px; border-radius:14px; border:1px solid rgba(101,231,255,.28);
    color:#dffaff; background:rgba(52,129,157,.14); font-weight:700; }

/* Agent 执行轨道 */
.agent-stage { position:relative; overflow:hidden; margin-top:12px; padding:26px 28px;
    border:1px solid var(--line); border-radius:22px; background:var(--panel-strong); }
.agent-stage.running::before { content:""; position:absolute; left:-35%; top:0; width:35%; height:2px;
    background:linear-gradient(90deg, transparent, var(--cyan), transparent);
    animation: scan-line 2.2s ease-in-out infinite; }
.stage-head { display:flex; justify-content:space-between; gap:16px; align-items:center; margin-bottom:24px; }
.stage-state { display:flex; align-items:center; gap:9px; color:#fff; font-weight:720; }
.stage-state .pulse { width:10px; height:10px; border-radius:50%; background:var(--cyan);
    box-shadow:0 0 0 0 rgba(101,231,255,.55); animation:live-pulse 1.5s infinite; }
.stage-state.done .pulse { background:var(--green); animation:none; }
.stage-state.failed .pulse { background:var(--red); animation:none; }
.stage-note { color:var(--muted); font-size:12px; }
.workflow { display:grid; grid-template-columns:repeat(6,1fr); gap:0; }
.flow-step { position:relative; text-align:center; min-width:0; }
.flow-step:not(:last-child)::after { content:""; position:absolute; height:1px; left:calc(50% + 21px);
    right:calc(-50% + 21px); top:19px; background:rgba(137,157,197,.22); }
.flow-step.done:not(:last-child)::after { background:linear-gradient(90deg,var(--green),rgba(101,231,255,.48)); }
.flow-node { position:relative; z-index:1; display:grid; place-items:center; width:38px; height:38px;
    margin:0 auto 9px; border-radius:13px; color:#78849a; background:#11192a;
    border:1px solid rgba(144,164,205,.16); font-size:12px; font-weight:800; }
.flow-step.active .flow-node { color:#06151c; border-color:transparent; background:var(--cyan);
    box-shadow:0 0 0 6px rgba(101,231,255,.08), 0 0 28px rgba(101,231,255,.25);
    animation:active-node 1.45s ease-in-out infinite; }
.flow-step.done .flow-node { color:#071a12; border-color:transparent; background:var(--green); }
.flow-step.failed .flow-node { color:#27080f; background:var(--red); border-color:transparent; }
.flow-step.skipped .flow-node { color:#a8b1c4; background:#283147; }
.flow-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#77849b; font-size:11px; }
.flow-step.active .flow-name, .flow-step.done .flow-name { color:#e8effc; }
.flow-detail { margin-top:22px; padding-top:16px; border-top:1px solid rgba(145,163,200,.12);
    color:#aeb9ce; font-size:12px; line-height:1.65; }

.event-list { padding:3px 2px; }
.event-line { display:grid; grid-template-columns:58px 82px 1fr; gap:10px; align-items:start;
    padding:9px 5px; border-bottom:1px solid rgba(146,165,204,.09); font-size:12px; }
.event-time { color:#657188; font-variant-numeric:tabular-nums; }
.event-step { color:#a8b5ca; font-weight:700; }
.event-msg { color:#dce4f2; line-height:1.55; }
.event-line.warn .event-step { color:var(--amber); }
.event-line.err .event-step { color:var(--red); }
.event-line.ok .event-step { color:var(--green); }

/* 结果与历史 */
.success-banner { padding:27px 30px; margin:12px 0 18px; border-radius:22px;
    border:1px solid rgba(88,230,169,.25); background:linear-gradient(120deg,rgba(26,81,65,.38),rgba(16,25,42,.84));
    box-shadow:0 18px 60px rgba(0,0,0,.22); animation:rise-in .55s ease both; }
.success-banner .label { color:var(--green); font-size:11px; font-weight:800; letter-spacing:.15em; }
.success-banner h2 { color:#fff; margin:7px 0 6px; font-size:27px; }
.success-banner p { color:#aeb9cd; margin:0; font-size:13px; }
[data-testid="stMetric"] { padding:14px 16px; border:1px solid var(--line); border-radius:16px; background:rgba(10,16,29,.58); }
[data-testid="stMetricValue"] { color:#fff; }

@keyframes rise-in { from { opacity:0; transform:translateY(15px); } to { opacity:1; transform:none; } }
@keyframes ambient-turn { to { transform:rotate(360deg); } }
@keyframes ring-spin { to { transform:rotate(360deg); } }
@keyframes core-breathe { 0%,100% { transform:scale(.97) rotate(-2deg); border-radius:38%; }
    50% { transform:scale(1.04) rotate(2deg); border-radius:46%; } }
@keyframes live-pulse { 0% { box-shadow:0 0 0 0 rgba(101,231,255,.48); }
    75%,100% { box-shadow:0 0 0 10px rgba(101,231,255,0); } }
@keyframes active-node { 50% { transform:translateY(-2px); box-shadow:0 0 0 9px rgba(101,231,255,.04),0 0 35px rgba(101,231,255,.34); } }
@keyframes scan-line { 0% { left:-35%; } 70%,100% { left:110%; } }
@keyframes cta-glow { 0%,100% { box-shadow:0 15px 38px rgba(92,160,255,.20); }
    50% { box-shadow:0 17px 46px rgba(101,231,255,.34); } }

@media (max-width: 820px) {
    .agent-hero { grid-template-columns:1fr; padding:32px 27px; }
    .agent-core { display:none; }
    .workflow { grid-template-columns:repeat(3,1fr); row-gap:20px; }
    .flow-step::after { display:none; }
    .event-line { grid-template-columns:52px 70px 1fr; }
}
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation-duration:.01ms !important; animation-iteration-count:1 !important; }
}
"""

# 白色主题：与深色完全同一套布局与动效，只换配色。
_LIGHT_CSS = """
:root {
    --ink: #1d1d1f;
    --muted: #6e6e73;
    --panel: rgba(255, 255, 255, 0.82);
    --panel-strong: #ffffff;
    --line: rgba(0, 0, 0, 0.08);
    --cyan: #0071e3;
    --violet: #5856d6;
    --green: #2da44e;
    --amber: #e08600;
    --red: #e0352b;
}

html, body, [data-testid="stAppViewContainer"], .stApp {
    font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont,
                 "SF Pro Display", "PingFang SC", "Microsoft YaHei", sans-serif;
    color: var(--ink);
}
[data-testid="stAppViewContainer"], .stApp {
    background:
        radial-gradient(circle at 12% 4%, rgba(0, 113, 227, 0.07), transparent 28%),
        radial-gradient(circle at 88% 12%, rgba(88, 86, 214, 0.06), transparent 24%),
        radial-gradient(circle at 54% 110%, rgba(0, 113, 227, 0.05), transparent 38%),
        #f5f5f7;
}
[data-testid="stHeader"], #MainMenu, footer { visibility: hidden; }
.block-container { max-width: 1180px; padding-top: 2rem; padding-bottom: 5rem; }

/* 首屏 Agent 身份 */
.agent-hero {
    position: relative; overflow: hidden; min-height: 286px;
    display: grid; grid-template-columns: 1fr 270px; align-items: center;
    padding: 42px 48px; margin: 8px 0 26px;
    border: 1px solid var(--line); border-radius: 30px;
    background: linear-gradient(135deg, #ffffff, #f7f9ff);
    box-shadow: 0 18px 50px rgba(0,0,0,.06), inset 0 1px rgba(255,255,255,.7);
    animation: rise-in .65s cubic-bezier(.2,.75,.2,1) both;
}
.agent-hero::before {
    content: ""; position: absolute; inset: -70%; pointer-events: none;
    background: conic-gradient(from 130deg, transparent 0 42%, rgba(0,113,227,.05), transparent 58%);
    animation: ambient-turn 18s linear infinite;
}
.hero-copy { position: relative; z-index: 1; }
.eyebrow { display: flex; align-items: center; gap: 9px; margin-bottom: 18px;
    color: var(--cyan); font-size: 12px; font-weight: 750; letter-spacing: .14em; text-transform: uppercase; }
.live-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green);
    box-shadow: 0 0 0 0 rgba(45,164,78,.45); animation: live-pulse 1.8s infinite; }
.agent-hero h1 { margin: 0 0 15px; max-width: 720px; color: #1d1d1f;
    font-size: clamp(38px, 5vw, 66px); line-height: 1.04; letter-spacing: -.052em; }
.agent-hero p { max-width: 660px; margin: 0; color: #6e6e73; font-size: 17px; line-height: 1.75; }
.hero-note { display: inline-flex; gap: 10px; align-items: center; margin-top: 22px;
    color: #3a3a3c; font-size: 13px; }
.hero-note b { color: #1d1d1f; }

.agent-core { position: relative; width: 218px; height: 218px; margin: auto; }
.agent-core .ring { position: absolute; inset: 0; border-radius: 50%;
    border: 1px solid rgba(0,113,227,.28); animation: ring-spin 11s linear infinite; }
.agent-core .ring::before, .agent-core .ring::after {
    content: ""; position: absolute; border-radius: 50%; background: var(--cyan);
    box-shadow: 0 0 18px rgba(0,113,227,.55); }
.agent-core .ring::before { width: 7px; height: 7px; left: 23px; top: 26px; }
.agent-core .ring::after { width: 5px; height: 5px; right: 12px; bottom: 67px; }
.agent-core .ring.two { inset: 24px; border-style: dashed; border-color: rgba(88,86,214,.38);
    animation-duration: 16s; animation-direction: reverse; }
.agent-core .orb { position: absolute; inset: 54px; display: grid; place-items: center;
    border-radius: 38%; color: #fff; font-weight: 800; font-size: 35px;
    background: linear-gradient(145deg, #0a84ff, #5e5ce6);
    box-shadow: 0 0 55px rgba(10,132,255,.28), inset 0 1px 12px rgba(255,255,255,.45);
    animation: core-breathe 3.2s ease-in-out infinite; }

/* 章节与原生组件 */
.section-kicker { margin-top: 10px; color: var(--cyan); font-size: 11px;
    font-weight: 760; letter-spacing: .15em; text-transform: uppercase; }
.section-title { margin: 5px 0 4px; color: #1d1d1f; font-size: 27px; font-weight: 720; letter-spacing: -.025em; }
.section-help { margin: 0 0 18px; color: var(--muted); font-size: 14px; }

[data-testid="stVerticalBlockBorderWrapper"] {
    border: 1px solid var(--line) !important; border-radius: 22px !important;
    background: linear-gradient(145deg, #ffffff, #fbfcff) !important;
    box-shadow: 0 10px 34px rgba(0,0,0,.05), inset 0 1px rgba(255,255,255,.6);
    transition: border-color .25s ease, transform .25s ease, box-shadow .25s ease;
}
[data-testid="stVerticalBlockBorderWrapper"]:hover {
    border-color: rgba(0,113,227,.30) !important;
    box-shadow: 0 14px 42px rgba(0,0,0,.07), 0 0 0 1px rgba(0,113,227,.05);
}
.input-head { display:flex; gap:14px; align-items:flex-start; margin-bottom:4px; }
.input-no { flex:none; display:grid; place-items:center; width:34px; height:34px; border-radius:12px;
    color:#ffffff; background:linear-gradient(145deg, #0a84ff, #5e9dff); font-weight:850; }
.input-title { color:#1d1d1f; font-size:17px; font-weight:700; margin-top:2px; }
.input-hint { color:var(--muted); font-size:12px; line-height:1.55; margin-top:3px; }

label, [data-testid="stWidgetLabel"] p, .stMarkdown p, .stCaption { color: #3a3a3c; }
[data-testid="stTextArea"] textarea, [data-testid="stTextInput"] input {
    color: #1d1d1f !important; background: #ffffff !important;
    border: 1px solid rgba(0,0,0,.14) !important; border-radius: 14px !important;
}
[data-testid="stTextArea"] textarea:focus, [data-testid="stTextInput"] input:focus {
    border-color: rgba(0,113,227,.75) !important;
    box-shadow: 0 0 0 3px rgba(0,113,227,.12) !important;
}
[data-testid="stFileUploader"] section {
    min-height: 112px; border: 1px dashed rgba(0,0,0,.20); border-radius: 15px;
    background: #fafafc; transition: .25s ease;
}
[data-testid="stFileUploader"] section:hover { border-color: var(--cyan); background: #f0f6ff; }
[data-testid="stFileUploaderDropzoneInstructions"] span { color: #1d1d1f !important; }
[data-testid="stFileUploaderDropzoneInstructions"] small { color: var(--muted) !important; }
[data-baseweb="radio"] { background: transparent; }
[data-testid="stExpander"] { border: 1px solid var(--line); border-radius: 16px; background: #ffffff; }
[data-testid="stExpander"] summary p { color: #1d1d1f !important; font-weight: 600; }

/* 明确的主行动区 */
.readiness { display:flex; align-items:center; gap:11px; min-height:42px; }
.ready-icon { width:36px; height:36px; display:grid; place-items:center; border-radius:12px;
    font-size:15px; font-weight:800; }
.ready-icon.ok { color:#ffffff; background:var(--green); box-shadow:0 0 24px rgba(45,164,78,.20); }
.ready-icon.wait { color:#ffffff; background:var(--amber); }
.ready-title { color:#1d1d1f; font-size:14px; font-weight:700; }
.ready-sub { color:var(--muted); font-size:12px; margin-top:2px; }
.stButton > button[kind="primary"] {
    position: relative; min-height: 54px; border: 0; border-radius: 16px;
    color: #ffffff; background: linear-gradient(110deg, #0a84ff, #5e5ce6 54%, #7d7aff);
    font-size: 16px; font-weight: 800; letter-spacing: -.01em;
    box-shadow: 0 15px 38px rgba(10,132,255,.25); transition: .22s ease;
    animation: cta-glow 3s ease-in-out infinite;
}
.stButton > button[kind="primary"]:hover { transform: translateY(-2px); filter: brightness(1.06); }
.stButton > button[kind="primary"]:disabled {
    color: #86868b; background: rgba(0,0,0,.06); box-shadow:none; animation:none;
}
.stDownloadButton > button { min-height:44px; border-radius:14px; border:1px solid rgba(0,113,227,.35);
    color:#0071e3; background:rgba(0,113,227,.06); font-weight:700; }

/* Agent 执行轨道 */
.agent-stage { position:relative; overflow:hidden; margin-top:12px; padding:26px 28px;
    border:1px solid var(--line); border-radius:22px; background:var(--panel-strong);
    box-shadow: 0 10px 34px rgba(0,0,0,.05); }
.agent-stage.running::before { content:""; position:absolute; left:-35%; top:0; width:35%; height:2px;
    background:linear-gradient(90deg, transparent, var(--cyan), transparent);
    animation: scan-line 2.2s ease-in-out infinite; }
.stage-head { display:flex; justify-content:space-between; gap:16px; align-items:center; margin-bottom:24px; }
.stage-state { display:flex; align-items:center; gap:9px; color:#1d1d1f; font-weight:720; }
.stage-state .pulse { width:10px; height:10px; border-radius:50%; background:var(--cyan);
    box-shadow:0 0 0 0 rgba(0,113,227,.45); animation:live-pulse 1.5s infinite; }
.stage-state.done .pulse { background:var(--green); animation:none; }
.stage-state.failed .pulse { background:var(--red); animation:none; }
.stage-note { color:var(--muted); font-size:12px; }
.workflow { display:grid; grid-template-columns:repeat(6,1fr); gap:0; }
.flow-step { position:relative; text-align:center; min-width:0; }
.flow-step:not(:last-child)::after { content:""; position:absolute; height:1px; left:calc(50% + 21px);
    right:calc(-50% + 21px); top:19px; background:rgba(0,0,0,.12); }
.flow-step.done:not(:last-child)::after { background:linear-gradient(90deg,var(--green),rgba(0,113,227,.45)); }
.flow-node { position:relative; z-index:1; display:grid; place-items:center; width:38px; height:38px;
    margin:0 auto 9px; border-radius:13px; color:#86868b; background:#ececf0;
    border:1px solid rgba(0,0,0,.06); font-size:12px; font-weight:800; }
.flow-step.active .flow-node { color:#ffffff; border-color:transparent; background:var(--cyan);
    box-shadow:0 0 0 6px rgba(0,113,227,.10), 0 0 28px rgba(0,113,227,.25);
    animation:active-node 1.45s ease-in-out infinite; }
.flow-step.done .flow-node { color:#ffffff; border-color:transparent; background:var(--green); }
.flow-step.failed .flow-node { color:#ffffff; background:var(--red); border-color:transparent; }
.flow-step.skipped .flow-node { color:#9b9ba1; background:#e3e3e8; }
.flow-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#86868b; font-size:11px; }
.flow-step.active .flow-name, .flow-step.done .flow-name { color:#1d1d1f; }
.flow-detail { margin-top:22px; padding-top:16px; border-top:1px solid rgba(0,0,0,.07);
    color:#6e6e73; font-size:12px; line-height:1.65; }

.event-list { padding:3px 2px; }
.event-line { display:grid; grid-template-columns:58px 82px 1fr; gap:10px; align-items:start;
    padding:9px 5px; border-bottom:1px solid rgba(0,0,0,.06); font-size:12px; }
.event-time { color:#9b9ba1; font-variant-numeric:tabular-nums; }
.event-step { color:#6e6e73; font-weight:700; }
.event-msg { color:#3a3a3c; line-height:1.55; }
.event-line.warn .event-step { color:var(--amber); }
.event-line.err .event-step { color:var(--red); }
.event-line.ok .event-step { color:var(--green); }

/* 结果与历史 */
.success-banner { padding:27px 30px; margin:12px 0 18px; border-radius:22px;
    border:1px solid rgba(45,164,78,.30); background:linear-gradient(120deg,rgba(45,164,78,.10),#ffffff);
    box-shadow:0 12px 40px rgba(0,0,0,.06); animation:rise-in .55s ease both; }
.success-banner .label { color:var(--green); font-size:11px; font-weight:800; letter-spacing:.15em; }
.success-banner h2 { color:#1d1d1f; margin:7px 0 6px; font-size:27px; }
.success-banner p { color:#6e6e73; margin:0; font-size:13px; }
[data-testid="stMetric"] { padding:14px 16px; border:1px solid var(--line); border-radius:16px; background:#fafafc; }
[data-testid="stMetricValue"] { color:#1d1d1f; }

@keyframes rise-in { from { opacity:0; transform:translateY(15px); } to { opacity:1; transform:none; } }
@keyframes ambient-turn { to { transform:rotate(360deg); } }
@keyframes ring-spin { to { transform:rotate(360deg); } }
@keyframes core-breathe { 0%,100% { transform:scale(.97) rotate(-2deg); border-radius:38%; }
    50% { transform:scale(1.04) rotate(2deg); border-radius:46%; } }
@keyframes live-pulse { 0% { box-shadow:0 0 0 0 rgba(0,113,227,.40); }
    75%,100% { box-shadow:0 0 0 10px rgba(0,113,227,0); } }
@keyframes active-node { 50% { transform:translateY(-2px); box-shadow:0 0 0 9px rgba(0,113,227,.05),0 0 35px rgba(0,113,227,.30); } }
@keyframes scan-line { 0% { left:-35%; } 70%,100% { left:110%; } }
@keyframes cta-glow { 0%,100% { box-shadow:0 15px 38px rgba(10,132,255,.18); }
    50% { box-shadow:0 17px 46px rgba(10,132,255,.32); } }

@media (max-width: 820px) {
    .agent-hero { grid-template-columns:1fr; padding:32px 27px; }
    .agent-core { display:none; }
    .workflow { grid-template-columns:repeat(3,1fr); row-gap:20px; }
    .flow-step::after { display:none; }
    .event-line { grid-template-columns:52px 70px 1fr; }
}
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation-duration:.01ms !important; animation-iteration-count:1 !important; }
}
"""

st.markdown(
    f"<style>{_DARK_CSS if _THEME == '深色' else _LIGHT_CSS}</style>",
    unsafe_allow_html=True,
)


_WORKFLOW = [
    ("理解规范", "理解格式来源"),
    ("解析文档", "读取文档结构"),
    ("标注角色", "判断段落角色"),
    ("执行排版", "写入 Word 样式"),
    ("视觉自检", "检查渲染结果"),
    ("完成", "交付结果"),
]
_STEP_INDEX = {key: index for index, (key, _) in enumerate(_WORKFLOW)}


def _escape(value):
    return html.escape(str(value or ""), quote=True)


def _llm_available():
    return bool(
        os.environ.get("LLM_BASE_URL")
        and os.environ.get("LLM_API_KEY")
        and os.environ.get("LLM_MODEL")
    )


def _save_upload(uploaded, suffix):
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as handle:
        handle.write(uploaded.getbuffer())
    return path


def _input_heading(number, title, hint):
    st.markdown(
        f'<div class="input-head"><div class="input-no">{number}</div>'
        f'<div><div class="input-title">{_escape(title)}</div>'
        f'<div class="input-hint">{_escape(hint)}</div></div></div>',
        unsafe_allow_html=True,
    )


def _workflow_markup(states, current_step=None, detail=None):
    state_values = set(states.values())
    if "failed" in state_values:
        stage_class, state_class, headline = "", "failed", "Agent 遇到问题"
    elif states.get("完成") == "done":
        stage_class, state_class, headline = "", "done", "Agent 已完成任务"
    else:
        stage_class, state_class, headline = "running", "", "Agent 正在运行"

    nodes = []
    for index, (key, label) in enumerate(_WORKFLOW, 1):
        state = states.get(key, "pending")
        symbol = "✓" if state == "done" else ("—" if state == "skipped" else str(index))
        nodes.append(
            f'<div class="flow-step {state}"><div class="flow-node">{symbol}</div>'
            f'<div class="flow-name">{_escape(label)}</div></div>'
        )
    current_label = dict(_WORKFLOW).get(current_step, current_step or "准备启动")
    detail = detail or "每完成一步，轨道会自动向前推进。"
    return (
        f'<div class="agent-stage {stage_class}"><div class="stage-head">'
        f'<div class="stage-state {state_class}"><span class="pulse"></span>{headline}</div>'
        f'<div class="stage-note">当前 · {_escape(current_label)}</div></div>'
        f'<div class="workflow">{"".join(nodes)}</div>'
        f'<div class="flow-detail">{_escape(detail)}</div></div>'
    )


def _render_step_clock(placeholder, step_label, started_at):
    """浏览器侧持续计时；Python 被模型/渲染器阻塞时也不会停。"""
    elapsed = max(0, int(time.time() - started_at))
    safe_label = _escape(step_label)
    # 计时器是独立 iframe 文档，配色要跟随主题
    if st.session_state.get("ui_theme", "白色") == "深色":
        c_text, c_bg, c_border, c_bold, c_accent = (
            "#cbd6e8", "rgba(10,16,29,.72)", "rgba(150,170,210,.15)", "#fff", "#65e7ff")
    else:
        c_text, c_bg, c_border, c_bold, c_accent = (
            "#3a3a3c", "#ffffff", "rgba(0,0,0,.09)", "#1d1d1f", "#0071e3")
    with placeholder.container():
        st.iframe(
            f"""
<!doctype html><html><head><style>
* {{ box-sizing:border-box; }} body {{ margin:0; color:{c_text}; background:transparent;
font-family:Inter,-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif; }}
.clock {{ height:52px; display:flex; align-items:center; justify-content:space-between; gap:16px;
padding:0 17px; border:1px solid {c_border}; border-radius:14px;
background:{c_bg}; }}
.left {{ display:flex; align-items:center; gap:10px; min-width:0; }}
.wave {{ display:flex; align-items:center; gap:3px; height:18px; }}
.wave i {{ display:block; width:3px; height:6px; border-radius:4px; background:{c_accent};
animation:wave 1s ease-in-out infinite; }} .wave i:nth-child(2){{animation-delay:.14s}}
.wave i:nth-child(3){{animation-delay:.28s}} .wave i:nth-child(4){{animation-delay:.42s}}
.copy {{ white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-size:12px; }}
.copy b {{ color:{c_bold}; }} .timer {{ flex:none; color:{c_accent}; font:700 13px ui-monospace,SFMono-Regular,Menlo,monospace; }}
.clock.slow {{ border-color:rgba(255,200,107,.4); }} .clock.slow .timer {{ color:#e08600; }}
@keyframes wave {{ 0%,100%{{height:5px;opacity:.45}} 50%{{height:17px;opacity:1}} }}
</style></head><body>
<div class="clock" id="clock"><div class="left"><span class="wave"><i></i><i></i><i></i><i></i></span>
<span class="copy" id="copy"><b>{safe_label}</b> 正在处理；计时持续表示页面仍在等待返回</span></div>
<span class="timer" id="timer">00:00</span></div>
<script>
const base={elapsed}; const start=Date.now();
function tick() {{
  const total=base+Math.floor((Date.now()-start)/1000);
  const m=String(Math.floor(total/60)).padStart(2,'0');
  const s=String(total%60).padStart(2,'0');
  document.getElementById('timer').textContent=m+':'+s;
  if(total>=120) {{
    document.getElementById('clock').classList.add('slow');
    document.getElementById('copy').innerHTML='<b>{safe_label}</b> 等待较久，通常仍在等待模型或渲染器；可继续等待或稍后重试';
  }}
}}
tick(); setInterval(tick,1000);
</script></body></html>
""",
            height=58,
            width="stretch",
        )


def _event_markup(events):
    rows = []
    for event in events[-24:]:
        status = event.get("status", "run")
        rows.append(
            f'<div class="event-line {status}"><span class="event-time">{_escape(event["time"])}</span>'
            f'<span class="event-step">{_escape(event["step"])}</span>'
            f'<span class="event-msg">{_escape(event["message"])}</span></div>'
        )
    return '<div class="event-list">' + "".join(rows) + "</div>"


# ---------------- 首屏 ----------------
model_name = os.environ.get("LLM_MODEL", "")
renderer_status = _renderer_status()
agent_state = "模型已连接" if _llm_available() else "等待模型配置"
renderer_name = renderer_status.get("version") or "渲染器未连接"

st.markdown(
    f"""
<section class="agent-hero">
  <div class="hero-copy">
    <div class="eyebrow"><span class="live-dot"></span>Format Agent · {agent_state}</div>
    <h1>把文档交给我。<br>格式这件事，我来完成。</h1>
    <p>告诉我排版要求，再上传原始文档。Agent 会理解规范、识别结构、写入 Word 样式，
       并把每一步状态清楚地展示给你。</p>
    <div class="hero-note"><b>只需完成下方两项</b><span>按钮会在材料齐全后自动点亮</span></div>
  </div>
  <div class="agent-core" aria-hidden="true">
    <div class="ring"></div><div class="ring two"></div><div class="orb">FA</div>
  </div>
</section>
""",
    unsafe_allow_html=True,
)

status_cols = st.columns([1, 1, 1.6, 0.95], vertical_alignment="center")
status_cols[0].caption(f"Agent · {agent_state}")
status_cols[1].caption(f"模型 · {model_name or '未配置'}")
status_cols[2].caption(f"文档渲染 · {renderer_name}")
with status_cols[3]:
    st.segmented_control(
        "界面主题",
        ["白色", "深色"],
        key="ui_theme",
        label_visibility="collapsed",
        width="stretch",
    )

if not _llm_available():
    st.warning(
        "自然语言规范和自动角色识别需要模型配置。你仍可在“高级设置”中上传 "
        "FormatSpec 与 RoleMap，走完全确定性的排版流程。"
    )
if not renderer_status["available"]:
    st.info("没有检测到可用的渲染器（Windows 用 Word，其他系统用 LibreOffice）："
            "DOCX 仍可生成，但前后对比和视觉复核将不可用。")


# ---------------- 输入任务 ----------------
st.markdown('<div class="section-kicker">New mission</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">创建一个排版任务</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="section-help">从左到右完成两项。多数情况下无需打开高级设置。</div>',
    unsafe_allow_html=True,
)

use_demo = st.toggle(
    "先加载内置示例看看效果",
    value=False,
    help="自动使用 assets/spec.txt 和 assets/messy.docx。",
)

left, right = st.columns(2, gap="large")
with left:
    with st.container(border=True):
        _input_heading("1", "告诉 Agent 要什么格式", "用自然语言描述，或给一份排版正确的参考文档。")
        if use_demo:
            spec_mode = "文字说明"
            template_file = None
            with open("assets/spec.txt", encoding="utf-8") as handle:
                spec_text = handle.read()
            st.text_area("已加载的示例规范", value=spec_text, height=190, disabled=True)
            st.success("示例格式要求已准备好")
        else:
            spec_mode = st.radio(
                "格式来源",
                ["文字说明", "参考模板"],
                horizontal=True,
                label_visibility="collapsed",
            )
            spec_text = None
            template_file = None
            if spec_mode == "文字说明":
                spec_text = st.text_area(
                    "描述排版要求",
                    height=190,
                    placeholder=(
                        "例如：标题用方正小标宋二号、居中；正文用仿宋三号、"
                        "每段首行缩进 2 字符；一级标题用黑体……"
                    ),
                    help="不需要使用专业术语，像交代给同事一样描述即可。",
                )
                st.caption("写清标题、正文、页边距等主要要求即可，其余交给 Agent 判断。")
            else:
                template_file = st.file_uploader(
                    "上传排版正确的参考文档",
                    type=["docx"],
                    key="template",
                    help="Agent 会读取参考文档里的字号、字体、间距、标题层级和编号。",
                )
                st.caption("建议模板至少包含一个标题和一段正文。")

with right:
    with st.container(border=True):
        _input_heading("2", "上传需要整理的原始文档", "Agent 不会改写正文内容，只处理结构与格式。")
        if use_demo:
            target_file = None
            st.file_uploader(
                "已加载示例文档",
                type=["docx"],
                key="demo-target",
                disabled=True,
            )
            st.success("示例文档 messy.docx 已准备好")
            st.caption("取消上方“内置示例”即可上传自己的文档。")
        else:
            target_file = st.file_uploader(
                "上传待排版 DOCX",
                type=["docx"],
                key="target",
                help="当前版本支持 DOCX；表格内容会保留原格式。",
            )
            if target_file is not None:
                st.success(f"已接收：{target_file.name}")
            else:
                st.caption("支持 .docx。上传后，下方运行按钮会进入准备状态。")


# 低频技术入口收进高级设置，不干扰主路径。
with st.expander("高级设置 · 预制 JSON / 跳过自动标注", expanded=False):
    st.caption(
        "这里面向熟悉 FormatSpec 和 RoleMap 的高级用户。上传预制规则后，会覆盖上方对应的自动理解步骤。"
    )
    advanced_left, advanced_right = st.columns(2)
    with advanced_left:
        spec_json_file = st.file_uploader(
            "FormatSpec JSON（可选）",
            type=["json"],
            key="spec-json",
            help="直接提供格式规则，跳过对文字说明或模板的理解。",
        )
    with advanced_right:
        rolemap_json_file = st.file_uploader(
            "RoleMap JSON（可选）",
            type=["json"],
            key="rolemap-json",
            help="直接提供段落角色，跳过 Agent 自动标注。",
        )
    if spec_json_file is not None:
        st.info("本次将优先使用预制 FormatSpec；上方格式来源不会参与规则抽取。")


# ---------------- 主行动区 ----------------
target_ready = use_demo or target_file is not None
if spec_json_file is not None or use_demo:
    source_ready = True
elif spec_mode == "文字说明":
    source_ready = bool(spec_text and spec_text.strip())
else:
    source_ready = template_file is not None
can_run = target_ready and source_ready

missing = []
if not source_ready:
    missing.append("格式要求")
if not target_ready:
    missing.append("原始文档")

with st.container(border=True):
    action_left, action_right = st.columns([1.9, 1], gap="large", vertical_alignment="center")
    with action_left:
        if can_run:
            st.markdown(
                '<div class="readiness"><div class="ready-icon ok">✓</div><div>'
                '<div class="ready-title">材料齐全，Agent 可以开始工作</div>'
                '<div class="ready-sub">点击右侧按钮后，你会看到每一步的实时状态与计时。</div></div></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="readiness"><div class="ready-icon wait">!</div><div>'
                f'<div class="ready-title">还差：{_escape("、".join(missing))}</div>'
                '<div class="ready-sub">完成上方缺失项后，运行按钮会自动点亮。</div></div></div>',
                unsafe_allow_html=True,
            )
        verify = st.checkbox(
            "完成排版后，再做一次视觉复核",
            value=False,
            disabled=not renderer_status["available"],
            help="会把排版结果渲染成图片，并调用多模态模型检查；耗时会更长。",
        )
    with action_right:
        run = st.button(
            "让 Agent 开始排版 →",
            type="primary",
            width="stretch",
            disabled=not can_run,
        )


# ---------------- Agent 执行 ----------------
if run and can_run:
    st.markdown('<div class="section-kicker">Live agent</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Agent 正在处理这份文档</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-help">轨道显示整体进度；下方计时器在模型或渲染器等待期间也会持续运行。</div>',
        unsafe_allow_html=True,
    )

    workflow_states = {key: "pending" for key, _ in _WORKFLOW}
    workflow_box = st.empty()
    clock_box = st.empty()
    events = []
    step_started_at = time.time()
    runtime = {"current_step": None, "started_at": step_started_at}

    workflow_box.markdown(
        _workflow_markup(workflow_states, detail="正在唤醒 Agent，准备读取任务材料。"),
        unsafe_allow_html=True,
    )
    _render_step_clock(clock_box, "准备任务", step_started_at)

    with st.expander("实时事件流 · 遇到长时间等待时可在这里查看", expanded=True):
        log_box = st.empty()

    def on_event(event):
        step = str(event.get("step") or "Agent")
        status = str(event.get("status") or "run")
        message = str(event.get("message") or "")

        if step in _STEP_INDEX:
            if runtime["current_step"] != step:
                runtime["current_step"] = step
                runtime["started_at"] = time.time()
            if status == "run":
                workflow_states[step] = "active"
            elif status == "ok":
                workflow_states[step] = "done"
            elif status == "err":
                workflow_states[step] = "failed"
            elif workflow_states.get(step) != "done":
                workflow_states[step] = "active"

            # 一旦进入后续步骤，前面的 pending 项即视为已完成；视觉复核可跳过。
            step_index = _STEP_INDEX[step]
            for earlier_key, _ in _WORKFLOW[:step_index]:
                if workflow_states[earlier_key] == "pending":
                    workflow_states[earlier_key] = (
                        "skipped"
                        if earlier_key == "视觉自检" and step == "完成" and not verify
                        else "done"
                    )

        events.append(
            {
                "time": datetime.now().strftime("%H:%M:%S"),
                "step": step,
                "message": message,
                "status": status,
            }
        )
        active_step = runtime["current_step"]
        workflow_box.markdown(
            _workflow_markup(workflow_states, active_step, message),
            unsafe_allow_html=True,
        )
        if workflow_states.get("完成") != "done" and "failed" not in workflow_states.values():
            _render_step_clock(
                clock_box,
                dict(_WORKFLOW).get(active_step, active_step or "处理中"),
                runtime["started_at"],
            )
        else:
            clock_box.empty()
        log_box.markdown(_event_markup(events), unsafe_allow_html=True)

    target_path = "assets/messy.docx" if use_demo else _save_upload(target_file, ".docx")
    out_dir = tempfile.mkdtemp(prefix="format-agent-")
    out_path = os.path.join(out_dir, "formatted.docx")
    report_path = os.path.join(out_dir, "report.md")

    try:
        kwargs = {
            "target_path": target_path,
            "out_path": out_path,
            "report_path": report_path,
            "verify": verify,
        }
        if spec_json_file is not None:
            kwargs["spec"] = json.loads(spec_json_file.getvalue().decode("utf-8"))
            validate_spec(kwargs["spec"])
        elif use_demo:
            # 一键示例使用项目内置标准答案，保证演示稳定且不产生外部模型调用。
            with open("assets/spec_std.json", encoding="utf-8") as handle:
                kwargs["spec"] = json.load(handle)
        elif spec_mode == "参考模板":
            kwargs["template_path"] = _save_upload(template_file, ".docx")
        else:
            kwargs["spec_text"] = spec_text

        if rolemap_json_file is not None:
            kwargs["rolemap"] = {
                int(key): value
                for key, value in json.loads(
                    rolemap_json_file.getvalue().decode("utf-8")
                ).items()
            }
        elif use_demo:
            with open("assets/rolemap_std.json", encoding="utf-8") as handle:
                kwargs["rolemap"] = {
                    int(key): value for key, value in json.load(handle).items()
                }

        result = Agent(on_event=on_event).run(**kwargs)
    except Exception as exc:  # 演示界面兜底：错误必须明确落在当前步骤。
        failed_step = runtime["current_step"]
        if failed_step in workflow_states:
            workflow_states[failed_step] = "failed"
        on_event({"step": failed_step or "Agent", "message": str(exc), "status": "err"})
        st.error(f"任务没有完成：{exc}")
        st.caption("你的原始文档没有被修改。检查事件流中的最后一条信息后，可以修正输入并重试。")
        st.stop()

    # ---------------- 结果 ----------------
    st.markdown(
        f"""
<div class="success-banner">
  <div class="label">MISSION COMPLETE</div>
  <h2>排版完成，结果已经准备好</h2>
  <p>Agent 共处理 {len(result['changelog'])} 个段落，生成可继续编辑的 Word 命名样式和完整修改记录。</p>
</div>
""",
        unsafe_allow_html=True,
    )

    summary_cols = st.columns(4)
    summary_cols[0].metric("解析段落", len(result["paragraphs"]))
    summary_cols[1].metric("已处理段落", len(result["changelog"]))
    summary_cols[2].metric("命名样式", len(result["stylemap"]))
    summary_cols[3].metric("视觉问题", len([i for i in result["issues"] if not i.get("pass")]))

    result_tab, summary_tab, technical_tab = st.tabs(["下载结果", "处理摘要", "技术详情"])
    with result_tab:
        st.markdown("#### 先下载排版后的 Word 文档")
        download_left, download_right = st.columns(2)
        with open(result["out_path"], "rb") as handle:
            download_left.download_button(
                "下载排版后的 DOCX",
                handle.read(),
                "formatted.docx",
                width="stretch",
                type="primary",
            )
        with open(result["report_path"], "rb") as handle:
            download_right.download_button(
                "下载修改报告",
                handle.read(),
                "format-report.md",
                width="stretch",
            )
        with st.expander("在页面中查看修改报告"):
            with open(result["report_path"], encoding="utf-8") as handle:
                st.markdown(handle.read())

    with summary_tab:
        st.caption("这些是 Agent 对每个段落作出的结构判断。")
        style_by_idx = {
            change["idx"]: change.get("style_name", "")
            for change in result["changelog"]
        }
        st.dataframe(
            [
                {
                    "段落": paragraph["idx"],
                    "角色": result["rolemap"].get(paragraph["idx"], "未处理"),
                    "应用样式": style_by_idx.get(paragraph["idx"], "保留原样式"),
                    "内容": paragraph["text"][:52],
                }
                for paragraph in result["paragraphs"]
            ],
            width="stretch",
            hide_index=True,
        )
        if result["issues"]:
            st.markdown("#### 视觉复核记录")
            st.dataframe(result["issues"], width="stretch", hide_index=True)

    with technical_tab:
        st.caption("面向开发者和高级用户的 JSON 中间产物；普通使用无需处理。")
        tech_one, tech_two, tech_three = st.tabs(["FormatSpec", "RoleMap", "Word 样式"])
        with tech_one:
            st.json(result["spec"])
        with tech_two:
            st.json({str(key): value for key, value in sorted(result["rolemap"].items())})
        with tech_three:
            st.dataframe(
                [{"角色": role, "Word 命名样式": name} for role, name in result["stylemap"].items()],
                width="stretch",
                hide_index=True,
            )

    source_name = "内置示例 messy.docx" if use_demo else target_file.name
    save_run(
        result["out_path"],
        result["report_path"],
        {
            "source_name": source_name,
            "spec_mode": "内置示例" if use_demo else ("预制规则" if spec_json_file else spec_mode),
            "issues_count": len(result.get("issues") or []),
        },
    )

    st.markdown('<div class="section-kicker">Visual compare</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">排版前后对比</div>', unsafe_allow_html=True)
    try:
        with st.spinner("正在生成前后对比图……"):
            from core.render import render_docx_to_png

            before_pages = render_docx_to_png(target_path, os.path.join(out_dir, "before"))
            after_pages = render_docx_to_png(result["out_path"], os.path.join(out_dir, "after"))
    except Exception as exc:
        st.warning(f"DOCX 已正常生成，但本机暂时无法生成对比图：{exc}")
    else:
        before_col, after_col = st.columns(2, gap="large")
        before_col.caption("排版前")
        after_col.caption("排版后")
        for page_index in range(min(len(before_pages), len(after_pages))):
            before_col.image(before_pages[page_index], caption=f"第 {page_index + 1} 页")
            after_col.image(after_pages[page_index], caption=f"第 {page_index + 1} 页")


# ---------------- 历史记录 ----------------
runs = list_runs()
if runs:
    st.markdown('<div class="section-kicker">Memory</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">最近完成的任务</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-help">历史结果默认收起，不干扰当前任务。</div>',
        unsafe_allow_html=True,
    )
    with st.expander(f"查看历史任务（{len(runs)}）", expanded=False):
        for record in runs:
            columns = st.columns([4.2, 1.4, 1.5, 1.5], vertical_alignment="center")
            columns[0].markdown(
                f"**{_escape(record.get('source_name', '未命名文档'))}**  \n"
                f"<span style='color:#7f8ba1;font-size:12px'>{_escape(record.get('time', ''))}</span>",
                unsafe_allow_html=True,
            )
            columns[1].caption(record.get("spec_mode", ""))
            with open(record["docx"], "rb") as handle:
                columns[2].download_button(
                    "DOCX",
                    handle.read(),
                    file_name=f"formatted_{record['run_id']}.docx",
                    key="history-docx-" + record["run_id"],
                    width="stretch",
                )
            if os.path.isfile(record["report"]):
                with open(record["report"], "rb") as handle:
                    columns[3].download_button(
                        "报告",
                        handle.read(),
                        file_name=f"report_{record['run_id']}.md",
                        key="history-report-" + record["run_id"],
                        width="stretch",
                    )
            st.divider()
