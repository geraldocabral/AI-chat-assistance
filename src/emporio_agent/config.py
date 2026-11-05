"""Configuração de integração carregada das variáveis de ambiente do processo."""

import math
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelSettings:
    api_key: str = field(repr=False)
    model: str = "gemini-3.5-flash-lite"
    timeout_seconds: float = 30
    max_output_tokens: int = 2048

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("GEMINI_API_KEY: configure a chave de API no ambiente local")
        if not self.model.strip():
            raise ValueError("GEMINI_MODEL: informe um modelo")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("LLM_TIMEOUT_SECONDS: informe um número positivo e finito")
        if type(self.max_output_tokens) is not int or self.max_output_tokens < 1:
            raise ValueError("LLM_MAX_OUTPUT_TOKENS: informe um inteiro positivo")

    @classmethod
    def from_environment(cls) -> "ModelSettings":
        try:
            timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "30"))
            tokens = int(os.environ.get("LLM_MAX_OUTPUT_TOKENS", "2048"))
        except ValueError:
            raise ValueError("Configuração inválida de timeout ou limite de tokens") from None
        return cls(
            api_key=os.environ.get("GEMINI_API_KEY", "").strip(),
            model=os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite").strip(),
            timeout_seconds=timeout,
            max_output_tokens=tokens,
        )
