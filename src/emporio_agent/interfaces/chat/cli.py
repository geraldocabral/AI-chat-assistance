"""Chat de terminal com composição explícita da sessão de demonstração."""

import argparse
import logging
import sqlite3
import sys
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

from dotenv import load_dotenv

from emporio_agent.application.agent.conversation import ConversationAgent
from emporio_agent.bootstrap import build_agent
from emporio_agent.config import ModelSettings
from emporio_agent.infrastructure.llm.gemini_model import GeminiModel
from emporio_agent.infrastructure.persistence.sqlite_import import import_csv_to_sqlite


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Informe um inteiro positivo") from None
    if number < 1:
        raise argparse.ArgumentTypeError("Informe um inteiro positivo")
    return number


def _check_customer(database: Path, customer_id: int | None) -> None:
    if customer_id is None:
        return
    if customer_id > 2**63 - 1:
        raise ValueError("Cliente de demonstração não encontrado")
    uri = database.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        exists = connection.execute(
            "SELECT 1 FROM customers WHERE customer_id = ?", (customer_id,),
        ).fetchone()
    if exists is None:
        raise ValueError("Cliente de demonstração não encontrado")


def run_chat(create_agent: Callable[[], ConversationAgent]) -> None:
    agent = create_agent()
    print("Empório da Música — assistente virtual")
    print("Digite /ajuda para ver os comandos ou /sair para encerrar.")
    try:
        while True:
            text = input("Você: ").strip()
            if not text:
                continue
            command = text.casefold()
            if command == "/sair":
                break
            if command == "/ajuda":
                print("/limpar: inicia uma conversa sem histórico, mantendo o cliente da sessão.")
                print("/sair: encerra o chat.")
                continue
            if command == "/limpar":
                agent = create_agent()
                print("Conversa reiniciada.")
                continue
            if command.startswith("/"):
                print("Comando desconhecido. Digite /ajuda.")
                continue
            try:
                print(f"Assistente: {agent.reply(text)}")
            except ValueError as error:
                print(f"Mensagem inválida: {error}")
    except (EOFError, KeyboardInterrupt):
        print()
    print("Atendimento encerrado.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assistente da Empório da Música no terminal")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--database", type=Path, default=Path("var/store.sqlite3"))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--customer-id", type=_positive_int, help="Cliente simulado; não representa autenticação real")
    parser.add_argument("--verbose", action="store_true", help="Mostra métricas de execução")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        load_dotenv(args.env_file, override=False)
        settings = ModelSettings.from_environment()
        if not args.database.exists():
            import_csv_to_sqlite(args.data_dir, args.database)
        _check_customer(args.database, args.customer_id)
        model = GeminiModel(settings)

        def create_agent() -> ConversationAgent:
            return build_agent(
                model, args.database, args.data_dir / "políticas_da_loja.pdf",
                customer_id=args.customer_id,
            )

        if args.customer_id is None:
            print("Sessão anônima: consulta de pedidos indisponível.")
        else:
            print(f"Sessão de demonstração: cliente {args.customer_id} (identidade simulada).")
        run_chat(create_agent)
    except (OSError, ValueError, sqlite3.Error):
        print(
            "Não foi possível iniciar o chat. Verifique a configuração do Gemini, "
            "o cliente selecionado e os arquivos de dados.",
            file=sys.stderr,
        )
        return 1
    return 0
