"""Conversas simuladas com ferramentas reais, sem consumir a API."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from emporio_agent.application.agent.conversation import ConversationAgent, FAILURE_REPLY, LIMIT_REPLY
from emporio_agent.application.agent.tools import AgentTools
from emporio_agent.application.ports.language_model import ChatMessage, ModelError, ModelReply, ToolCall
from emporio_agent.bootstrap import build_agent
from emporio_agent.infrastructure.persistence.sqlite_import import import_csv_to_sqlite


def tool_reply(name, arguments, call_id="call_1"):
    return ModelReply(ChatMessage("assistant", tool_calls=(ToolCall(call_id, name, arguments),)))


def text_reply(text="Resposta final"):
    return ModelReply(ChatMessage("assistant", text))


class ScriptedModel:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.requests = []

    def complete(self, messages, tools=()):
        self.requests.append((messages, tools))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


class AgentToolsIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.database = Path(cls.temp.name) / "store.sqlite3"
        source = Path(__file__).resolve().parents[1] / "data"
        cls.manual = source / "políticas_da_loja.pdf"
        import_csv_to_sqlite(source, cls.database)

    def run_tool(self, name, arguments, customer_id=None):
        model = ScriptedModel(tool_reply(name, arguments), text_reply())
        agent = build_agent(model, self.database, self.manual, customer_id=customer_id)
        self.assertEqual(agent.reply("Pergunta de teste"), "Resposta final")
        message = model.requests[1][0][-1]
        self.assertEqual(message.role, "tool")
        self.assertEqual(message.tool_call_id, "call_1")
        return json.loads(message.content)

    def test_catalog_search_serializes_money_availability_and_limit(self):
        result = self.run_tool("search_products", {"category": "Violões", "max_price_brl": "1000.00"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["returned_count"], 5)
        self.assertTrue(result["data"]["may_have_more"])
        self.assertTrue(result["data"]["products"][0]["is_available"])
        self.assertIsInstance(result["data"]["products"][0]["price_brl"], str)

    def test_product_details_and_payment_tools(self):
        details = self.run_tool("get_product_details", {"product_id": 81})
        self.assertEqual(details["data"]["specs"]["strings"], "nylon")
        self.assertEqual(details["data"]["created_at"], "2021-03-15")
        payment = self.run_tool("get_payment_options", {"product_id": 94})
        self.assertEqual(payment["data"]["quote"]["pix_price_brl"], "5519.08")

    def test_policies_return_source_and_pages(self):
        result = self.run_tool("search_policies", {"query": "Me arrependi, posso devolver?"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"][0]["number"], 4)
        self.assertEqual(result["data"][0]["pages"], [4])
        self.assertEqual(result["data"][0]["source"], self.manual.name)

    def test_order_tool_uses_only_session_identity(self):
        result = self.run_tool("get_order", {"order_id": 1}, customer_id=3)
        self.assertEqual(result["data"]["order_id"], 1)
        self.assertEqual(result["data"]["order_date"], "2025-10-15")
        self.assertIsNone(self.run_tool("get_order", {"order_id": 1}, customer_id=7)["data"])
        self.assertFalse(self.run_tool("get_order", {"order_id": 1})["ok"])
        self.assertFalse(self.run_tool("get_order", {"order_id": 1, "customer_id": 3}, customer_id=7)["ok"])

    def test_invalid_tools_and_arguments_produce_recoverable_errors(self):
        for name, arguments in (
            ("run_sql", {"query": "DROP TABLE products"}),
            ("get_product_details", {}),
            ("get_product_details", {"product_id": True}),
            ("get_product_details", {"product_id": -1}),
            ("search_products", {"max_price_brl": 1000}),
            ("search_products", {"max_price_brl": "abc"}),
            ("search_products", {"max_price_brl": "NaN"}),
            ("search_policies", {"query": "horario", "limit": 10}),
        ):
            with self.subTest(name=name, arguments=arguments):
                self.assertFalse(self.run_tool(name, arguments)["ok"])


class ConversationFlowTests(unittest.TestCase):
    def setUp(self):
        self.tools = Mock(spec=AgentTools)
        self.tools.definitions = ()
        self.tools.execute.return_value = '{"ok":true,"data":null}'

    def test_multi_step_tools_and_followup_keep_complete_history(self):
        model = ScriptedModel(
            tool_reply("search_products", {}),
            tool_reply("get_product_details", {"product_id": 81}, "call_2"),
            text_reply("Yamaha C40"), text_reply("Seguimento"),
        )
        agent = ConversationAgent(model, self.tools)
        self.assertEqual(agent.reply("Quero um violão"), "Yamaha C40")
        self.assertEqual(agent.reply("E as especificações?"), "Seguimento")
        roles = [message.role for message in model.requests[3][0]]
        self.assertEqual(roles, ["system", "user", "assistant", "tool", "assistant", "tool", "assistant", "user"])
        self.assertEqual(self.tools.execute.call_count, 2)

    def test_model_failure_keeps_only_clean_fallback_in_history(self):
        model = ScriptedModel(tool_reply("search_products", {}), ModelError("secret-provider-body"), text_reply())
        agent = ConversationAgent(model, self.tools)
        with self.assertLogs("emporio_agent.application.agent.conversation", level="WARNING") as logs:
            self.assertEqual(agent.reply("Quero um violão"), FAILURE_REPLY)
        self.assertNotIn("secret-provider-body", " ".join(logs.output))
        agent.reply("Tentar novamente")
        self.assertEqual([message.role for message in model.requests[2][0]], ["system", "user", "assistant", "user"])

    def test_model_call_limit_stops_before_useless_tool_execution(self):
        model = ScriptedModel(tool_reply("search_products", {}))
        agent = ConversationAgent(model, self.tools, max_model_calls=1)
        self.assertEqual(agent.reply("Buscar"), LIMIT_REPLY)
        self.tools.execute.assert_not_called()

    def test_tool_limit_rejects_whole_batch_before_execution(self):
        calls = (ToolCall("1", "search_products", {}), ToolCall("2", "search_products", {}))
        model = ScriptedModel(ModelReply(ChatMessage("assistant", tool_calls=calls)))
        agent = ConversationAgent(model, self.tools, max_tool_calls=1)
        self.assertEqual(agent.reply("Buscar"), LIMIT_REPLY)
        self.tools.execute.assert_not_called()

    def test_storage_error_is_not_exposed_to_model(self):
        self.tools.execute.side_effect = RuntimeError("private-path-and-data")
        model = ScriptedModel(tool_reply("get_order", {"order_id": 1}), text_reply())
        agent = ConversationAgent(model, self.tools)
        with self.assertLogs("emporio_agent.application.agent.conversation", level="WARNING") as logs:
            agent.reply("Meu pedido")
        self.assertNotIn("private-path-and-data", model.requests[1][0][-1].content)
        self.assertNotIn("private-path-and-data", " ".join(logs.output))

    def test_history_limit_preserves_whole_turns(self):
        model = ScriptedModel(text_reply("1"), text_reply("2"), text_reply("3"))
        agent = ConversationAgent(model, self.tools, history_turns=1)
        agent.reply("primeira")
        agent.reply("segunda")
        agent.reply("terceira")
        self.assertEqual([message.content for message in model.requests[2][0][1:]], ["segunda", "2", "terceira"])

    def test_invalid_input_is_rejected_without_calling_model(self):
        model = ScriptedModel()
        agent = ConversationAgent(model, self.tools)
        for text in (None, " ", "x" * 4001):
            with self.subTest(text_type=type(text)), self.assertRaises(ValueError):
                agent.reply(text)
        self.assertEqual(model.requests, [])


if __name__ == "__main__":
    unittest.main()
