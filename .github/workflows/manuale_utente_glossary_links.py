from __future__ import annotations

import argparse
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple


logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
LOGGER = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
MANUAL_ROOT = REPO_ROOT / "src" / "PB" / "Documenti Esterni" / "Manuale Utente"
CONTENT_ROOT = MANUAL_ROOT / "content"
GLOSSARY_PATH = CONTENT_ROOT / "glossario.tex"

SKIP_FILES = {
    "glossario.tex",
    "heading.tex",
    "title.tex",
    "table.tex",
    "modifiche.tex",
}
SECTION_COMMANDS = (
    "section",
    "subsection",
    "subsubsection",
    "subsubsubsection",
    "subsubsubsubsection",
    "caption",
)
PROTECTED_COMMANDS = (
    "href",
    "url",
    "hyperlink",
    "hypertarget",
    "hyperref",
    "ref",
    "label",
    "term",
    "input",
    "includegraphics",
)
PROTECTED_ENVIRONMENTS = ("lstlisting", "verbatim")


@dataclass(frozen=True)
class GlossaryTerm:
    term: str
    anchor: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text.lower()).strip("-")
    return cleaned or "term"


def strip_latex_markup(value: str) -> str:
    result = value.strip()

    # Unwrap nested commands that carry visible text.
    patterns = [
        re.compile(r"\\hypertarget\{[^{}]*\}\{([^{}]*)\}"),
        re.compile(r"\\hyperlink\{[^{}]*\}\{([^{}]*)\}"),
        re.compile(r"\\texttt\{([^{}]*)\}"),
        re.compile(r"\\textbf\{([^{}]*)\}"),
        re.compile(r"\\emph\{([^{}]*)\}"),
        re.compile(r"\\vr\{([^{}]*)\}"),
        re.compile(r"\\vrs\{([^{}]*)\}"),
    ]

    changed = True
    while changed:
        changed = False
        for pattern in patterns:
            updated = pattern.sub(r"\1", result)
            if updated != result:
                result = updated
                changed = True

    result = result.replace(r"\_", "_")
    result = re.sub(r"\s+", " ", result).strip()
    return result


