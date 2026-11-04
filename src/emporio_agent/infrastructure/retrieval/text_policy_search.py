"""Busca lexical local por seções, sem chamadas de API ou embeddings."""

import math
import re
import unicodedata
from collections import Counter

from emporio_agent.application.ports.policies import PolicySection


STOPWORDS = set(
    "a ao aos as ate com como da das de do dos e em essa esse eu ha isso me meu minha "
    "na nas no nos o os ou para pelo pela por posso qual quais que se sem ser sua seu "
    "tem um uma voces loja produto produtos".split()
)
ALIASES = {
    "devolver": "devolucao", "devolucoes": "devolucao",
    "arrependi": "arrependimento", "trocar": "troca", "trocas": "troca",
    "horarios": "horario", "horas": "horario", "abre": "horario", "abrem": "horario",
    "fecha": "horario", "fecham": "horario", "aberta": "horario",
    "parcelar": "parcelamento", "parcelas": "parcelamento",
    "promocoes": "promocao", "descontos": "desconto",
    "rastrear": "rastreamento", "garantias": "garantia",
}


def _tokens(text: str) -> set[str]:
    normalized = "".join(
        char for char in unicodedata.normalize("NFD", text.casefold())
        if not unicodedata.combining(char)
    )
    return {
        ALIASES.get(word, word)
        for word in re.findall(r"[a-z0-9]+", normalized)
        if len(word) > 1 and word not in STOPWORDS
    }


class TextPolicySearch:
    def __init__(self, sections: tuple[PolicySection, ...]) -> None:
        self._sections = sections
        self._terms = [_tokens(section.text) for section in sections]
        self._titles = [_tokens(section.title) for section in sections]
        self._frequencies = Counter(term for terms in self._terms for term in terms)

    def search(self, query: str, limit: int) -> list[PolicySection]:
        query_terms = _tokens(query)
        scored = []
        for section, terms, title in zip(self._sections, self._terms, self._titles):
            score = sum(
                (1 + math.log((len(self._sections) + 1) / (self._frequencies[term] + 1)))
                * (2 if term in title else 1)
                for term in sorted(query_terms & terms)
            )
            if score > 0:
                scored.append((score, section))
        scored.sort(key=lambda item: (-item[0], item[1].number))
        return [section for _, section in scored[:limit]]
