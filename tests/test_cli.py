"""Interação do terminal e inicialização sem chamadas reais ao modelo."""

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from emporio_agent.interfaces.chat.cli import main, run_chat


CLI = "emporio_agent.interfaces.chat.cli"
SOURCE = Path(__file__).resolve().parents[1] / "data"


class TerminalChatTests(unittest.TestCase):
    def test_messages_help_and_exit(self):
        agent = Mock()
        agent.reply.return_value = "Olá, como posso ajudar?"
        with patch("builtins.input", side_effect=["", "/ajuda", "/desconhecido", "Oi", "/sair"]):
            with patch("sys.stdout", new_callable=io.StringIO) as output:
                run_chat(lambda: agent)
        agent.reply.assert_called_once_with("Oi")
        self.assertIn("Olá, como posso ajudar?", output.getvalue())
        self.assertIn("Comando desconhecido", output.getvalue())
        self.assertIn("Atendimento encerrado", output.getvalue())

    def test_clear_creates_new_agent_before_next_message(self):
        first, second = Mock(), Mock()
        factory = Mock(side_effect=[first, second])
        with patch("builtins.input", side_effect=["primeira", "/limpar", "segunda", "/sair"]):
            with patch("sys.stdout", new_callable=io.StringIO):
                run_chat(factory)
        first.reply.assert_called_once_with("primeira")
        second.reply.assert_called_once_with("segunda")
        self.assertEqual(factory.call_count, 2)

    def test_invalid_message_does_not_end_session(self):
        agent = Mock()
        agent.reply.side_effect = [ValueError("Mensagem longa"), "Resposta"]
        with patch("builtins.input", side_effect=["longa", "curta", "/sair"]):
            with patch("sys.stdout", new_callable=io.StringIO) as output:
                run_chat(lambda: agent)
        self.assertIn("Mensagem inválida: Mensagem longa", output.getvalue())
        self.assertIn("Assistente: Resposta", output.getvalue())

    def test_eof_and_keyboard_interrupt_exit_cleanly(self):
        for error in (EOFError(), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                with patch("builtins.input", side_effect=error), patch("sys.stdout", new_callable=io.StringIO):
                    run_chat(Mock())


class CliStartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / "store.sqlite3"
        self.env_file = self.root / ".env"
        self.args = ["--data-dir", str(SOURCE), "--database", str(self.database), "--env-file", str(self.env_file)]

    def test_first_run_imports_database_and_uses_selected_customer(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-test-key"}, clear=True):
            with patch(f"{CLI}.build_agent") as build, patch("builtins.input", return_value="/sair"):
                with patch("sys.stdout", new_callable=io.StringIO):
                    self.assertEqual(main([*self.args, "--customer-id", "3"]), 0)
        self.assertTrue(self.database.exists())
        self.assertEqual(build.call_args.kwargs["customer_id"], 3)

    def test_anonymous_session_and_existing_database_are_preserved(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-test-key"}, clear=True):
            with patch(f"{CLI}.build_agent"), patch("builtins.input", return_value="/sair"):
                with patch("sys.stdout", new_callable=io.StringIO):
                    self.assertEqual(main(self.args), 0)
                    with patch(f"{CLI}.import_csv_to_sqlite") as importer:
                        self.assertEqual(main(self.args), 0)
                        importer.assert_not_called()

    def test_unknown_customer_stops_before_starting_chat(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-test-key"}, clear=True):
            with patch(f"{CLI}.run_chat") as chat, patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(main([*self.args, "--customer-id", "9999"]), 1)
                chat.assert_not_called()

    def test_missing_key_stops_before_creating_database(self):
        with patch.dict(os.environ, {}, clear=True), patch("sys.stderr", new_callable=io.StringIO) as output:
            self.assertEqual(main(self.args), 1)
        self.assertFalse(self.database.exists())
        self.assertIn("configuração do Gemini", output.getvalue())

    def test_dotenv_loads_locally_without_overriding_environment(self):
        self.env_file.write_text("GEMINI_API_KEY=fake-file-key\nGEMINI_MODEL=file-model\n", encoding="utf-8")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-env-key"}, clear=True):
            with patch(f"{CLI}.GeminiModel") as model, patch(f"{CLI}.build_agent"):
                with patch("builtins.input", return_value="/sair"), patch("sys.stdout", new_callable=io.StringIO):
                    self.assertEqual(main(self.args), 0)
                settings = model.call_args.args[0]
                self.assertEqual(settings.api_key, "fake-env-key")
                self.assertEqual(settings.model, "file-model")


if __name__ == "__main__":
    unittest.main()
