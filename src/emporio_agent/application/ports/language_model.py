"""Mensagens e contrato do modelo, independentes do SDK do provedor."""

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]
    provider_metadata: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ModelReply:
    message: ChatMessage
    input_tokens: int | None = None
    output_tokens: int | None = None


class ModelError(RuntimeError):
    """Falha de integração com mensagem segura para a aplicação."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class LanguageModel(Protocol):
    def complete(
        self, messages: list[ChatMessage], tools: tuple[ToolDefinition, ...] = (),
    ) -> ModelReply:
        """Produz texto ou solicita ferramentas, sem executá-las."""
        ...
