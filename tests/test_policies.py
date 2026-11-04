"""Cenários de recuperação e preservação do contexto do manual."""

import tempfile
import unittest
from pathlib import Path

from emporio_agent.application.ports.policies import PolicySection
from emporio_agent.application.use_cases.search_policies import SearchPolicies
from emporio_agent.infrastructure.retrieval.pdf_policies import PolicyLoadError, load_policy_sections
from emporio_agent.infrastructure.retrieval.text_policy_search import TextPolicySearch


MANUAL = Path(__file__).resolve().parents[1] / "data" / "políticas_da_loja.pdf"


class PolicyRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sections = load_policy_sections(MANUAL)
        cls.search = SearchPolicies(TextPolicySearch(cls.sections))

    def test_extracts_ten_sections_with_source_pages(self):
        self.assertEqual([section.number for section in self.sections], list(range(1, 11)))
        for section in self.sections:
            self.assertEqual(section.source, MANUAL.name)
            self.assertTrue(section.text)
            self.assertTrue(section.pages)
            self.assertNotIn("Página ", section.text)
            self.assertNotIn("Empório da Música Manual de Políticas e Procedimentos", section.text)

    def test_returns_and_shipping_keep_exceptions_and_page_continuations(self):
        returns = self.sections[3]
        self.assertIn("7 (sete) dias corridos após o recebimento", returns.text)
        self.assertIn("4.4 Itens Não Elegíveis", returns.text)
        self.assertIn("venda final", returns.text)
        shipping = self.sections[4]
        self.assertEqual(shipping.pages, (4, 5))
        self.assertIn("5.1 Entregas", shipping.text)
        self.assertIn("5.3 Código de Rastreamento", shipping.text)
        self.assertIn("SEDEX", shipping.text)

    def test_numbered_service_steps_are_not_mistaken_for_sections(self):
        service = self.sections[6]
        self.assertEqual(service.pages, (6, 7))
        self.assertIn("3. Consulta:", service.text)
        self.assertIn("4. Resposta:", service.text)
        self.assertIn("7.3 Situações Especiais", service.text)

    def test_customer_questions_retrieve_expected_section_first(self):
        cases = (
            ("Qual o endereço?", 1),
            ("Que horas abre?", 2),
            ("Como parcelar o pagamento?", 3),
            ("Me arrependi, posso devolver?", 4),
            ("Qual o prazo do frete SEDEX?", 5),
            ("Promoções e descontos acumulam no PIX?", 6),
            ("Qual a garantia legal?", 8),
            ("Privacidade e proteção de dados", 9),
        )
        for query, expected in cases:
            with self.subTest(query=query):
                results = self.search.execute(query)
                self.assertTrue(results)
                self.assertEqual(results[0].number, expected)

    def test_case_accents_limit_and_unrelated_questions(self):
        self.assertEqual(self.search.execute("PROMOÇÕES"), self.search.execute("promocoes"))
        self.assertEqual(len(self.search.execute("pagamento frete garantia", limit=1)), 1)
        self.assertEqual(self.search.execute("astronomia galaxias telescopio"), [])
        self.assertEqual(self.search.execute("a de para"), [])


class PolicyBoundaryTests(unittest.TestCase):
    def test_invalid_queries_and_limits_are_rejected(self):
        search = SearchPolicies(TextPolicySearch(()))
        for query in (None, 12, "", "  "):
            with self.subTest(query=query), self.assertRaises(ValueError):
                search.execute(query)
        for limit in (0, 6, True, "3"):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                search.execute("horario", limit)

    def test_missing_corrupt_and_textless_pdf_are_rejected(self):
        from pypdf import PdfWriter

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manual.pdf"
            with self.assertRaises(PolicyLoadError):
                load_policy_sections(path)
            path.write_bytes(b"%PDF-1.4\ncorrupt document")
            with self.assertLogs("pypdf", level="WARNING"), self.assertRaises(PolicyLoadError):
                load_policy_sections(path)
            writer = PdfWriter()
            writer.add_blank_page(width=100, height=100)
            with path.open("wb") as stream:
                writer.write(stream)
            with self.assertRaisesRegex(PolicyLoadError, "dez seções"):
                load_policy_sections(path)

    def test_use_case_accepts_an_alternative_search_implementation(self):
        section = PolicySection(2, "Horário", "Horário de atendimento", "manual.pdf", (2,))
        received = []

        class MemorySearch:
            def search(self, query, limit):
                received.append((query, limit))
                return [section]

        self.assertEqual(SearchPolicies(MemorySearch()).execute(" horario ", 1), [section])
        self.assertEqual(received, [("horario", 1)])


if __name__ == "__main__":
    unittest.main()
