"""Composição da aplicação: conecta adaptadores aos casos de uso e ao agente."""

from pathlib import Path

from emporio_agent.application.agent.conversation import ConversationAgent
from emporio_agent.application.agent.tools import AgentTools
from emporio_agent.application.ports.language_model import LanguageModel
from emporio_agent.application.use_cases.get_order import GetOrder
from emporio_agent.application.use_cases.get_payment_options import GetPaymentOptions
from emporio_agent.application.use_cases.get_product_details import GetProductDetails
from emporio_agent.application.use_cases.search_policies import SearchPolicies
from emporio_agent.application.use_cases.search_products import SearchProducts
from emporio_agent.infrastructure.persistence.sqlite_catalog import SQLiteCatalog
from emporio_agent.infrastructure.persistence.sqlite_orders import SQLiteOrderReader
from emporio_agent.infrastructure.retrieval.pdf_policies import load_policy_sections
from emporio_agent.infrastructure.retrieval.text_policy_search import TextPolicySearch


def build_agent(
    model: LanguageModel, database: Path, manual: Path, *, customer_id: int | None = None,
) -> ConversationAgent:
    catalog = SQLiteCatalog(database)
    policies = TextPolicySearch(load_policy_sections(manual))
    tools = AgentTools(
        search_products=SearchProducts(catalog),
        get_product_details=GetProductDetails(catalog),
        get_payment_options=GetPaymentOptions(catalog),
        search_policies=SearchPolicies(policies),
        get_order=GetOrder(SQLiteOrderReader(database), customer_id),
    )
    return ConversationAgent(model, tools)