def iter_term_commands(text: str) -> Iterable[Tuple[int, int, str]]:
    token = r"\term{"
    pos = 0

    while True:
        start = text.find(token, pos)
        if start == -1:
            break

        index = start + len(token)
        depth = 1
        inner_start = index

        while index < len(text) and depth > 0:
            char = text[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            index += 1

        if depth == 0:
            yield start, index, text[inner_start:index - 1]

        pos = index


def extract_glossary_terms(glossary_text: str) -> List[GlossaryTerm]:
    terms: List[GlossaryTerm] = []

    for _start, _end, raw_term in iter_term_commands(glossary_text):
        visible_term = strip_latex_markup(raw_term)
        if not visible_term:
            continue
        terms.append(GlossaryTerm(term=visible_term, anchor=f"glossario:{slugify(visible_term)}"))

    unique: dict[str, GlossaryTerm] = {}
    for entry in terms:
        unique.setdefault(entry.term.lower(), entry)

    return sorted(unique.values(), key=lambda item: len(item.term), reverse=True)


def ensure_glossary_targets(glossary_text: str, terms: Sequence[GlossaryTerm]) -> str:
    terms_by_key = {term.term.lower(): term for term in terms}
    chunks: List[str] = []
    cursor = 0

    for start, end, raw_term in iter_term_commands(glossary_text):
        chunks.append(glossary_text[cursor:start])
        visible_term = strip_latex_markup(raw_term)
        entry = terms_by_key.get(visible_term.lower())

        if raw_term.lstrip().startswith(r"\hypertarget{") or entry is None:
            chunks.append(glossary_text[start:end])
        else:
            replacement = rf"\term{{\hypertarget{{{entry.anchor}}}{{{raw_term}}}}}"
            chunks.append(replacement)

        cursor = end

    chunks.append(glossary_text[cursor:])
    return "".join(chunks)


def find_brace_ranges(text: str, command: str) -> List[Tuple[int, int]]:
    ranges: List[Tuple[int, int]] = []
    token = f"\\{command}"
    pos = 0

    while True:
        start = text.find(token, pos)
        if start == -1:
            break

        brace_start = text.find("{", start + len(token))
        if brace_start == -1:
            pos = start + len(token)
            continue

        index = brace_start + 1
        depth = 1
        while index < len(text) and depth > 0:
            char = text[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            index += 1

        if depth == 0:
            ranges.append((brace_start + 1, index - 1))
            pos = index
        else:
            pos = brace_start + 1

    return ranges


def find_command_ranges(text: str, command: str) -> List[Tuple[int, int]]:
    pattern = re.compile(rf"\\{command}(?:\[[^\]]*\])?(?:\{{[^{{}}]*\}})*(?:\[[^\]]*\])?")
    return [(match.start(), match.end()) for match in pattern.finditer(text)]


def find_environment_ranges(text: str, environment: str) -> List[Tuple[int, int]]:
    pattern = re.compile(
        rf"\\begin\{{{environment}\}}.*?\\end\{{{environment}\}}",
        flags=re.DOTALL,
    )
    return [(match.start(), match.end()) for match in pattern.finditer(text)]


def find_comment_ranges(text: str) -> List[Tuple[int, int]]:
    ranges: List[Tuple[int, int]] = []
    for match in re.finditer(r"(?<!\\)%.*", text):
        ranges.append((match.start(), match.end()))
    return ranges


def build_protected_ranges(text: str) -> List[Tuple[int, int]]:
    ranges: List[Tuple[int, int]] = []

    for command in SECTION_COMMANDS:
        ranges.extend(find_brace_ranges(text, command))

    for command in PROTECTED_COMMANDS:
        ranges.extend(find_command_ranges(text, command))

    for environment in PROTECTED_ENVIRONMENTS:
        ranges.extend(find_environment_ranges(text, environment))

    ranges.extend(find_comment_ranges(text))
    ranges.sort()
    return ranges


def is_protected(index: int, ranges: Sequence[Tuple[int, int]]) -> bool:
    return any(start <= index < end for start, end in ranges)


def build_term_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term)
    return re.compile(
        rf"(?<![\\\w])({escaped})(\$\^G\$)?(?!\w)",
        flags=re.IGNORECASE,
    )


def link_terms_in_text(text: str, glossary_terms: Sequence[GlossaryTerm]) -> str:
    protected_ranges = build_protected_ranges(text)
    replacements: List[Tuple[int, int, str]] = []
    occupied: List[Tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(not (end <= occ_start or start >= occ_end) for occ_start, occ_end in occupied)

    for glossary_term in glossary_terms:
        pattern = build_term_pattern(glossary_term.term)

        for match in pattern.finditer(text):
            start, end = match.span()
            if is_protected(start, protected_ranges):
                continue
            if overlaps(start, end):
                continue

            before_char = text[start - 1:start] if start > 0 else ""
            after_char = text[end:end + 1]
            if before_char == "." or after_char == ".":
                continue

            visible_text = match.group(0)
            replacement = rf"\hyperlink{{{glossary_term.anchor}}}{{{visible_text}}}"
            replacements.append((start, end, replacement))
            occupied.append((start, end))

    if not replacements:
        return text

    output = text
    for start, end, replacement in sorted(replacements, key=lambda item: item[0], reverse=True):
        output = output[:start] + replacement + output[end:]

    return output


def iter_manual_files() -> Iterable[Path]:
    for tex_file in CONTENT_ROOT.rglob("*.tex"):
        if tex_file.name in SKIP_FILES:
            continue
        yield tex_file


def process_manual_files(glossary_terms: Sequence[GlossaryTerm], apply_changes: bool) -> int:
    changed_files = 0

    for tex_file in iter_manual_files():
        original = read_text(tex_file)
        updated = link_terms_in_text(original, glossary_terms)

        if updated != original:
            changed_files += 1
            LOGGER.info("Aggiornato file manuale: %s", tex_file.relative_to(REPO_ROOT))
            if apply_changes:
                write_text(tex_file, updated)

    return changed_files


def process_glossary(glossary_terms: Sequence[GlossaryTerm], apply_changes: bool) -> bool:
    original = read_text(GLOSSARY_PATH)
    updated = ensure_glossary_targets(original, glossary_terms)

    if updated == original:
        return False

    LOGGER.info("Aggiornato glossario: %s", GLOSSARY_PATH.relative_to(REPO_ROOT))
    if apply_changes:
        write_text(GLOSSARY_PATH, updated)
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggiunge hyperlink interni dal Manuale Utente al glossario.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Esegue solo l'analisi senza modificare i file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not MANUAL_ROOT.exists():
        raise FileNotFoundError(f"Cartella Manuale Utente non trovata: {MANUAL_ROOT}")
    if not GLOSSARY_PATH.exists():
        raise FileNotFoundError(f"Glossario del Manuale Utente non trovato: {GLOSSARY_PATH}")

    glossary_text = read_text(GLOSSARY_PATH)
    glossary_terms = extract_glossary_terms(glossary_text)

    if not glossary_terms:
        raise RuntimeError("Nessun termine trovato in content/glossario.tex")

    LOGGER.info("Termini glossario rilevati: %s", len(glossary_terms))
    apply_changes = not args.check

    glossary_changed = process_glossary(glossary_terms, apply_changes)
    manual_changed = process_manual_files(glossary_terms, apply_changes)

    if args.check:
        LOGGER.info(
            "Check completato. Glossario da aggiornare: %s. File manuale da aggiornare: %s.",
            "si" if glossary_changed else "no",
            manual_changed,
        )
    else:
        LOGGER.info(
            "Aggiornamento completato. Glossario modificato: %s. File manuale modificati: %s.",
            "si" if glossary_changed else "no",
            manual_changed,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
