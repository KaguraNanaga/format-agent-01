# OpenAI 兼容 LLM 客户端 —— 不引框架，直接 requests 打 HTTP。
# 配置走环境变量（场地 tokens 到场再填，自备 key 兜底）：
#   LLM_BASE_URL / LLM_API_KEY / LLM_MODEL / LLM_VISION_MODEL
#   Kimi: https://api.moonshot.cn/v1 ；GLM: https://open.bigmodel.cn/api/paas/v4
# 约定：temperature=0；超时 60s；指数退避重试 <=2 次。

import base64
import json
import os
import time

import requests


class LLMError(Exception):
    """LLM 调用失败（网络/HTTP/解析），重试耗尽后抛出。"""


class LLMClient:
    def __init__(self, base_url=None, api_key=None, model=None, vision_model=None,
                 timeout=60, max_retries=2, on_event=None):
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL") or "").rstrip("/")
        self.api_key = api_key or os.environ.get("LLM_API_KEY") or ""
        self.model = model or os.environ.get("LLM_MODEL") or ""
        self.vision_model = vision_model or os.environ.get("LLM_VISION_MODEL") or self.model
        self.timeout = timeout
        self.max_retries = max_retries
        self.on_event = on_event or (lambda msg: None)
        if not self.base_url or not self.api_key or not self.model:
            raise LLMError(
                "缺少 LLM 配置：请设置环境变量 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL"
            )

    def chat_json(self, prompt, model=None):
        """发单轮 user prompt，要求模型输出 JSON，返回解析后的对象。
        失败（HTTP 错误/超时/JSON 解析失败）指数退避重试，耗尽后抛 LLMError。
        """
        last_err = None
        for attempt in range(self.max_retries + 1):
            try:
                text = self._chat(prompt, model=model, json_mode=True)
                return _parse_json(text)
            except Exception as e:  # noqa: BLE001 —— 统一收口为重试
                last_err = e
                if attempt < self.max_retries:
                    self.on_event(f"LLM 调用失败（{e}），{2 ** attempt}s 后重试（第 {attempt + 1} 次）")
                    time.sleep(2 ** attempt)  # 1s, 2s
        raise LLMError(f"LLM 调用失败（重试 {self.max_retries} 次后放弃）: {last_err}")

    def _chat(self, prompt, model=None, json_mode=True, image_paths=None):
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if image_paths:
            content = [{"type": "text", "text": prompt}]
            for path in image_paths:
                with open(path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                })
            messages = [{"role": "user", "content": content}]
        else:
            messages = [{"role": "user", "content": prompt}]
        body = {
            "model": model or self.model,
            "messages": messages,
            "temperature": 0,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        resp = requests.post(url, headers=headers, json=body, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def chat_vision_json(self, prompt, image_paths, model=None):
        """带图调用（视觉模型）：prompt + png 列表 → 解析后的 JSON 对象。
        默认用 LLM_VISION_MODEL，重试策略同 chat_json。
        """
        last_err = None
        for attempt in range(self.max_retries + 1):
            try:
                text = self._chat(prompt, model=model or self.vision_model,
                                  json_mode=True, image_paths=image_paths)
                return _parse_json(text)
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt < self.max_retries:
                    self.on_event(f"视觉模型调用失败（{e}），{2 ** attempt}s 后重试（第 {attempt + 1} 次）")
                    time.sleep(2 ** attempt)
        raise LLMError(f"视觉模型调用失败（重试 {self.max_retries} 次后放弃）: {last_err}")


def _parse_json(text):
    """从模型输出里抠出 JSON。容忍 ```json 围栏和前后杂文本。"""
    text = text.strip()
    if text.startswith("```"):
        # 去掉首尾围栏行
        lines = text.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 找第一个 { 或 [ 到最后一个 } 或 ]
        start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
        end = max(text.rfind("}"), text.rfind("]"))
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise
