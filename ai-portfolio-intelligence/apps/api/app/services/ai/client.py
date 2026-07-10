from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from app.core.config import settings

_runtime_api_key: str | None = None
_runtime_model: str | None = None


class GeminiAPIError(RuntimeError):
    pass


def configure_runtime_gemini(api_key: str, model: str | None = None) -> None:
    if settings.environment != "development":
        raise RuntimeError("Runtime Gemini configuration is only allowed in development")
    global _runtime_api_key, _runtime_model
    _runtime_api_key = api_key.strip()
    _runtime_model = model.strip() if model else None


def resolve_gemini_credentials(
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> tuple[str | None, str]:
    if settings.environment == "development":
        resolved_key = api_key if api_key is not None else _runtime_api_key or os.getenv("GEMINI_API_KEY") or settings.gemini_api_key
        resolved_model = model or _runtime_model or os.getenv("GEMINI_MODEL") or settings.gemini_model
        return resolved_key, resolved_model
    resolved_key = api_key or os.getenv("GEMINI_API_KEY") or settings.gemini_api_key
    resolved_model = model or os.getenv("GEMINI_MODEL") or settings.gemini_model
    return resolved_key, resolved_model


class GeminiClient:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key, self.model = resolve_gemini_credentials(api_key=api_key, model=model)
        self.last_grounding_used = False

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def generate_json(self, prompt: str, response_schema: dict[str, Any] | None = None, tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "topP": 0.8,
                "responseMimeType": "application/json",
            },
        }
        if response_schema:
            payload["generationConfig"]["responseSchema"] = response_schema
        if tools:
            payload["tools"] = tools

        self.last_grounding_used = False
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        with httpx.Client(timeout=settings.ai_timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise GeminiAPIError(_gemini_error_message(exc.response)) from exc
            data = response.json()

        # Check if grounding was used
        try:
            candidate = data.get("candidates", [{}])[0]
            grounding_metadata = candidate.get("groundingMetadata", {})
            if grounding_metadata and (grounding_metadata.get("webSearchQueries") or grounding_metadata.get("searchEntryPoint")):
                self.last_grounding_used = True
            else:
                self.last_grounding_used = False
        except (KeyError, IndexError, TypeError):
            self.last_grounding_used = False

        text = _extract_text(data)
        return _parse_json_text(text)

    def generate_text(self, prompt: str, system_instruction: str | None = None, tools: list[dict[str, Any]] | None = None) -> str:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.4,
                "topP": 0.8,
            },
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        if tools:
            payload["tools"] = tools
            
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        with httpx.Client(timeout=settings.ai_timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
            self.last_grounding_used = False

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise GeminiAPIError(_gemini_error_message(exc.response)) from exc
            data = response.json()

        # Check if grounding was used
        try:
            candidate = data.get("candidates", [{}])[0]
            grounding_metadata = candidate.get("groundingMetadata", {})
            if grounding_metadata and (grounding_metadata.get("webSearchQueries") or grounding_metadata.get("searchEntryPoint")):
                self.last_grounding_used = True
            else:
                self.last_grounding_used = False
        except (KeyError, IndexError, TypeError):
            self.last_grounding_used = False

        return _extract_text(data)



def _gemini_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            status = error.get("status")
            if message and status:
                return f"Gemini API {response.status_code} {status}: {message}"
            if message:
                return f"Gemini API {response.status_code}: {message}"

    text = response.text.strip()
    if text:
        return f"Gemini API {response.status_code}: {text[:500]}"
    return f"Gemini API {response.status_code}: request rejected without an error body"


def _extract_text(data: dict[str, Any]) -> str:
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "\n".join(part.get("text", "") for part in parts if "text" in part).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Gemini response did not contain text content") from exc


def _parse_json_text(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL)
        if match:
            cleaned = match.group(1)
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("Gemini JSON response must be an object")
    return parsed
