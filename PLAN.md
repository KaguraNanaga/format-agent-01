# 通用格式排版 Agent — 完整实施方案（黑客松执行版）

> 本文件自包含：新 session 只需读完本文件 + 三个已验证模块即可开工。
> 比赛 8-28 晚 18:00 已开始；目标：**今晚做出端到端 demo**，明天做视觉验证和演示打磨。

## 0. 当前状态（8-28 晚已提前完成）

今晚排期全部完成，且明天的两项也提前做完：

- ✅ `core/`：llm / schema / extract / rules_from_text / rules_from_template / label_roles /
  apply / verify_visual / agent（事件流编排器，CLI 和界面共用）
- ✅ `main.py` CLI、`app.py` Streamlit 演示界面（Agent 工作日志实时直播 + 一键内置示例）
- ✅ 测试素材 `assets/`（messy.docx + spec.txt + 标准答案 JSON），端到端+渲染图验证通过
- ⏳ 真模型联调：代码就绪，等 `LLM_BASE_URL/LLM_API_KEY/LLM_MODEL` 配好即可
- 明天只剩：真机联调 → 演示排练（14:30 冻结）→ 有余力再做视觉读模板加分项

模板读规则做成了**纯确定性方案**（effective_props 读生效属性），不依赖视觉模型。

## 1. 目标与演示故事

用户丢进两样东西：**格式来源**（一段规范文字，或一份模板 docx）+ **待排版的目标文档**，
Agent 阅读并理解两者，输出按该格式排好版的 docx 和一份修改对照报告。

演示一句话：**"理解归 AI，动手归代码，中间用 JSON 交接。"**
界面要展示 Agent 读出的 FormatSpec 和段落角色标注——让评委看见"理解"发生。

## 2. 核心架构

```
格式源(规范文字 / 模板docx)
    │  ① 规则抽取(LLM / VLM+XML)
    ▼
FormatSpec(JSON 中间层) ◄── 全系统的核心契约
    │
目标docx ── ② 结构抽取(python-docx) ──► 段落清单 ── ③ 角色标注(LLM) ──► RoleMap
    │                                                                    │
    └──────────────── ④ 执行器(确定性代码, 应用 FormatSpec×RoleMap) ◄──────┘
                                │
                                ▼
                      输出docx + 修改对照报告
                                │
                      ⑤ 渲染成图 → VLM 视觉验证 → 结构化问题清单（→ 一次定向修复）
```

铁律：**LLM 只产出 FormatSpec 和 RoleMap 两个结构化结果，永远不直接生成/修改 docx。**
所有 XML 修改由确定性代码完成。

## 3. 新仓库目录结构

```
format-agent/
  PLAN.md                  ← 本文件
  core/
    executor.py            ← 已验证，直接复制自源仓库 docs/hackathon-executor.py
    effective_props.py     ← 已验证，直接复制自源仓库 docs/hackathon-effective-props.py
    render.py              ← 已验证，直接复制自源仓库 docs/hackathon-render.py
    schema.py              ← FormatSpec 校验器 ✅
    llm.py                 ← OpenAI 兼容客户端 + 重试 + 视觉调用 ✅
    extract.py             ← docx → 段落清单 ✅
    rules_from_text.py     ← 规范文字 → FormatSpec ✅
    rules_from_template.py ← 模板 docx → FormatSpec（确定性，不依赖 VLM）✅
    label_roles.py         ← 段落清单 → RoleMap ✅
    apply.py               ← 执行器接线 + 对照报告 ✅
    verify_visual.py       ← 视觉验证 + 一轮定向修复 ✅
    agent.py               ← 事件流编排器（CLI/界面共用）✅
  main.py                  ← CLI（薄壳，走 agent.py）
  app.py                   ← Streamlit 演示界面（Agent 工作日志直播）
  assets/                  ← 测试文档、规范文字、人工标准答案 JSON
  out/                     ← 输出
```

**已验证模块来源**（本机实测通过，复制即可，不要重写）：
`D:\AI\claudeprojects\docformatpro\docformatter-pro-private\docs\hackathon-{executor,effective-props,render}.py`
环境：`.venv-win7`（python-docx 1.2.0、pywin32、PyMuPDF 1.24.11、Word COM 可用；无 LibreOffice）。

