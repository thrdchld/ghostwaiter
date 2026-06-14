from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from huggingface_hub import AsyncInferenceClient

from .config import settings
from .storage import store


class AIUnavailable(RuntimeError):
    pass


class AIService:
    def __init__(self) -> None:
        self.active_model = settings.default_model
        self.last_error = ""

    @property
    def models(self) -> tuple[str, ...]:
        models_file = store.read_json(store.root / "system" / "models.json")
        return tuple(
            dict.fromkeys(
                [models_file.get("default_model", settings.default_model)]
                + models_file.get("fallback_models", list(settings.fallback_models))
            )
        )

    def client(self) -> AsyncInferenceClient:
        if not settings.hf_token:
            raise AIUnavailable("HF_TOKEN belum dikonfigurasi di Settings Hugging Face Space")
        return AsyncInferenceClient(
            api_key=settings.hf_token,
            provider=settings.inference_provider,
            timeout=120,
        )

    async def stream(self, messages: list[dict[str, str]], max_tokens: int = 900) -> AsyncIterator[str]:
        errors: list[str] = []
        for model in self.models:
            try:
                client = self.client()
                stream = await client.chat_completion(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=0.7,
                    stream=True,
                )
                self.active_model = model
                async for chunk in stream:
                    text = chunk.choices[0].delta.content or ""
                    if text:
                        yield text
                self.last_error = ""
                return
            except Exception as exc:
                errors.append(f"{model}: {exc}")
        self.last_error = " | ".join(errors)
        raise AIUnavailable("Semua model inference gagal. Periksa token, provider, dan kuota.")

    async def complete(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> str:
        errors: list[str] = []
        for model in self.models:
            try:
                response = await self.client().chat_completion(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                self.active_model = model
                self.last_error = ""
                return response.choices[0].message.content or ""
            except Exception as exc:
                errors.append(f"{model}: {exc}")
        self.last_error = " | ".join(errors)
        raise AIUnavailable("Semua model inference gagal. Periksa token, provider, dan kuota.")

    def context(self, workspace_id: str) -> str:
        brain = store.workspace_path(workspace_id) / "brain"
        style = store.read_json(brain / "style_profile.json").get("rules", [])
        thinking = store.read_json(brain / "thinking_profile.json").get("patterns", [])
        rules = store.read_json(brain / "rules.json").get("items", [])
        memory = store.read_json(brain / "memory.json").get("items", [])
        sections = []
        if style:
            sections.append("Gaya pengguna:\n" + "\n".join(f"- {item}" for item in style[-12:]))
        if thinking:
            sections.append("Pola berpikir pengguna:\n" + "\n".join(f"- {item}" for item in thinking[-8:]))
        if rules:
            sections.append(
                "Aturan eksplisit:\n"
                + "\n".join(f"- {item.get('content', item)}" for item in rules[-12:])
            )
        if memory:
            sections.append(
                "Memori relevan:\n"
                + "\n".join(f"- {item.get('content', item)}" for item in memory[-10:])
            )
        return "\n\n".join(sections)

    async def learn_revision(self, ai_output: str, user_revision: str) -> dict[str, list[str]]:
        prompt = (
            "Bandingkan keluaran AI dan revisi pengguna. Keluarkan JSON valid saja dengan bentuk "
            '{"style_rules":["..."],"thinking_patterns":["..."]}. '
            "Maksimal 3 item per daftar, konkret, singkat, dan jangan membahas isi/topik."
        )
        result = await self.complete(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"KELUARAN AI:\n{ai_output}\n\nREVISI PENGGUNA:\n{user_revision}"},
            ],
            max_tokens=400,
            temperature=0.2,
        )
        start, end = result.find("{"), result.rfind("}")
        try:
            parsed = json.loads(result[start : end + 1])
        except (ValueError, json.JSONDecodeError):
            parsed = {"style_rules": [result.strip()], "thinking_patterns": []}
        return {
            "style_rules": [str(item).strip() for item in parsed.get("style_rules", []) if str(item).strip()][:3],
            "thinking_patterns": [
                str(item).strip() for item in parsed.get("thinking_patterns", []) if str(item).strip()
            ][:3],
        }


ai_service = AIService()
