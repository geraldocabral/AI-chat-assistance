"""Rotas do chat com sessões isoladas e agente simulado."""

import unittest
from unittest.mock import Mock

from emporio_agent.interfaces.chat.web import create_app


class WebChatTests(unittest.TestCase):
    def setUp(self):
        self.agents = []

        def factory(customer_id):
            agent = Mock()
            agent.reply.return_value = "Posso ajudar com instrumentos."
            self.agents.append((customer_id, agent))
            return agent

        self.app = create_app(factory, (1, 3, 7))
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_page_and_static_assets_are_served(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Empório da Música", response.get_data(as_text=True))
        for path in ("/static/chat.css", "/static/chat.js"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                response.close()

    def test_anonymous_session_is_created_and_restored(self):
        state = self.client.get("/api/session").get_json()
        self.assertEqual(state, {"messages": [], "customer_id": None, "customer_ids": [1, 3, 7]})
        self.client.get("/api/session")
        self.assertEqual(len(self.agents), 1)

    def test_message_and_history_are_preserved_on_reload(self):
        response = self.client.post("/api/messages", json={"message": "  Olá  "})
        self.assertEqual(response.status_code, 200)
        messages = response.get_json()["messages"]
        self.assertEqual(messages, [
            {"role": "user", "content": "Olá"},
            {"role": "assistant", "content": "Posso ajudar com instrumentos."},
        ])
        self.agents[0][1].reply.assert_called_once_with("Olá")
        self.assertEqual(self.client.get("/api/session").get_json()["messages"], messages)

    def test_browser_sessions_do_not_share_history(self):
        self.client.post("/api/messages", json={"message": "Minha conversa"})
        other = self.app.test_client()
        self.assertEqual(other.get("/api/session").get_json()["messages"], [])
        self.assertEqual(len(self.agents), 2)

    def test_reset_clears_history_and_selects_demo_customer(self):
        self.client.post("/api/messages", json={"message": "Olá"})
        state = self.client.post("/api/session", json={"customer_id": 3}).get_json()
        self.assertEqual(state["customer_id"], 3)
        self.assertEqual(state["messages"], [])
        self.assertEqual(self.agents[-1][0], 3)
        anonymous = self.client.post("/api/session", json={"customer_id": None}).get_json()
        self.assertIsNone(anonymous["customer_id"])

    def test_invalid_messages_and_identity_injection_are_rejected(self):
        cases = ({}, {"message": ""}, {"message": 123}, {"message": "x" * 4001}, {"message": "Pedido", "customer_id": 7})
        for body in cases:
            with self.subTest(body_type=list(body)):
                self.assertEqual(self.client.post("/api/messages", json=body).status_code, 400)
        self.assertEqual(self.agents, [])
        self.assertEqual(self.client.post("/api/messages", data="not-json").status_code, 400)

    def test_invalid_demo_customer_does_not_change_session(self):
        self.client.post("/api/session", json={"customer_id": 3})
        for value in (9999, "3", True):
            with self.subTest(value=value):
                self.assertEqual(self.client.post("/api/session", json={"customer_id": value}).status_code, 400)
        self.assertEqual(self.client.get("/api/session").get_json()["customer_id"], 3)

    def test_cross_origin_post_is_rejected(self):
        response = self.client.post("/api/messages", json={"message": "Olá"}, headers={"Origin": "https://other.example"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.agents, [])

    def test_unexpected_error_is_sanitized(self):
        self.client.get("/api/session")
        self.agents[0][1].reply.side_effect = RuntimeError("private-key-and-path")
        with self.assertLogs(self.app.logger.name, level="ERROR") as logs:
            response = self.client.post("/api/messages", json={"message": "Olá"})
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("private-key-and-path", response.get_data(as_text=True))
        self.assertNotIn("private-key-and-path", " ".join(logs.output))

    def test_history_keeps_complete_turns_with_bounded_size(self):
        for index in range(8):
            self.client.post("/api/messages", json={"message": f"Pergunta {index}"})
        messages = self.client.get("/api/session").get_json()["messages"]
        self.assertEqual(len(messages), 12)
        self.assertEqual(messages[0]["content"], "Pergunta 2")


if __name__ == "__main__":
    unittest.main()
