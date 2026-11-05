"""Interface web local; agentes e credenciais permanecem no servidor."""

import argparse
import logging
import secrets
import sqlite3
import sys
from collections import OrderedDict
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session

from emporio_agent.application.agent.conversation import ConversationAgent
from emporio_agent.bootstrap import build_agent
from emporio_agent.config import ModelSettings
from emporio_agent.infrastructure.llm.gemini_model import GeminiModel
from emporio_agent.infrastructure.persistence.sqlite_import import import_csv_to_sqlite


@dataclass
class _ChatSession:
    agent: ConversationAgent
    customer_id: int | None
    messages: list[dict[str, str]] = field(default_factory=list)


def create_app(
    create_agent: Callable[[int | None], ConversationAgent], customer_ids: tuple[int, ...] = (),
) -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=secrets.token_hex(32), MAX_CONTENT_LENGTH=32_000,
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict",
    )
    conversations: OrderedDict[str, _ChatSession] = OrderedDict()

    def current_chat() -> _ChatSession:
        identifier = session.get("chat_id")
        if identifier not in conversations:
            identifier = secrets.token_urlsafe(24)
            conversations[identifier] = _ChatSession(create_agent(None), None)
            session["chat_id"] = identifier
            while len(conversations) > 32:
                conversations.popitem(last=False)
        conversations.move_to_end(identifier)
        return conversations[identifier]

    def state(chat: _ChatSession):
        return jsonify(messages=chat.messages, customer_id=chat.customer_id, customer_ids=customer_ids)

    @app.before_request
    def check_origin():
        if request.method == "POST":
            origin = request.headers.get("Origin")
            if origin and origin != request.host_url.rstrip("/"):
                return jsonify(error="Origem da requisição não permitida"), 403

    @app.get("/")
    def index():
        return render_template("chat.html")

    @app.get("/api/session")
    def get_session():
        return state(current_chat())

    @app.post("/api/messages")
    def send_message():
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or set(body) != {"message"}:
            return jsonify(error="Envie apenas o campo message"), 400
        text = body["message"]
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            return jsonify(error="Escreva uma mensagem entre 1 e 4000 caracteres"), 400
        chat = current_chat()
        answer = chat.agent.reply(text.strip())
        chat.messages.extend(({"role": "user", "content": text.strip()}, {"role": "assistant", "content": answer}))
        chat.messages = chat.messages[-12:]
        return state(chat)

    @app.post("/api/session")
    def reset_session():
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or set(body) != {"customer_id"}:
            return jsonify(error="Informe o cliente da nova sessão ou null"), 400
        customer_id = body["customer_id"]
        if customer_id is not None and (type(customer_id) is not int or customer_id not in customer_ids):
            return jsonify(error="Cliente de demonstração inválido"), 400
        agent = create_agent(customer_id)
        identifier = session.pop("chat_id", None)
        if identifier in conversations:
            del conversations[identifier]
        identifier = secrets.token_urlsafe(24)
        conversations[identifier] = _ChatSession(agent, customer_id)
        session["chat_id"] = identifier
        while len(conversations) > 32:
            conversations.popitem(last=False)
        return state(conversations[identifier])

    @app.errorhandler(Exception)
    def unexpected_error(error):
        from werkzeug.exceptions import HTTPException

        if isinstance(error, HTTPException):
            return jsonify(error="Requisição inválida"), error.code
        app.logger.error("web_request_failed error_type=%s", type(error).__name__)
        return jsonify(error="Não foi possível concluir. Tente novamente."), 500

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chat local da Empório da Música no navegador")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--database", type=Path, default=Path("var/store.sqlite3"))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("A porta deve estar entre 1 e 65535")
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)
    try:
        load_dotenv(args.env_file, override=False)
        model = GeminiModel(ModelSettings.from_environment())
        if not args.database.exists():
            import_csv_to_sqlite(args.data_dir, args.database)
        uri = args.database.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            customer_ids = tuple(row[0] for row in connection.execute("SELECT customer_id FROM customers ORDER BY customer_id"))

        def create_agent(customer_id: int | None) -> ConversationAgent:
            return build_agent(model, args.database, args.data_dir / "políticas_da_loja.pdf", customer_id=customer_id)

        # Valida também o manual antes de disponibilizar a página.
        create_agent(None)
        app = create_app(create_agent, customer_ids)
        print(f"Abra http://127.0.0.1:{args.port} no navegador. Ctrl+C para encerrar.")
        app.run(host="127.0.0.1", port=args.port, debug=False, threaded=False)
    except (OSError, ValueError, sqlite3.Error):
        print("Não foi possível iniciar. Verifique configuração, dados e porta.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
