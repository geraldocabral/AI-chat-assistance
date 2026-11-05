"""Testa o contrato HTTP sem usar chave real ou consumir a cota do provedor."""

import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from emporio_agent.application.ports.language_model import (
    ChatMessage, ModelError, ToolCall, ToolDefinition,
)
from emporio_agent.config import ModelSettings
from emporio_agent.infrastructure.llm.gemini_model import ENDPOINT, GeminiModel


TARGET = "emporio_agent.infrastructure.llm.gemini_model.urlopen"


def response_payload(content="Olá!", calls=None, finish="stop"):
    message = {"role": "assistant", "content": content}
    if calls is not None:
        message["tool_calls"] = calls
    return {
        "choices": [{"finish_reason": finish, "message": message}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10},
    }


def response_stream(payload):
    return io.BytesIO(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


class GeminiModelTests(unittest.TestCase):
    def setUp(self):
        self.settings = ModelSettings(api_key="fake-test-key")
        self.model = GeminiModel(self.settings)

    def test_text_response_usage_and_http_parameters(self):
        with patch(TARGET, return_value=response_stream(response_payload())) as request:
            reply = self.model.complete([ChatMessage("user", "Oi")])
        self.assertEqual(reply.message.content, "Olá!")
        self.assertEqual((reply.input_tokens, reply.output_tokens), (20, 10))
        sent = request.call_args.args[0]
        self.assertEqual(sent.full_url, ENDPOINT)
        self.assertEqual(sent.get_method(), "POST")
        self.assertEqual(sent.get_header("Authorization"), "Bearer fake-test-key")
        self.assertEqual(request.call_args.kwargs["timeout"], 30)
        payload = json.loads(sent.data)
        self.assertEqual(payload["messages"], [{"role": "user", "content": "Oi"}])
        self.assertEqual(payload["max_completion_tokens"], 2048)
        self.assertNotIn("tools", payload)

    def test_tool_request_is_decoded_without_executing_it(self):
        calls = [{"id": "call_1", "type": "function", "function": {
            "name": "search_products", "arguments": '{"category": "Violões"}',
        }}]
        definition = ToolDefinition("search_products", "Busca produtos", {"type": "object"})
        with patch(TARGET, return_value=response_stream(response_payload(None, calls, "tool_calls"))) as request:
            reply = self.model.complete([ChatMessage("user", "Quero um violão")], (definition,))
        self.assertEqual(reply.message.tool_calls, (ToolCall("call_1", "search_products", {"category": "Violões"}),))
        payload = json.loads(request.call_args.args[0].data)
        self.assertEqual(payload["tools"][0]["function"]["name"], "search_products")
        self.assertEqual(payload["tool_choice"], "auto")

    def test_tool_history_is_encoded_for_next_turn(self):
        messages = [
            ChatMessage("assistant", tool_calls=(ToolCall("call_1", "get_product_details", {"product_id": 81}),)),
            ChatMessage("tool", '{"name":"Yamaha"}', tool_call_id="call_1"),
        ]
        with patch(TARGET, return_value=response_stream(response_payload())) as request:
            self.model.complete(messages)
        encoded = json.loads(request.call_args.args[0].data)["messages"]
        self.assertEqual(json.loads(encoded[0]["tool_calls"][0]["function"]["arguments"]), {"product_id": 81})
        self.assertEqual(encoded[1]["tool_call_id"], "call_1")

    def test_provider_metadata_is_preserved_in_tool_history(self):
        metadata = {"google": {"thought_signature": "opaque-signature"}}
        calls = [{"id": "call_1", "type": "function", "function": {
            "name": "get_product_details", "arguments": '{"product_id": 81}',
        }, "extra_content": metadata}]
        with patch(TARGET, return_value=response_stream(response_payload(None, calls, "tool_calls"))):
            reply = self.model.complete([ChatMessage("user", "Quero detalhes")])
        self.assertEqual(reply.message.tool_calls[0].provider_metadata, metadata)
        with patch(TARGET, return_value=response_stream(response_payload())) as request:
            self.model.complete([
                reply.message, ChatMessage("tool", '{"name":"Yamaha"}', tool_call_id="call_1"),
            ])
        history = json.loads(request.call_args.args[0].data)["messages"]
        self.assertEqual(history[0]["tool_calls"][0]["extra_content"], metadata)

    def test_http_errors_have_safe_messages_and_are_not_retried(self):
        for status, retryable in ((400, False), (401, False), (403, False), (429, True), (500, True)):
            with self.subTest(status=status):
                error = HTTPError(ENDPOINT, status, "sensitive body", {}, io.BytesIO(b"fake-test-key"))
                with patch(TARGET, side_effect=error) as request, self.assertRaises(ModelError) as caught:
                    self.model.complete([ChatMessage("user", "Oi")])
                self.assertEqual(caught.exception.retryable, retryable)
                self.assertNotIn("fake-test-key", str(caught.exception))
                self.assertNotIn("sensitive", str(caught.exception))
                self.assertEqual(request.call_count, 1)

    def test_connection_and_timeout_errors(self):
        for error in (URLError("offline"), TimeoutError()):
            with self.subTest(error=type(error).__name__):
                with patch(TARGET, side_effect=error), self.assertRaises(ModelError) as caught:
                    self.model.complete([ChatMessage("user", "Oi")])
                self.assertTrue(caught.exception.retryable)

    def test_malformed_or_truncated_responses_are_rejected(self):
        invalid_call = {"id": "call_1", "type": "function", "function": {"name": "search", "arguments": "[]"}}
        cases = [
            {}, [], {"choices": []}, response_payload(" "),
            response_payload("incompleta", finish="length"),
            response_payload(None, [invalid_call], "tool_calls"),
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                with patch(TARGET, return_value=response_stream(payload)), self.assertRaises(ModelError):
                    self.model.complete([ChatMessage("user", "Oi")])
        with patch(TARGET, return_value=io.BytesIO(b"not json")), self.assertRaises(ModelError):
            self.model.complete([ChatMessage("user", "Oi")])


class ModelSettingsTests(unittest.TestCase):
    def test_settings_are_loaded_from_environment_without_showing_key(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": " fake-test-key ", "GEMINI_MODEL": "test-model"}, clear=True):
            settings = ModelSettings.from_environment()
        self.assertEqual(settings.api_key, "fake-test-key")
        self.assertEqual(settings.model, "test-model")
        self.assertNotIn("fake-test-key", repr(settings))

    def test_default_model_is_gemini(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-test-key"}, clear=True):
            settings = ModelSettings.from_environment()
        self.assertEqual(settings.model, "gemini-3.5-flash-lite")

    def test_missing_key_and_invalid_limits_are_rejected(self):
        for environment in (
            {}, {"GEMINI_API_KEY": "key", "GEMINI_MODEL": " "},
            {"GEMINI_API_KEY": "key", "LLM_TIMEOUT_SECONDS": "nan"},
            {"GEMINI_API_KEY": "key", "LLM_TIMEOUT_SECONDS": "0"},
            {"GEMINI_API_KEY": "key", "LLM_MAX_OUTPUT_TOKENS": "-1"},
            {"GEMINI_API_KEY": "key", "LLM_MAX_OUTPUT_TOKENS": "abc"},
        ):
            with self.subTest(environment=environment), patch.dict(os.environ, environment, clear=True):
                with self.assertRaises(ValueError):
                    ModelSettings.from_environment()


if __name__ == "__main__":
    unittest.main()
