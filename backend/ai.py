from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .storage import store
from .config import settings

# Provider endpoint configurations
PROVIDER_ENDPOINTS = {
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "groq":       "https://api.groq.com/openai/v1/chat/completions",
    "deepseek":   "https://api.deepseek.com/v1/chat/completions",
    "mistral":    "https://api.mistral.ai/v1/chat/completions",
    "google":     "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    "kilo":       "https://api.kilo.ai/v1/chat/completions",
}


class AIUnavailable(RuntimeError):
    pass


class AIService:
    def __init__(self) -> None:
        pass

    def _endpoint(self, provider: str) -> str:
        if not provider or provider == "default":
            return settings.ai_base_url
        if provider.startswith("custom|"):
            parts = provider.split("|", 1)
            custom_url = parts[1].strip()
            if not custom_url.endswith("/chat/completions"):
                if custom_url.endswith("/"):
                    custom_url += "chat/completions"
                else:
                    custom_url += "/chat/completions"
            return custom_url
        return PROVIDER_ENDPOINTS.get(provider, settings.ai_base_url)

    def _headers(self, provider: str, api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async def stream(
        self,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int = 900,
        provider: str = "openrouter",
    ) -> AsyncIterator[str]:
        # Fallback to default 9Router if credentials are not provided
        if not api_key:
            provider = "default"
            api_key = settings.supabase_key or "dummy"
        if not model:
            model = "default"

        endpoint = self._endpoint(provider)
        headers = self._headers(provider, api_key)

        async with httpx.AsyncClient() as client:
            try:
                # Use standard OpenAI payload format
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.7,
                    "stream": True,
                }
                async with client.stream(
                    "POST",
                    endpoint,
                    headers=headers,
                    json=payload,
                    timeout=120.0,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                delta = data.get("choices", [{}])[0].get("delta", {})
                                text = delta.get("content", "")
                                if text:
                                    yield text
                            except json.JSONDecodeError:
                                continue
            except AIUnavailable:
                raise
            except Exception as exc:
                raise AIUnavailable(f"Inference failed ({provider}): {exc}")

    async def complete(
        self,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int = 500,
        temperature: float = 0.3,
        provider: str = "openrouter",
    ) -> str:
        # Fallback to default 9Router if credentials are not provided
        if not api_key:
            provider = "default"
            api_key = settings.supabase_key or "dummy"
        if not model:
            model = "default"

        endpoint = self._endpoint(provider)
        headers = self._headers(provider, api_key)

        async with httpx.AsyncClient() as client:
            try:
                # Use standard OpenAI payload format
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "stream": False,
                }
                response = await client.post(
                    endpoint,
                    headers=headers,
                    json=payload,
                    timeout=120.0,
                )
                response.raise_for_status()
                data = response.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "")
            except AIUnavailable:
                raise
            except Exception as exc:
                raise AIUnavailable(f"Inference failed ({provider}): {exc}")

    def context(self, workspace_id: str) -> str:
        brain = store.workspace_path(workspace_id) / "brain"
        style = store.read_json(brain / "style_profile.json", {"rules": []}).get("rules", [])
        thinking = store.read_json(brain / "thinking_profile.json", {"patterns": []}).get("patterns", [])
        rules = store.read_json(brain / "rules.json", {"items": []}).get("items", [])
        memory = store.read_json(brain / "memory.json", {"items": []}).get("items", [])
        sections = []

        def content(item: Any) -> str:
            return str(item.get("content", "")) if isinstance(item, dict) else str(item)

        if style:
            sections.append("User style:\n" + "\n".join(f"- {item}" for item in style[-12:]))
        if thinking:
            sections.append("User thinking patterns:\n" + "\n".join(f"- {item}" for item in thinking[-8:]))
        if rules:
            sections.append(
                "Explicit rules:\n"
                + "\n".join(f"- {content(item)}" for item in rules[-12:])
            )
        if memory:
            sections.append(
                "Relevant memory:\n"
                + "\n".join(f"- {content(item)}" for item in memory[-10:])
            )
        return "\n\n".join(sections)

    async def learn_revision(
        self, api_key: str, model: str, ai_output: str, user_revision: str, provider: str = "openrouter"
    ) -> dict[str, list[str]]:
        prompt = (
            "Compare the AI output with the user's revision. Output only valid JSON in the format "
            '{"style_rules":["..."],"thinking_patterns":["..."]}. '
            "Maximum 3 items per list, concrete, concise, and do not discuss the content/topic itself. "
            "Write the style_rules and thinking_patterns in the same language as the user's revision."
        )
        result = await self.complete(
            api_key, model,
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"AI OUTPUT:\n{ai_output}\n\nUSER REVISION:\n{user_revision}"},
            ],
            max_tokens=400, temperature=0.2, provider=provider,
        )
        start, end = result.find("{"), result.rfind("}")
        try:
            parsed = json.loads(result[start: end + 1])
        except (ValueError, json.JSONDecodeError):
            parsed = {"style_rules": [result.strip()], "thinking_patterns": []}
        return {
            "style_rules": [str(item).strip() for item in parsed.get("style_rules", []) if str(item).strip()][:3],
            "thinking_patterns": [
                str(item).strip() for item in parsed.get("thinking_patterns", []) if str(item).strip()
            ][:3],
        }

    async def analyze_chat(
        self, api_key: str, model: str, messages: list[dict[str, str]], previous_summary: str = "", provider: str = "openrouter"
    ) -> dict[str, Any]:
        transcript = "\n".join(
            f"{item['role'].upper()}: {item['content']}" for item in messages[-12:]
        )
        prompt = (
            "Analyze the conversation for continuity and personalization. Respond with valid JSON only: "
            '{"summary":"summary of concepts and decisions","concepts":["important concept"],'
            '"proposals":[{"type":"style|thinking|memory|rule","content":"proposal"}]}. '
            "Summary and concepts must be factual. Proposals are for user preferences or explicit facts only, "
            "max 4, no duplicates, and do not treat regular questions as permanent preferences. "
            "Write all summaries, concepts, and proposals in the same language as the conversation."
        )
        result = await self.complete(
            api_key, model,
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"PREVIOUS SUMMARY:\n{previous_summary}\n\nCONVERSATION:\n{transcript}"},
            ],
            max_tokens=700, temperature=0.2, provider=provider,
        )
        start, end = result.find("{"), result.rfind("}")
        try:
            parsed = json.loads(result[start: end + 1])
        except (ValueError, json.JSONDecodeError):
            parsed = {"summary": result.strip(), "concepts": [], "proposals": []}
        allowed = {"style", "thinking", "memory", "rule"}
        proposals = [
            {"type": str(item.get("type", "")), "content": str(item.get("content", "")).strip()}
            for item in parsed.get("proposals", [])
            if isinstance(item, dict)
            and str(item.get("type", "")) in allowed
            and str(item.get("content", "")).strip()
        ][:4]
        return {
            "summary": str(parsed.get("summary", "")).strip(),
            "concepts": [str(item).strip() for item in parsed.get("concepts", []) if str(item).strip()][:8],
            "proposals": proposals,
        }

    async def test_connection(self, api_key: str, model: str, provider: str) -> tuple[bool, str]:
        # Fallback to default 9Router if credentials are not provided
        if not api_key:
            if provider == "default" or not provider:
                api_key = settings.supabase_key or "dummy"
            else:
                return False, f"API key for {provider} is not configured"

        if provider == "default" or not provider:
            url = f"{settings.ai_base_url}/models"
            headers = {"Authorization": f"Bearer {api_key}"}
        elif provider == "google":
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
            headers = {}
        elif provider == "openrouter":
            url = "https://openrouter.ai/api/v1/models"
            headers = {"Authorization": f"Bearer {api_key}"}
        elif provider == "groq":
            url = "https://api.groq.com/openai/v1/models"
            headers = {"Authorization": f"Bearer {api_key}"}
        elif provider == "deepseek":
            url = "https://api.deepseek.com/v1/models"
            headers = {"Authorization": f"Bearer {api_key}"}
        elif provider == "mistral":
            url = "https://api.mistral.ai/v1/models"
            headers = {"Authorization": f"Bearer {api_key}"}
        elif provider == "kilo":
            url = "https://api.kilo.ai/v1/models"
            headers = {"Authorization": f"Bearer {api_key}"}
        elif provider.startswith("custom|"):
            parts = provider.split("|", 1)
            custom_url = parts[1].strip()
            if custom_url.endswith("/"):
                url = f"{custom_url}models"
            else:
                url = f"{custom_url}/models"
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
        else:
            return False, f"Unknown provider: {provider}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    return True, "Connected successfully"
                else:
                    return False, f"HTTP {res.status_code}"
        except Exception as e:
            return False, f"Connection error: {e}"


ai_service = AIService()
