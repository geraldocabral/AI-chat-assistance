"""Consulta às políticas independente do PDF e do algoritmo de busca."""

from emporio_agent.application.ports.policies import PolicySearch, PolicySection


class SearchPolicies:
    def __init__(self, policies: PolicySearch) -> None:
        self._policies = policies

    def execute(self, query: str, limit: int = 3) -> list[PolicySection]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query: informe um texto não vazio")
        if type(limit) is not int or not 1 <= limit <= 5:
            raise ValueError("limit: informe um inteiro entre 1 e 5")
        return self._policies.search(query.strip(), limit)
