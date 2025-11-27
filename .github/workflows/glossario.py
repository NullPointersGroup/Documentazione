from pathlib import Path
import re
import logging

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s | %(message)s')

SRC_DIR = Path("src")
EXCLUDE_DIRS = {"Candidatura", "Diario Di Bordo", "Glossario"}
IGNORE_FILENAMES = {"heading.tex", "table.tex", "title.tex", "modifiche.tex"}

def find_glossary():
    pb_gloss = SRC_DIR / "PB/Documenti Interni/Glossario/Glossario.tex"
    rtb_gloss = SRC_DIR / "RTB/Documenti Interni/Glossario/Glossario.tex"
    if pb_gloss.exists():
        EXCLUDE_DIRS.add("RTB")
        logging.info(f"Glossario trovato in PB: {pb_gloss}")
        return pb_gloss
    if rtb_gloss.exists():
        logging.info(f"Glossario trovato in RTB: {rtb_gloss}")
        return rtb_gloss
    logging.error("Nessun glossario trovato in PB o RTB")
    return None

def estrai_termini_da_file(fpath: Path):
    text = fpath.read_text(encoding="utf-8")
    # parser semplice per \term{...} con gestione di {} annidate
    termini = []
    pos = 0
    while True:
        idx = text.find(r"\term{", pos)
        if idx == -1:
            break
        idx += len(r"\term{")
        brace = 1
        start = idx
        while idx < len(text) and brace > 0:
            if text[idx] == "{":
                brace += 1
            elif text[idx] == "}":
                brace -= 1
            idx += 1
        termine_raw = text[start:idx-1].strip()
        # rimuove eventuali comandi annidati come \textbf{...}
        termine_clean = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', '', termine_raw).strip()
        if termine_clean:
            termini.append(termine_clean)
        pos = idx
    return termini

def build_patterns(termini):
    # rimuove vuoti e ordina per lunghezza decrescente (evita match dentro parole più lunghe)
    termini = [t for t in termini if t and t.strip()]
    termini = sorted(set(termini), key=len, reverse=True)
    patterns = []
    for term in termini:
        # regex: non preceduto da backslash, non parte di parola (\w), non già seguito da $^G$, non parte di parola dopo
        # Nota: \w è Unicode-aware in Python e gestisce lettere accentate.
        pat = re.compile(
            rf'(?<!\\)(?<!\w)({re.escape(term)})(?!\$\^G\$)(?!\w)',
            flags=re.IGNORECASE | re.MULTILINE
        )
        patterns.append((term, pat))
    return patterns

def should_skip(tex_file: Path):
    # esclude per cartelle specifiche
    if any(part in EXCLUDE_DIRS for part in tex_file.parts):
        logging.debug(f"Escluso per cartella: {tex_file}")
        return True
    # esclude nomi di file specifici
    if tex_file.name in IGNORE_FILENAMES:
        #logging.debug(f"Escluso per filename: {tex_file}")
        return True
    # esclude file con stem uguale al nome della cartella padre (sostituisci spazi con underscore)
    parent_name = tex_file.parent.name.replace(" ", "_")
    if tex_file.stem == parent_name:
        #logging.debug(f"Escluso per nome uguale alla cartella: {tex_file}")
        return True
    return False

def apply_tags_to_text(text: str, patterns, tex_file: Path):
    """
    Applica i patterns su `text`. Aggiunge '$^G$' solo se:
      - subito dopo il match non c'è già '$^G$'
      - e il carattere immediatamente successivo è uno spazio o non esiste (fine stringa)
    Se il carattere successivo è QUALSIASI COSA DIVERSA DALLA ' ' (spazio),
    il termine NON viene marcato.
    """
    new_text = text
    for term, pat in patterns:
        def repl(m):
            matched = m.group(1)
            # caratteri subito dopo il match nella stringa corrente
            after = new_text[m.end(): m.end() + 4]   # controllo rapido per $^G$
            if after.startswith("$^G$"):
                return matched
            # singolo carattere subito dopo (vuoto se fine stringa)
            after_char = new_text[m.end(): m.end() + 1]
            # se esiste un carattere e NON è spazio -> non marcare
            if after_char and after_char != " ":
                return matched
            # altrimenti (spazio o fine stringa) aggiungi tag
            return matched + "$^G$"

        new_text, n = pat.subn(repl, new_text)
        # opzionale: log se vuoi
        # if n:
        #     logging.info(f"  -> {n} sostituzioni per termine '{term}'")
    return new_text



def process_all_tex(root_dir: Path, patterns):
    for tex_file in root_dir.rglob("*.tex"):
        if should_skip(tex_file):
            #logging.info(f"Saltato file: {tex_file}")
            continue
        #logging.info(f"Scansione file: {tex_file}")
        text = tex_file.read_text(encoding="utf-8")
        new_text = apply_tags_to_text(text, patterns, tex_file)
        if new_text != text:
            tex_file.write_text(new_text, encoding="utf-8")
            logging.info(f"Modificato: {tex_file}")
        #else:
            #logging.info(f"Nessuna modifica: {tex_file}")

if __name__ == "__main__":
    logging.info("Inizio elaborazione")
    gloss = find_glossary()
    termini = []
    if gloss:
        # estrai termini dal file Glossario.tex
        termini.extend(estrai_termini_da_file(gloss))
        # estrai termini dai files letters nella stessa cartella del glossario
        letters_dir = gloss.parent / "content" / "letters"
        if letters_dir.exists():
            for f in sorted(letters_dir.glob("*.tex")):
                #logging.info(f"Lettura letters: {f}")
                termini.extend(estrai_termini_da_file(f))

    termini = [t for t in termini if t and t.strip()]
    patterns = build_patterns(termini)
    logging.info(f"Pattern creati per {len(patterns)} termini")
    print(termini)  # Stampa i termini trovati

    process_all_tex(SRC_DIR, patterns)
    logging.info("Elaborazione completata")