## 4. FormatSpec Schema（定稿）

```json
{
  "page": {
    "size": "A4",
    "margin": { "top_mm": 37, "bottom_mm": 35, "left_mm": 28, "right_mm": 26 },
    "line_grid": { "line_pt": 28 }
  },
  "roles": {
    "title":     { "font_eastasia": "方正小标宋简体", "font_ascii": "Times New Roman",
                   "size_pt": 22, "bold": false, "alignment": "center",
                   "line_spacing": { "type": "exact", "pt": 28 } },
    "heading_1": { "font_eastasia": "黑体", "size_pt": 16, "alignment": "left",
                   "first_line_indent_chars": 2,
                   "line_spacing": { "type": "exact", "pt": 28 } },
    "body":      { "font_eastasia": "仿宋_GB2312", "font_ascii": "Times New Roman",
                   "size_pt": 16, "alignment": "justify",
                   "first_line_indent_chars": 2,
                   "line_spacing": { "type": "exact", "pt": 28 } }
  }
}
```

角色 Base 闭集：`title / subtitle / heading_1 / heading_2 / heading_3 / body /
signature / date / attachment_label / attachment / other`。
**可扩展**：规范文字可自定义角色键；执行器对未知角色按 `other` 处理（保留原格式）。

**校验器规则（schema.py 必须实现）**：
- `roles.body` 必填；每个角色字段齐全（font_eastasia、size_pt、alignment 至少）
- 数值边界：`size_pt ∈ [8,72]`、`margin ∈ [5,50]mm`、`first_line_indent_chars ∈ [0,8]`
- 非法输出带校验错误回喂 LLM 重试，≤2 次

## 5. LLM 调用约定（llm.py）

- OpenAI 兼容接口，配置走环境变量（场地 tokens 到场再填，自备 key 兜底）：
  `LLM_BASE_URL / LLM_API_KEY / LLM_MODEL`（统一使用支持图片输入的多模态模型）
  - Kimi: `https://api.moonshot.cn/v1`；GLM: `https://open.bigmodel.cn/api/paas/v4`
- temperature=0；JSON 模式输出；超时 60s；指数退避重试 ≤2 次，校验失败把错误信息拼进 prompt 再试
- 不引框架，直接 `requests`/`openai` 库打 HTTP，减少现场依赖风险

## 6. 三个 Prompt 草稿

### 6.1 规则抽取（规范文字 → FormatSpec）

```
你是公文/文章排版规范解析器。把用户给的格式规范文字，转换成下面这个 JSON schema，
只输出 JSON，不要任何解释。
schema 角色枚举: title/subtitle/heading_1/heading_2/heading_3/body/signature/date/
attachment_label/attachment/other。规范里没提到的角色不要输出；没提到的字段不要编。
字段: font_eastasia(中文字体名)/font_ascii/size_pt(磅)/bold/alignment(left|center|
right|justify)/first_line_indent_chars(字符数)/line_spacing({type:exact|multiple, pt})。
页面字段: page.margin(毫米)/page.line_grid.line_pt。
数值必须合理: size_pt 8~72, margin 5~50。
规范文字如下：
<<<SPEC_TEXT>>>
```

### 6.2 角色标注（段落清单 → RoleMap）

```
你是文档结构标注器。给每一段标注角色，角色只能从枚举里选:
title/subtitle/heading_1/heading_2/heading_3/body/signature/date/attachment_label/
attachment/other。
判断依据: 文字内容、位置顺序、当前格式提示。落款单位通常在末尾、署名感强;
日期含"年/月/日"; 标题通常在最前且独立成行。
输入是 JSON 数组 [{idx, text, size_pt, bold, alignment}]，
输出严格为 [{"idx": 0, "role": "title"}, ...]，必须覆盖所有 idx，不多不少。
段落清单：
<<<PARAGRAPHS_JSON>>>
```

### 6.3 视觉验证（明天做）

```
你是排版质检员。对照检查清单逐条检查这页文档渲染图。
输出严格 JSON: [{"role": "...", "field": "...", "pass": true/false,
"observed": "图上看到的实际值", "expected": "清单要求值"}]。只输出有把握判断的项。
```

## 7. 模块规格

