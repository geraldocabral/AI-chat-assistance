"""Ferramentas permitidas e validação dos argumentos enviados pelo modelo."""

import json
from dataclasses import fields, is_dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from emporio_agent.application.ports.catalog import ProductSearch
from emporio_agent.application.ports.language_model import ToolCall, ToolDefinition
from emporio_agent.application.use_cases.get_order import GetOrder
from emporio_agent.application.use_cases.get_payment_options import GetPaymentOptions
from emporio_agent.application.use_cases.get_product_details import GetProductDetails
from emporio_agent.application.use_cases.search_policies import SearchPolicies
from emporio_agent.application.use_cases.search_products import SearchProducts
from emporio_agent.domain.product import Product


def _json_value(value):
    if is_dataclass(value):
        result = {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
        if isinstance(value, Product):
            result["is_available"] = value.is_available
        return result
    if isinstance(value, (Decimal, date)):
        return str(value)
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def _definition(name, description, properties, required=()):
    return ToolDefinition(name, description, {
        "type": "object", "properties": properties,
        "required": list(required), "additionalProperties": False,
    })


def _validate_arguments(definition: ToolDefinition, arguments: dict) -> None:
    if not isinstance(arguments, dict):
        raise ValueError("Argumentos devem ser um objeto")
    schema = definition.parameters
    if set(arguments) - set(schema["properties"]):
        raise ValueError("Parâmetro não permitido")
    if set(schema["required"]) - set(arguments):
        raise ValueError("Parâmetro obrigatório ausente")
    types = {"string": str, "integer": int, "boolean": bool}
    for name, value in arguments.items():
        if type(value) is not types[schema["properties"][name]["type"]]:
            raise ValueError(f"Tipo inválido para {name}")


class AgentTools:
    def __init__(
        self, search_products: SearchProducts, get_product_details: GetProductDetails,
        get_payment_options: GetPaymentOptions, search_policies: SearchPolicies, get_order: GetOrder,
    ) -> None:
        self._search_products = search_products
        product_id = {"product_id": {"type": "integer", "description": "Identificador obtido no catálogo"}}
        definitions = (
            _definition("search_products", "Busca por trecho do nome e categoria exata; preço de tabela, sem desconto. Retorna até limit resultados, disponíveis por padrão.", {
                "name": {"type": "string"}, "category": {"type": "string"},
                "max_price_brl": {"type": "string", "description": "Valor decimal em reais, ex.: 1000.00"},
                "available_only": {"type": "boolean"}, "limit": {"type": "integer"},
            }),
            _definition("get_product_details", "Consulta especificações, estoque, status e promoções ativas, incluindo produtos indisponíveis.", product_id, ("product_id",)),
            _definition("get_payment_options", "Calcula preço promocional, PIX e parcelas de uma unidade disponível; não inclui frete.", product_id, ("product_id",)),
            _definition("search_policies", "Consulta regras e informações da loja, com seção e páginas. Retorna referências completas, não uma decisão sobre um caso individual.", {
                "query": {"type": "string"}, "limit": {"type": "integer"},
            }, ("query",)),
            _definition("get_order", "Consulta pedido do cliente da sessão. Nunca aceita identidade do cliente; ausência não distingue outro proprietário de pedido inexistente.", {
                "order_id": {"type": "integer"},
            }, ("order_id",)),
        )
        handlers = (
            self._search, get_product_details.execute, get_payment_options.execute,
            search_policies.execute, get_order.execute,
        )
        self._tools = {definition.name: (definition, handler) for definition, handler in zip(definitions, handlers)}

    @property
    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(definition for definition, _ in self._tools.values())

    def _search(self, **arguments):
        price = arguments.get("max_price_brl")
        if price is not None:
            try:
                arguments["max_price_brl"] = Decimal(price)
            except InvalidOperation:
                raise ValueError("max_price_brl: informe um valor decimal") from None
        arguments.setdefault("limit", 5)
        filters = ProductSearch(**arguments)
        results = self._search_products.execute(filters)
        return {"products": results, "returned_count": len(results), "may_have_more": len(results) == filters.limit}

    def execute(self, call: ToolCall) -> str:
        tool = self._tools.get(call.name)
        if tool is None:
            result = {"ok": False, "error": "Ferramenta não permitida"}
        else:
            definition, handler = tool
            try:
                _validate_arguments(definition, call.arguments)
                arguments = dict(call.arguments)
                if call.name == "search_policies":
                    arguments.setdefault("limit", 2)
                result = {"ok": True, "data": handler(**arguments)}
            except PermissionError:
                result = {"ok": False, "error": "Consulta exige uma sessão com cliente identificado"}
            except (ValueError, InvalidOperation) as error:
                result = {"ok": False, "error": str(error)}
        return json.dumps(_json_value(result), ensure_ascii=False, allow_nan=False)
