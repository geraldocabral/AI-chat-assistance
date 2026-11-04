"""Contrato de recuperação de políticas com referências à origem."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PolicySection:
    number: int
    title: str
    text: str
    source: str
    pages: tuple[int, ...]


class PolicySearch(Protocol):
    def search(self, query: str, limit: int) -> list[PolicySection]:
        """Retorna seções por relevância, ou lista vazia sem correspondências."""
        ...
