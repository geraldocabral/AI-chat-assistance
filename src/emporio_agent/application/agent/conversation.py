"""Fluxo limitado de chamadas ao modelo e ferramentas, com histórico por sessão."""

import logging
from time import perf_counter

from emporio_agent.application.agent.instructions import SYSTEM_INSTRUCTIONS
from emporio_agent.application.agent.tools import AgentTools
from emporio_agent.application.ports.language_model import ChatMessage, LanguageModel, ModelError


logger = logging.getLogger(__name__)
FAILURE_REPLY = "Não consegui concluir a consulta agora. Tente novamente em instantes."
LIMIT_REPLY = "Não consegui concluir dentro do limite de consultas. Pode simplificar ou detalhar sua pergunta?"


class ConversationAgent:
    def __init__(
        self, model: LanguageModel, tools: AgentTools, *,
        max_model_calls: int = 4, max_tool_calls: int = 8, history_turns: int = 6,
    ) -> None:
        for value in (max_model_calls, max_tool_calls, history_turns):
            if type(value) is not int or value < 1:
                raise ValueError("Limites da conversa devem ser inteiros positivos")
        self._model = model
        self._tools = tools
        self._max_model_calls = max_model_calls
        self._max_tool_calls = max_tool_calls
        self._history_turns = history_turns
        self._turns: list[list[ChatMessage]] = []

    def _remember(self, messages: list[ChatMessage]) -> None:
        self._turns.append(messages)
        self._turns = self._turns[-self._history_turns:]

    def reply(self, text: str) -> str:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Informe uma mensagem não vazia")
        if len(text) > 4000:
            raise ValueError("A mensagem deve ter até 4000 caracteres")
        user = ChatMessage("user", text.strip())
        history = [message for turn in self._turns for message in turn]
        messages = [ChatMessage("system", SYSTEM_INSTRUCTIONS), *history, user]
        turn = [user]
        tool_count = 0
        fallback = LIMIT_REPLY
        for model_call in range(self._max_model_calls):
            started = perf_counter()
            try:
                reply = self._model.complete(list(messages), self._tools.definitions)
            except ModelError:
                logger.warning("model_failed duration_ms=%.0f", (perf_counter() - started) * 1000)
                fallback = FAILURE_REPLY
                break
            logger.info(
                "model_completed duration_ms=%.0f input_tokens=%s output_tokens=%s",
                (perf_counter() - started) * 1000, reply.input_tokens, reply.output_tokens,
            )
            message = reply.message
            if not message.tool_calls:
                if message.content is None or not message.content.strip():
                    fallback = FAILURE_REPLY
                    break
                turn.append(message)
                self._remember(turn)
                return message.content
            if model_call == self._max_model_calls - 1 or tool_count + len(message.tool_calls) > self._max_tool_calls:
                break
            messages.append(message)
            turn.append(message)
            for call in message.tool_calls:
                tool_count += 1
                started = perf_counter()
                try:
                    result = self._tools.execute(call)
                except Exception as error:
                    logger.warning("tool_failed error_type=%s", type(error).__name__)
                    result = '{"ok":false,"error":"Consulta temporariamente indisponível"}'
                name = call.name if call.name in {tool.name for tool in self._tools.definitions} else "unknown"
                logger.info("tool_completed name=%s duration_ms=%.0f", name, (perf_counter() - started) * 1000)
                response = ChatMessage("tool", result, tool_call_id=call.call_id)
                messages.append(response)
                turn.append(response)
        self._remember([user, ChatMessage("assistant", fallback)])
        return fallback