### extract.py（30 分钟）

`extract_paragraphs(docx_path) -> list[dict]`：
遍历 `doc.paragraphs`，每段输出 `{idx, text(截前80字), size_pt, bold, alignment,
style_name, in_table}`。`size_pt/bold` 用 `effective_props.get_paragraph_effective_font`。
`in_table=True` 的段落 v1 不参与重排。

### rules_from_text.py（1 小时）

`extract_rules(spec_text, llm) -> FormatSpec`：6.1 prompt → JSON → schema.py 校验 →
失败回喂重试 ≤2 次。

### label_roles.py（1 小时）

`label_roles(paragraphs, llm) -> dict[int, str]`：每 40 段一批送 6.2 prompt；
校验 role ∈ 枚举、idx 全覆盖；失败重试。

### executor 接线（1 小时）

`apply_format(docx_path, spec, rolemap, out_path) -> changelog`：
对每个段落按 RoleMap 取角色、从 FormatSpec 取规则，调用 `core/executor.py` 的
`set_run_fonts / set_paragraph_fixed_spacing / set_first_line_indent_chars`，
对齐用 `WD_ALIGN_PARAGRAPH`；页边距用 `section.top_margin = Mm(x)` 等；
行网格调 `set_doc_grid`。changelog 记录 `{idx, role, changed_fields}`，
最后写对照报告 markdown。

### main.py（30 分钟）

```
python main.py --spec assets/spec.txt --target assets/messy.docx --out out/formatted.docx
```
串起 extract → rules → label → apply → 输出对照报告。

## 8. 今晚排期（从现在起，目标=端到端跑通）

| 用时 | 任务 | 验收 |
|---|---|---|
| 0:00–0:30 | 建仓库、复制三个已验证模块、llm.py 调通 | 模型能返回 |
| 0:30–1:00 | schema.py 校验器 | 非法 JSON 能拦 |
| 1:00–2:00 | executor 接线 apply_format | 手写 FormatSpec+RoleMap 改出正确 docx |
| 2:00–3:00 | rules_from_text + label_roles | 两个 prompt 真模型跑通 |
| 3:00–4:00 | main.py 串联 + 演示文档端到端 | **demo 诞生** |
| 4:00 后 | 修 bug、备份、睡 | 留体力给明天 |

**砍线**：23:30 还没到"端到端"，砍 rules_from_text（规范文字改成人肉 JSON 喂），保演示链路。
模板视觉读规则（格式源第二种）不在今晚范围，明天有余力再做。

## 9. 明天排期（8:30–18:00 现场）

1. verify_visual.py：render.py 渲染输出 → 6.3 prompt → 结构化问题 `[{role, field,
   observed, expected}]` → 代码只改 FormatSpec 对应字段重跑一次（不做开放循环）
2. 简单演示界面（Streamlit 或静态页）：上传文档+规范 → 展示 FormatSpec、RoleMap、
   前后对比图
3. 模板 docx 视觉读规则（加分项，翻车就砍）
4. 14:30 冻结功能 → 修 bug + 演示排练两遍

## 10. 验收标准

- 今晚：演示文档端到端跑通，输出 docx 用 Word 打开人工核对（标题居中、正文缩进、
  行距正确），对照报告可读
- 明天：视觉验证能报出至少一类真实错误；演示 3 分钟脱稿两遍

## 11. 风险与对策

| 风险 | 对策 |
|---|---|
| LLM 输出脏值 | schema.py 数值边界校验 + 回喂重试 |
| 现场 tokens 限流 | 环境变量切自备 key；减少调用次数 |
| 渲染依赖 | 只用 Word COM（已验证）；render.py 已用 DispatchEx |
| Kimi/GLM 视觉不稳 | 主线不依赖视觉；视觉验证是独立加分项 |
| 执行器 XML 细节 | 三处关键写法已实测，直接复用 core/executor.py |

## 12. 队友任务（并行，不占代码关键路径）

- 手写 3 份测试文档（错误典型的演示报告 1 份 + 规范文字 1 份 + 模板 1 份）
- 手写每份文档对应的标准 FormatSpec JSON（当验收基准，也当 LLM 失败时的降级输入）
- 准备演示话术初稿（他主讲痛点故事）
