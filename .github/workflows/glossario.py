from pathlib import Path
import re
import logging
from typing import List, Tuple, Pattern, Optional, Set

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s | %(message)s')

SRC_DIR: Path = Path("src")
EXCLUDE_DIRS: Set[str] = {"Candidatura", "Diario Di Bordo", "Glossario"}
IGNORE_FILENAMES: Set[str] = {"heading.tex", "table.tex", "title.tex", "modifiche.tex"}


def find_glossary() -> Optional[Path]:
    pb_gloss: Path = SRC_DIR / "PB/Documenti Interni/Glossario/Glossario.tex"
    rtb_gloss: Path = SRC_DIR / "RTB/Documenti Interni/Glossario/Glossario.tex"
    if pb_gloss.exists():
        EXCLUDE_DIRS.add("RTB")
        logging.info(f"Glossario trovato in PB: {pb_gloss}")
        return pb_gloss
    if rtb_gloss.exists():
        logging.info(f"Glossario trovato in RTB: {rtb_gloss}")
        return rtb_gloss
    logging.error("Nessun glossario trovato in PB o RTB")
    return None


def estrai_termini_da_file(fpath: Path) -> List[str]:
    text: str = fpath.read_text(encoding="utf-8")
    termini: List[str] = []
    pos: int = 0
    while True:
        idx: int = text.find(r"\term{", pos)
        if idx == -1:
            break
        idx += len(r"\term{")
        brace: int = 1
        start: int = idx
        while idx < len(text) and brace > 0:
            if text[idx] == "{":
                brace += 1
            elif text[idx] == "}":
                brace -= 1
            idx += 1
        termine_raw: str = text[start:idx - 1].strip()
        termine_clean: str = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', '', termine_raw).strip()
        if termine_clean:
            termini.append(termine_clean)
        pos = idx
    return termini


def build_patterns(termini: List[str]) -> List[Tuple[str, Pattern]]:
    termini_filtered: List[str] = [t for t in termini if t and t.strip()]
    termini_sorted: List[str] = sorted(set(termini_filtered), key=len, reverse=True)
    patterns: List[Tuple[str, Pattern]] = []
    for term in termini_sorted:
        pat: Pattern = re.compile(
            rf'(?<!\\)(?<!\w)({re.escape(term)})(?!\$\^G\$)(?!\w)',
            flags=re.IGNORECASE | re.MULTILINE
        )
        patterns.append((term, pat))
    return patterns


def should_skip(tex_file: Path) -> bool:
    if any(part in EXCLUDE_DIRS for part in tex_file.parts):
        return True
    if tex_file.name in IGNORE_FILENAMES:
        return True
    parent_name: str = tex_file.parent.name.replace(" ", "_")
    if tex_file.stem == parent_name:
        return True
    return False


def apply_tags_to_text(text: str, patterns: List[Tuple[str, Pattern]], tex_file: Path) -> str:
    """
    Applica i patterns su `text` aggiungendo $^G$ solo se:
      - subito dopo il match non c'è già $^G$
      - il match NON è all'interno di un titolo (section, subsection, subsubsection, ...)
      - il carattere successivo è spazio o fine stringa
    Rimuove prima eventuali tag esistenti.
    """
    new_text: str = re.sub(r'\$\^G\$', '', text)
    title_ranges: List[Tuple[int, int]] = []

    # Sezioni/subsezioni
    for m in re.finditer(r'\\(?:sub)*section\{(.*?)\}', new_text, flags=re.MULTILINE):
        start, end = m.start(1), m.end(1)
        title_ranges.append((start, end))

    # Caption
    for m in re.finditer(r'\\caption\{(.*?)\}', new_text, flags=re.MULTILINE):
        start, end = m.start(1), m.end(1)
        title_ranges.append((start, end))

    def in_title(pos: int) -> bool:
        return any(start <= pos < end for start, end in title_ranges)

    occupied: List[Tuple[int, int]] = []
    inserts: List[Tuple[int, str, str]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(not (end <= s or start >= e) for s, e in occupied)

    for _, pat in patterns:
        for m in pat.finditer(new_text):
            start, end = m.start(1), m.end(1)
            if in_title(start):
                continue
            if overlaps(start, end):
                continue
            after_char: str = new_text[end:end + 1]
            if after_char and after_char not in {" ", ".", ",", ";", ":"}:
                continue
            inserts.append((end, "$^G$", m.group(1)))
            occupied.append((start, end))

    for pos, insert_text, matched in sorted(inserts, key=lambda x: x[0], reverse=True):
        new_text = new_text[:pos] + insert_text + new_text[pos:]
        logging.debug(f"Aggiunto $^G$ a '{matched}' in file {tex_file}")

    return new_text


def process_all_tex(root_dir: Path, patterns: List[Tuple[str, Pattern]]) -> None:
    for tex_file in root_dir.rglob("*.tex"):
        if should_skip(tex_file):
            continue
        text: str = tex_file.read_text(encoding="utf-8")
        new_text: str = apply_tags_to_text(text, patterns, tex_file)
        if new_text != text:
            tex_file.write_text(new_text, encoding="utf-8")
            logging.info(f"Modificato: {tex_file}")


if __name__ == "__main__":
    logging.info("Inizio elaborazione")
    gloss: Optional[Path] = find_glossary()
    termini: List[str] = []

    if gloss:
        termini.extend(estrai_termini_da_file(gloss))
        letters_dir: Path = gloss.parent / "content" / "letters"
        if letters_dir.exists():
            for f in sorted(letters_dir.glob("*.tex")):
                termini.extend(estrai_termini_da_file(f))

    termini_filtered: List[str] = [t for t in termini if t and t.strip()]
    patterns: List[Tuple[str, Pattern]] = build_patterns(termini_filtered)
    logging.info(f"Pattern creati per {len(patterns)} termini")
    print(termini_filtered)

    process_all_tex(SRC_DIR, patterns)
    logging.info("Elaborazione completata")