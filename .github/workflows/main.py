import os
import re
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

INDEX_HTML_PATH = Path("index.html")
SRC_DIR = Path("src")
OUTPUT_DIR = Path("output")
SECTION_ORDER = ["RTB", "PB", "Candidatura", "Diario Di Bordo"]
MAX_DEPTH = 2

MONTH_IT = {
    1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile",
    5: "Maggio", 6: "Giugno", 7: "Luglio", 8: "Agosto",
    9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre"
}

def format_filename(filename):
    name, ext = os.path.splitext(filename)
    parts = name.split("_")
    first = parts[0]

    # caso con data YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", first):
        date = first  # mantieni trattini

        # file che contengono "VE" nel nome → Verbale Esterno
        if "est" in name.lower():
            return f"{date}_VE"

        # file che contengono "VI" nel nome → Verbale Interno
        if "int" in name.lower():
            return f"{date}_VI"

        # nessuna etichetta → solo data
        return date

    # nessuna data → restituisci nome base
    return name



def clear_output_folder():
    if OUTPUT_DIR.exists() and OUTPUT_DIR.is_dir():
        shutil.rmtree(OUTPUT_DIR)

def cleanup_source_pdf():
    for root, dirs, files in os.walk(SRC_DIR):
        for file in files:
            if file.endswith((".pdf", ".log", ".aux", ".fls", ".out", ".fdb_latexmk", ".synctex.gz", ".toc")):
                try:
                    os.remove(os.path.join(root, file))
                except:
                    pass

def compile_tex_to_pdf():
    clear_output_folder()

    if not OUTPUT_DIR.exists():
        OUTPUT_DIR.mkdir(parents=True)

    tex_files = []
    for tex_path in SRC_DIR.rglob("*.tex"):
        try:
            with open(tex_path, "r", encoding="utf-8", errors="ignore") as f:
                if "\\documentclass" in f.read(1024):
                    tex_files.append(tex_path)
        except:
            continue

    for tex_file in tex_files:
        tex_dir = tex_file.parent
        tex_name = tex_file.name
        try:
            subprocess.run(
                ["latexmk", "-pdf", "-interaction=nonstopmode", "-f", tex_name],
                cwd=str(tex_dir),
                capture_output=True,
                text=True,
                timeout=60
            )
            pdf_name = tex_file.stem + ".pdf"
            pdf_path = tex_dir / pdf_name
            if pdf_path.exists():
                relative_parts = tex_dir.relative_to(SRC_DIR).parts
                if len(relative_parts) > MAX_DEPTH:
                    relative_parts = relative_parts[:MAX_DEPTH]
                output_dir = OUTPUT_DIR.joinpath(*relative_parts)
                output_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(pdf_path, output_dir / pdf_name)
        except Exception as e:
            print(f"Error processing {tex_file}: {e}")
            continue

    cleanup_source_pdf()

def build_tree(path: Path, depth=0, max_depth=MAX_DEPTH):
    node = {}
    if not path.exists() or not path.is_dir():
        return {}
    
    def _extract_date(path):
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", path.name)
        if not m:
            return 0
        return int(m.group(1)) * 10000 + int(m.group(2)) * 100 + int(m.group(3))

    pdfs = [f for f in path.iterdir() if f.is_file() and f.suffix.lower() == ".pdf"]

    # separa file datati da non-datati
    dated = []
    plain = []

    for f in pdfs:
        if re.match(r"^\d{4}-\d{2}-\d{2}", f.stem):
            dated.append(f)
        else:
            plain.append(f)

    # ordina solo i datati in ordine decrescente
    dated.sort(key=_extract_date, reverse=True)

    # ricompone: prima i datati (recenti→vecchi), poi gli altri mantenendo ordine originale
    pdfs = dated + sorted(plain, key=lambda x: x.name.lower())


    if pdfs:
        node["_files"] = [(format_filename(f.name), str(f)) for f in pdfs]

    for d in sorted([d for d in path.iterdir() if d.is_dir()]):
        if max_depth is not None and depth + 1 > max_depth:
            continue
        child = build_tree(d, depth + 1, max_depth)
        if child:
            node[d.name] = child

    return node

def generate_html(node, level=2, indent=0):
    html = []
    space = "    " * indent
    for key in sorted(node.keys(), key=lambda k: (SECTION_ORDER.index(k) if k in SECTION_ORDER else 1000, k.lower())):
        if key == "_files":
            for name, path in node["_files"]:
                rel = os.path.relpath(path, ".")
                tag = f"h{min(level, 4)}"
                html.append(f'{space}<{tag}><a href="./{rel}" target="_blank">{name}</a></{tag}>')
        else:
            tag = f"h{min(level, 4)}"
            section_id = key.lower() if level == 2 else None
            if level == 2:
                html.append(f'{space}<section id="{section_id}">')
            html.append(f'{space}<{tag}>{key}</{tag}>')
            html.append(generate_html(node[key], level + 1, indent + 1))
            if level == 2:
                html.append(f'{space}</section>')
    return "\n".join(html)

def update_index_html():
    if not INDEX_HTML_PATH.exists():
        print("index.html not found")
        return

    html_text = INDEX_HTML_PATH.read_text(encoding="utf-8")

    # Preserve Contatti
    start_idx = html_text.find('<section id="contatti"')
    if start_idx == -1:
        contatti_html = ""
    else:
        end_idx = html_text.find('</section>', start_idx) + len('</section>')
        contatti_html = html_text[start_idx:end_idx]
        html_text = html_text[:start_idx] + html_text[end_idx:]

    tree = build_tree(OUTPUT_DIR)
    generated_html = generate_html(tree)

    # Ensure nav <li> for all sections
    nav_pattern = re.compile(r'<ul id="nav-navigation">(.*?)</ul>', re.DOTALL)
    match = nav_pattern.search(html_text)
    if match:
        nav_content = match.group(1)
        new_nav = ""
        for sec in SECTION_ORDER + ["Contatti"]:
            folder_exists = sec.lower() in (k.lower() for k in tree.keys())
            li = f'<li><a href="#{sec.lower()}">{sec}</a></li>'
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

    INDEX_HTML_PATH.write_text(html_text, encoding="utf-8")
    print("index.html updated correctly")

if __name__ == "__main__":
    compile_tex_to_pdf()
    update_index_html()
