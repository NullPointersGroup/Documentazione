import os
import re
import sys
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

# Configuration
INDEX_HTML_PATH = Path("index.html")
SRC_DIR = Path("src")
OUTPUT_DIR = Path("output")
SECTION_ORDER = ["PB", "RTB", "Candidatura", "Diario Di Bordo"]
MAX_DEPTH = 2

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def cleanup_source_pdf(src_dir: Path = SRC_DIR) -> None:
    """Rimuove file generati temporanei nella sorgente (.pdf, .log, .aux, ...)."""
    patterns = (".pdf", ".lof", ".lot", ".log", ".aux", ".fls", ".out", ".fdb_latexmk", ".synctex.gz", ".toc", ".snm", ".nav")
    for root, _dirs, files in os.walk(src_dir):
        for file in files:
            if file.endswith(patterns):
                try:
                    os.remove(os.path.join(root, file))
                except Exception:
                    logger.debug(f"Could not remove {os.path.join(root, file)}")

def compile_tex_to_pdf(
    src_dir: Path = SRC_DIR,
    output_dir: Path = OUTPUT_DIR,
    max_depth: Optional[int] = MAX_DEPTH,
    latexmk_cmd: str = "latexmk",
) -> Dict[Path, str]:
    #Compila i .tex e copia i PDF in output, restituendo una mappa PDF -> table.tex
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
            raise RuntimeError(f"Skipped unreadable tex file: {tex_path}")

    pdf_to_tex_content: Dict[Path, str] = {}

    for tex_file in tex_files:
        tex_dir = tex_file.parent
        tex_name = tex_file.name
        try:
            logger.info(f"Compiling {tex_file}...")
            res = subprocess.run(
                [latexmk_cmd, "-pdf", "-interaction=nonstopmode", "-f", tex_name],
                cwd=str(tex_dir),
                capture_output=True,
                text=True,
                encoding='latin-1',
            )

            if res.returncode != 0:
                logger.warning(f"latexmk failed for {tex_file}: {res.stderr.strip()}")
                raise RuntimeError(f"latexmk failed for {tex_file}: {res.stderr.strip()}")

            pdf_name = tex_file.stem + ".pdf"
            pdf_path = tex_dir / pdf_name
            if pdf_path.exists():
                relative_parts = tex_dir.relative_to(src_dir).parts if tex_dir != src_dir else ()
                if max_depth is not None and len(relative_parts) > max_depth:
                    relative_parts = relative_parts[:max_depth]
                dest_dir = output_dir.joinpath(*relative_parts)
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_pdf_path = dest_dir / pdf_name
                shutil.copy2(pdf_path, dest_pdf_path)

                # Legge il contenuto del table.tex relativo
                table_tex_path = tex_dir / "content/table.tex"
                tex_content = ""
                if table_tex_path.exists():
                    with open(table_tex_path, "r", encoding="utf-8", errors="ignore") as tf:
                        tex_content = tf.read()

                pdf_to_tex_content[dest_pdf_path] = tex_content
                
        except Exception as e:
            logger.exception(f"Error processing {tex_file}: {e}")
            raise RuntimeError(f"Error processing {tex_file}: {e}")

    cleanup_source_pdf(src_dir)

    return pdf_to_tex_content

def format_filename(filename: str, tex_content: str = "") -> str:
    """
    Format del nome file con prefissi e versione.

    - Se il nome inizia con YYYY-MM-DD: mantiene la data come prefisso
    - Aggiunge _VE se contiene "est" (verbale esterno), _VI se contiene "int" (verbale interno), _DB se contiene "diario"
    - Aggiunge la versione se disponibile in tex_content e non è un diario
    """
    name = os.path.splitext(filename)[0]
    parts = name.split("_")
    first = parts[0]

    versione = None
    if tex_content and not re.search(r"diario", name, re.IGNORECASE):
        match = re.search(r"Versione\s*&\s*([\d\.]+)\s*\\\\", tex_content)
        if match:
            versione = match.group(1)
    v = f" v{versione}" if versione else ""

    if re.match(r"^\d{4}-\d{2}-\d{2}$", first):
        date = first
        lower_name = name.lower()
        if "est" in lower_name:
            return f"{date}_VE{v}"
        if "int" in lower_name:
            return f"{date}_VI{v}"
        if "diario" in lower_name:
            return f"{date}_DB"
        return date

    return name.replace("_", " ") + v

def build_tree(
    path: Path,
    pdf_to_tex_content: Optional[Dict[Path, str]] = None,
    depth: int = 0,
    max_depth: Optional[int] = MAX_DEPTH
) -> Dict[str, Any]:
    node: Dict[str, Any] = {}
    if pdf_to_tex_content is None:
        pdf_to_tex_content = {}

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
        files_with_versions = []
        for f in pdfs_sorted:
            tex_content = pdf_to_tex_content.get(f, "")
            files_with_versions.append((format_filename(f.name, tex_content), str(f)))
        node["_files"] = files_with_versions

    for d in sorted([d for d in path.iterdir() if d.is_dir()]):
        if max_depth is not None and depth + 1 > max_depth:
            continue
        child = build_tree(d, pdf_to_tex_content, depth + 1, max_depth)
        if child:
            node[d.name] = child

    return node

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
                section_id = key.lower().split()[0]
                html_lines.append(f'{space}<section id="{section_id}">')
            html_lines.append(f'{space}<{tag}>{key}</{tag}>')
            html_lines.append(generate_html(node[key], level + 1, indent + 1))
            if level == 2:
                html_lines.append(f'{space}</section>')
    return "\n".join(html_lines)

def update_index_html(
    index_path: Path = INDEX_HTML_PATH,
    output_dir: Path = OUTPUT_DIR,
    section_order: List[str] = SECTION_ORDER,
    pdf_to_tex_content: Optional[Dict[Path, str]] = None,
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

    tree = build_tree(output_dir, pdf_to_tex_content)
    generated_html = generate_html(tree)

    nav_pattern = re.compile(r'<ul id="nav-navigation">(.*?)</ul>', re.DOTALL)
    match = nav_pattern.search(html_text)
    if match:
        new_nav = ""
        for sec in section_order + ["Contatti"]:
            folder_exists = sec.lower() in (k.lower() for k in tree.keys())
            section_id = sec.lower().split()[0]
            li = f'<li><a href="#{section_id}">{sec}</a></li>'

            # Keep visible only sections that actually exist, keep Contatti always visible
            if sec == "Contatti" or folder_exists:
                new_nav += f"{li}\n"
            else:
                new_nav += f"<!-- {li} -->\n"
        html_text = html_text[:match.start(1)] + new_nav + html_text[match.end(1):]

    copyright_line = '<p id="copyright">Copyright© 2025 by NullPointers Group - All rights reserved</p>'
    main_start = html_text.find('<main>')
    main_end = html_text.find('</main>', main_start) + len('</main>')
    new_main = f'<main>\n<a href="website/glossario/glossario.html" id="glossario">Glossario</a>\n{generated_html}\n{contatti_html}\n{copyright_line}\n</main>'
    html_text = html_text[:main_start] + new_main + html_text[main_end:]

    index_path.write_text(html_text, encoding="utf-8")
    logger.info("index.html updated correctly")


def main() -> None:
    pdf_to_tex_content = compile_tex_to_pdf()
    update_index_html(pdf_to_tex_content=pdf_to_tex_content)


try:
    main()
except Exception as e:
    logger.debug(f"Errore durante la compilazione: {e}")
    sys.exit(1)