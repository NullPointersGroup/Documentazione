import os
import re
import shutil
import subprocess
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional

# Optional runtime type-checking with beartype. Disable by setting BEARTYPE_ENABLE=0 in the environment.
try:
    from beartype import beartype as _beartype
except Exception:  # beartype not installed
    def _beartype(func):
        return func

BEARTYPE_ENABLED = os.getenv("BEARTYPE_ENABLE", "1") != "0"

def maybe_beartype(func):
    """Return beartype-decorated function if enabled, otherwise original function."""
    return _beartype(func) if BEARTYPE_ENABLED else func

# Configuration
INDEX_HTML_PATH = Path("index.html")
SRC_DIR = Path("src")
OUTPUT_DIR = Path("output")
SECTION_ORDER = ["RTB", "PB", "Candidatura", "Diario Di Bordo"]
MAX_DEPTH = 2

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


@maybe_beartype
def format_filename(filename: str) -> str:
    """Formatta il nome file secondo le regole specificate nel codice originale.

    - se il nome inizia con YYYY-MM-DD: mantiene la data come prefisso
    - aggiunge _VE se contiene "est" (verbale esterno) o _VI se contiene "int" (verbale interno)
    - altrimenti restituisce il nome base (senza estensione)
    """
    name, _ext = os.path.splitext(filename)
    parts = name.split("_")
    first = parts[0]

    if re.match(r"^\d{4}-\d{2}-\d{2}$", first):
        date = first
        lower_name = name.lower()
        if "est" in lower_name:
            return f"{date}_VE"
        if "int" in lower_name:
            return f"{date}_VI"
        return date

    return name


@maybe_beartype
def cleanup_source_pdf(src_dir: Path = SRC_DIR) -> None:
    """Rimuove file generati temporanei nella sorgente (.pdf, .log, .aux, ...)."""
    patterns = (".pdf", ".log", ".aux", ".fls", ".out", ".fdb_latexmk", ".synctex.gz", ".toc")
    for root, _dirs, files in os.walk(src_dir):
        for file in files:
            if file.endswith(patterns):
                try:
                    os.remove(os.path.join(root, file))
                except Exception:
                    logger.debug(f"Could not remove {os.path.join(root, file)}")


