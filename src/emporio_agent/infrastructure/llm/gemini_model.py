"""Adaptador HTTP do Gemini usando apenas a biblioteca padrão do Python."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from emporio_agent.application.ports.language_model import (
    ChatMessage, ModelError, ModelReply, ToolCall, ToolDefinition,
)
from emporio_agent.config import ModelSettings


ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"


def _encode_message(message: ChatMessage) -> dict:
    result = {"role": message.role, "content": message.content}
    if message.tool_calls:
        result["tool_calls"] = [
            {"id": call.call_id, "type": "function", "function": {
                "name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False),
            }, **({"extra_content": call.provider_metadata} if call.provider_metadata else {})}
            for call in message.tool_calls
        ]
    if message.tool_call_id is not None:
        result["tool_call_id"] = message.tool_call_id
    return result


def _decode_reply(payload: dict) -> ModelReply:
    try:
        choice = payload["choices"][0]
        if choice["finish_reason"] not in {"stop", "tool_calls"}:
            raise ValueError("Resposta incompleta ou interrompida")
        message = choice["message"]
        if message["role"] != "assistant":
            raise ValueError("Papel inesperado")
        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise ValueError("Conteúdo inválido")
        calls = []
        for item in message.get("tool_calls") or []:
            function = item["function"]
            arguments = json.loads(function["arguments"])
            if item["type"] != "function" or not isinstance(arguments, dict):
                raise ValueError("Chamada de ferramenta inválida")
            if not isinstance(item["id"], str) or not item["id"]:
                raise ValueError("Identificador de chamada inválido")
            if not isinstance(function["name"], str) or not function["name"]:
                raise ValueError("Nome de ferramenta inválido")
            metadata = item.get("extra_content") or {}
            if not isinstance(metadata, dict):
                raise ValueError("Metadados de ferramenta inválidos")
            calls.append(ToolCall(item["id"], function["name"], arguments, metadata))
        if not calls and (content is None or not content.strip()):
            raise ValueError("Resposta vazia")
        if len({call.call_id for call in calls}) != len(calls):
            raise ValueError("Identificadores de chamada duplicados")
        usage = payload.get("usage") or {}
        return ModelReply(
            message=ChatMessage("assistant", content, tuple(calls)),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )
    except (AttributeError, KeyError, IndexError, TypeError, ValueError):
        raise ModelError("O provedor retornou uma resposta inválida ou incompleta") from None


class GeminiModel:
    def __init__(self, settings: ModelSettings) -> None:
        self._settings = settings

    def complete(
        self, messages: list[ChatMessage], tools: tuple[ToolDefinition, ...] = (),
    ) -> ModelReply:
        payload = {
            "model": self._settings.model,
            "messages": [_encode_message(message) for message in messages],
            "temperature": 0,
            "max_completion_tokens": self._settings.max_output_tokens,
        }
        if tools:
            payload["tools"] = [
                {"type": "function", "function": {
                    "name": tool.name, "description": tool.description, "parameters": tool.parameters,
                }}
                for tool in tools
            ]
            payload["tool_choice"] = "auto"
        request = Request(
            ENDPOINT, data=json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._settings.api_key}",
                "Content-Type": "application/json", "User-Agent": "emporio-agent/0.1",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._settings.timeout_seconds) as response:
                result = json.load(response)
        except HTTPError as error:
            status = error.code
            error.close()
            if status in {401, 403}:
                raise ModelError("Acesso ao modelo negado; verifique a chave e as permissões") from None
            if status == 429:
                raise ModelError("Limite da API atingido; tente novamente mais tarde", retryable=True) from None
            raise ModelError(f"Falha HTTP do provedor ({status})", retryable=status >= 500) from None
        except (URLError, TimeoutError, OSError):
            raise ModelError("Não foi possível conectar ao provedor", retryable=True) from None
        except (ValueError, UnicodeError):
            raise ModelError("O provedor retornou conteúdo inválido") from None
        return _decode_reply(result)
