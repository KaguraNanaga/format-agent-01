# Agent 编排器 —— 把整条流水线包装成带"工作日志"的事件流，供演示界面实时展示。
# 事件: {"step": 步骤名, "message": 人话描述, "status": run|ok|warn|err, "data": 任意}
# 演示故事: 理解归 AI，动手归代码，中间用 JSON 交接 —— 日志把这个过程直播出来。

import json
import os

from core.apply import apply_format, write_report
from core.extract import extract_paragraphs
from core.schema import validate_spec


class Agent:
    """任务式排版 Agent：给它格式来源 + 目标文档，它自主完成理解→执行→自检。"""

    def __init__(self, llm=None, on_event=None):
        # on_event(event_dict)；llm 为 None 时，需要 LLM 的步骤才会延迟构造
        self._llm = llm
        self.on_event = on_event or (lambda event: None)

    def _emit(self, step, message, status="run", data=None):
        self.on_event({"step": step, "message": message, "status": status, "data": data})

    def _get_llm(self):
        if self._llm is None:
            from core.llm import LLMClient
            self._llm = LLMClient(on_event=lambda msg: self._emit("llm", msg, status="warn"))
        return self._llm

    def run(self, target_path, out_path, spec_text=None, spec=None,
            template_path=None, template_rolemap=None, rolemap=None,
            verify=False, report_path=None):
        """跑完整流程，返回结果 dict（spec/rolemap/changelog/issues/paths）。"""
        report_path = report_path or os.path.splitext(out_path)[0] + "_report.md"

        # ① 理解格式规范 → FormatSpec
        self._emit("理解规范", "开始理解格式来源，抽取格式规则 ...")
        if spec is not None:
            validate_spec(spec)
            self._emit("理解规范", "FormatSpec 由用户直接给定（JSON），校验通过", status="ok")
        elif template_path is not None:
            from core.rules_from_template import extract_rules_from_template
            if template_rolemap is None:
                self._emit("理解规范", "正在解析模板文档结构，标注模板段落角色 ...")
                tpl_paras = extract_paragraphs(template_path)
                from core.label_roles import label_roles
                template_rolemap = label_roles(
                    tpl_paras, self._get_llm(),
                    on_event=lambda m: self._emit("理解规范", m))
            spec = extract_rules_from_template(template_path, template_rolemap)
            self._emit("理解规范",
                       f"已从模板确定性读取出 {len(spec['roles'])} 个角色的格式规则",
                       status="ok")
        elif spec_text is not None:
            from core.rules_from_text import extract_rules
            spec = extract_rules(
                spec_text, self._get_llm(),
                on_event=lambda m: self._emit("理解规范", m, status="warn"))
            self._emit("理解规范",
                       f"规范理解完成：识别出 {len(spec['roles'])} 个角色的格式规则",
                       status="ok")
        else:
            raise ValueError("必须提供 spec_text / spec / template_path 之一")

        # ② 解析目标文档结构
        self._emit("解析文档", "正在解析目标文档结构 ...")
        paragraphs = extract_paragraphs(target_path)
        n_table = sum(1 for p in paragraphs if p["in_table"])
        self._emit("解析文档",
                   f"发现 {len(paragraphs)} 个段落（{n_table} 段在表格内，不参与重排）",
                   status="ok", data=paragraphs)

        # ③ 标注段落角色 → RoleMap
        if rolemap is not None:
            self._emit("标注角色", "RoleMap 由用户直接给定（JSON），跳过标注", status="ok")
        else:
            self._emit("标注角色", "正在逐段判断角色（标题/正文/落款/日期 ...）")
            from core.label_roles import label_roles
            rolemap = label_roles(
                paragraphs, self._get_llm(),
                on_event=lambda m: self._emit("标注角色", m))
            counts = {}
            for r in rolemap.values():
                counts[r] = counts.get(r, 0) + 1
            summary = "、".join(f"{k}×{v}" for k, v in sorted(counts.items()))
            self._emit("标注角色", f"角色标注完成：{summary}", status="ok", data=rolemap)

        # ④ 确定性执行排版
        self._emit("执行排版", "正在按 FormatSpec × RoleMap 逐段改写文档（确定性代码，AI 不碰 docx）...")
        changelog = apply_format(target_path, spec, rolemap, out_path)
        write_report(changelog, spec, report_path)
        n_changed = sum(1 for c in changelog if c["changed_fields"])
        self._emit("执行排版",
                   f"排版完成：{n_changed} 个段落被改写，输出 {os.path.basename(out_path)}",
                   status="ok", data=changelog)

        # ⑤ 视觉自检（可选，一轮定向修复，不做开放循环）
        issues, applied = [], []
        if verify:
            self._emit("视觉自检", "正在把排版结果渲染成图，交给视觉模型对照规范质检 ...")
            from core.verify_visual import apply_fixes, verify_visual
            png_dir = os.path.splitext(out_path)[0] + "_verify_render"
            issues = verify_visual(out_path, spec, self._get_llm(), png_dir)
            failed = [i for i in issues if not i["pass"]]
            if not failed:
                self._emit("视觉自检", f"自检通过：{len(issues)} 项检查全部符合规范", status="ok")
            else:
                self._emit("视觉自检",
                           f"发现 {len(failed)} 项不符："
                           + "、".join(f"{i['role']}.{i['field']}" for i in failed),
                           status="warn", data=issues)
                spec, applied = apply_fixes(spec, failed)
                if applied:
                    self._emit("视觉自检",
                               f"已定向修复 {len(applied)} 项，正在重排 ...", status="warn")
                    changelog = apply_format(target_path, spec, rolemap, out_path)
                    write_report(changelog, spec, report_path)
                    self._emit("视觉自检", "修复后重排完成", status="ok")
                else:
                    self._emit("视觉自检",
                               "这些问题无法安全自动修复，已保留在问题清单中供人工处理",
                               status="warn")

        self._emit("完成", "全部流程结束", status="ok")
        return {
            "spec": spec, "paragraphs": paragraphs, "rolemap": rolemap,
            "changelog": changelog, "issues": issues, "applied_fixes": applied,
            "out_path": out_path, "report_path": report_path,
        }