@maybe_beartype
def compile_tex_to_pdf(
    src_dir: Path = SRC_DIR,
    output_dir: Path = OUTPUT_DIR,
    max_depth: Optional[int] = MAX_DEPTH,
    latexmk_cmd: str = "latexmk",
    timeout_sec: int = 60,
) -> None:
    """Compila file .tex trovati nella cartella src e copia i PDF generati in output/.

    Nota: non cancella l'intera cartella output per evitare rimozioni accidentali. Sovrascrive i PDF trovati.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    tex_files: List[Path] = []
    for tex_path in src_dir.rglob("*.tex"):
        try:
            with open(tex_path, "r", encoding="utf-8", errors="ignore") as f:
                head = f.read(4096)
                if "\\documentclass" in head:
                    tex_files.append(tex_path)
        except Exception:
            logger.debug(f"Skipped unreadable tex file: {tex_path}")

    for tex_file in tex_files:
        tex_dir = tex_file.parent
        tex_name = tex_file.name
        try:
            #logger.info(f"Compiling {tex_file}...")
            res = subprocess.run(
                [latexmk_cmd, "-pdf", "-interaction=nonstopmode", "-f", tex_name],
                cwd=str(tex_dir),
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            if res.returncode != 0:
                logger.warning(f"latexmk failed for {tex_file}: {res.stderr.strip()}")
                continue

            pdf_name = tex_file.stem + ".pdf"
            pdf_path = tex_dir / pdf_name
            if pdf_path.exists():
                relative_parts = tex_dir.relative_to(src_dir).parts if tex_dir != src_dir else ()
                if max_depth is not None and len(relative_parts) > max_depth:
                    relative_parts = relative_parts[:max_depth]
                dest_dir = output_dir.joinpath(*relative_parts)
                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(pdf_path, dest_dir / pdf_name)
                #logger.info(f"Copied {pdf_path} -> {dest_dir / pdf_name}")
        except subprocess.TimeoutExpired:
            logger.warning(f"Compilation timed out for {tex_file}")
        except Exception as e:
            logger.exception(f"Error processing {tex_file}: {e}")

    # Pulizia dei file temporanei generati nella cartella src
    cleanup_source_pdf(src_dir)


@maybe_beartype
def build_tree(path: Path, depth: int = 0, max_depth: Optional[int] = MAX_DEPTH) -> Dict[str, Any]:
    node: Dict[str, Any] = {}
    if not path.exists() or not path.is_dir():
        return {}

    def _extract_date(name: str) -> int:
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", name)
        if not m:
            return 0
        return int(m.group(1)) * 10000 + int(m.group(2)) * 100 + int(m.group(3))

    pdfs = [f for f in path.iterdir() if f.is_file() and f.suffix.lower() == ".pdf"]

    dated: List[Path] = []
    plain: List[Path] = []

    for f in pdfs:
        if re.match(r"^\d{4}-\d{2}-\d{2}", f.stem):
            dated.append(f)
        else:
            plain.append(f)

    dated.sort(key=lambda p: _extract_date(p.stem), reverse=True)
    pdfs_sorted = dated + sorted(plain, key=lambda x: x.name.lower())

    if pdfs_sorted:
        node["_files"] = [(format_filename(f.name), str(f)) for f in pdfs_sorted]

    for d in sorted([d for d in path.iterdir() if d.is_dir()]):
        if max_depth is not None and depth + 1 > max_depth:
            continue
        child = build_tree(d, depth + 1, max_depth)
        if child:
            node[d.name] = child

    return node


@maybe_beartype
def generate_html(node: Dict[str, Any], level: int = 2, indent: int = 0) -> str:
    html_lines: List[str] = []
    space = "    " * indent
    sorted_keys = sorted(
        node.keys(),
        key=lambda k: (SECTION_ORDER.index(k) if k in SECTION_ORDER else 1000, k.lower()),
    )
    for key in sorted_keys:
        if key == "_files":
            for name, path in node["_files"]:
                rel = os.path.relpath(path, ".")
                tag = f"h{min(level,4)}"
                html_lines.append(f'{space}<{tag}><a href="./{rel}" target="_blank">{name}</a></{tag}>')
        else:
            tag = f"h{min(level,4)}"
            if level == 2:
                section_id = key.lower()
                html_lines.append(f'{space}<section id="{section_id}">')
            html_lines.append(f'{space}<{tag}>{key}</{tag}>')
            html_lines.append(generate_html(node[key], level + 1, indent + 1))
            if level == 2:
                html_lines.append(f'{space}</section>')
    return "\n".join(html_lines)


@maybe_beartype
def update_index_html(
    index_path: Path = INDEX_HTML_PATH,
    output_dir: Path = OUTPUT_DIR,
    section_order: List[str] = SECTION_ORDER,
) -> None:
    if not index_path.exists():
        logger.error("index.html not found")
        return

    html_text = index_path.read_text(encoding="utf-8")

    start_idx = html_text.find('<section id="contatti"')
    if start_idx == -1:
        contatti_html = ""
    else:
        end_idx = html_text.find('</section>', start_idx) + len('</section>')
        contatti_html = html_text[start_idx:end_idx]
        html_text = html_text[:start_idx] + html_text[end_idx:]

    tree = build_tree(output_dir)
    generated_html = generate_html(tree)

    nav_pattern = re.compile(r'<ul id="nav-navigation">(.*?)</ul>', re.DOTALL)
    match = nav_pattern.search(html_text)
    if match:
        new_nav = ""
        for sec in section_order + ["Contatti"]:
            folder_exists = sec.lower() in (k.lower() for k in tree.keys())
            li = f'<li><a href="#{sec.lower()}">{sec}</a></li>'

            # Keep visible only sections that actually exist, keep Contatti always visible
            if sec == "Contatti" or folder_exists:
                new_nav += f"{li}\n"
            else:
                new_nav += f"<!-- {li} -->\n"
        html_text = html_text[:match.start(1)] + new_nav + html_text[match.end(1):]

    copyright_line = '<p id="copyright">Copyright© 2025 by NullPointers Group - All rights reserved</p>'
    main_start = html_text.find('<main>')
    main_end = html_text.find('</main>', main_start) + len('</main>')
    new_main = f"<main>\n{generated_html}\n{contatti_html}\n{copyright_line}\n</main>"
    html_text = html_text[:main_start] + new_main + html_text[main_end:]

    index_path.write_text(html_text, encoding="utf-8")
    logger.info("index.html updated correctly")


if __name__ == "__main__":
    # Compila i .tex e aggiorna index.html
    compile_tex_to_pdf()
    update_index_html()
