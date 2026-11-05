"""Extração das dez seções principais do manual fornecido."""

import re
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from emporio_agent.application.ports.policies import PolicySection


class PolicyLoadError(ValueError):
    """Manual ausente, ilegível ou com estrutura incompatível."""


def _split_sections(page_texts: list[str], source: str) -> tuple[PolicySection, ...]:
    sections = []
    number = 0
    title = ""
    lines: list[str] = []
    pages: set[int] = set()
    for page, text in enumerate(page_texts, start=1):
        for raw_line in text.splitlines():
            line = " ".join(raw_line.split())
            if not line or re.fullmatch(r"Página \d+", line):
                continue
            if line == "Empório da Música Manual de Políticas e Procedimentos":
                continue
            heading = re.fullmatch(r"(\d{1,2})\.\s+(.+)", line)
            if heading and int(heading[1]) == number + 1:
                if number:
                    sections.append(PolicySection(number, title, " ".join(lines), source, tuple(sorted(pages))))
                number = int(heading[1])
                title = heading[2]
                lines = [line]
                pages = {page}
            elif number:
                lines.append(line)
                pages.add(page)
    if number:
        sections.append(PolicySection(number, title, " ".join(lines), source, tuple(sorted(pages))))
    if len(sections) != 10:
        raise PolicyLoadError("Manual incompatível: esperadas dez seções principais numeradas de 1 a 10")
    return tuple(sections)


def load_policy_sections(path: Path) -> tuple[PolicySection, ...]:
    """Lê o PDF uma vez e mantém regras e exceções na mesma seção."""
    try:
        with path.open("rb") as stream:
            reader = PdfReader(stream)
            page_texts = [page.extract_text(extraction_mode="layout") or "" for page in reader.pages]
    except (OSError, PyPdfError, ValueError) as error:
        raise PolicyLoadError(f"{path.name}: não foi possível ler o manual") from error
    return _split_sections(page_texts, path.name)
