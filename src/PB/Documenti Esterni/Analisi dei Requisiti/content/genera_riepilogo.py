import re
from collections import defaultdict

# ============================================================
# CONFIGURAZIONE - cambia questi se Qualità/Vincolo cambiano
# (non vengono da funzionali.tex quindi li mettiamo a mano)
QUALITA_OB  = 5
QUALITA_DE  = 0
QUALITA_OP  = 0
VINCOLO_OB  = 8
VINCOLO_DE  = 0
VINCOLO_OP  = 0
# ============================================================

with open('funzionali.tex', 'r', encoding='utf-8') as f:
    content = f.read()

# uc_label -> lista ordinata di (req_code_latex, anchor), senza duplicati
uc_to_reqs      = defaultdict(list)
uc_to_reqs_seen = defaultdict(set)
req_max = {'OB': 0, 'DE': 0, 'OP': 0}

# Matcha righe tipo:
#   RF-OB\_01 \hypertarget{rf-ob_1} & descrizione & \hyperref[uc_xx]{...} \\
row_pattern = re.compile(
    r'RF-(OB|DE|OP)\\_(\d+)\s*\\hypertarget\{([^}]+)\}(.*?)\\\\',
    re.DOTALL
)

for match in row_pattern.finditer(content):
    req_type    = match.group(1)          # OB / DE / OP
    req_num_str = match.group(2)          # "01", "02", ...
    req_num     = int(req_num_str)
    anchor      = match.group(3)          # rf-ob_1
    rest        = match.group(4)          # & descrizione & UC refs

    req_code = f'RF-{req_type}\\_{req_num_str}'   # RF-OB\_01

    if req_num > req_max[req_type]:
        req_max[req_type] = req_num

    # L'ultima cella (dopo l'ultimo &) contiene i riferimenti ai UC
    cells    = rest.split('&')
    uc_cell  = cells[-1] if len(cells) >= 2 else ''

    # Estrai tutti i \hyperref[uc_xx.xx]{...}
    uc_labels = re.findall(r'\\hyperref\[([^\]]+)\]', uc_cell)

    for uc_label in uc_labels:
        key = (req_code, anchor)
        if key not in uc_to_reqs_seen[uc_label]:
            uc_to_reqs_seen[uc_label].add(key)
            uc_to_reqs[uc_label].append((req_code, anchor))


# ---- Ordinamento naturale dei UC (uc_01 < uc_01.1 < uc_01.1.1 < uc_02 ...) ----
def uc_sort_key(uc):
    parts = re.sub(r'^uc_', '', uc).split('.')
    return [int(p) for p in parts]

sorted_ucs = sorted(uc_to_reqs.keys(), key=uc_sort_key)


# ---- Costruzione righe della tabella di tracciamento ----
rows = []
for uc in sorted_ucs:
    reqs     = uc_to_reqs[uc]
    uc_num   = uc.replace('uc_', '')
    uc_disp  = f'UC\\_{uc_num}'

    req_parts = [f'\\hyperlink{{{anchor}}}{{{code}}}' for code, anchor in reqs]
    req_str   = ', '.join(req_parts)

    rows.append(
        f'    \\hyperref[{uc}]{{{uc_disp}}} & {req_str} \\\\\n    \\hline'
    )

tracking_content = '\n'.join(rows)

ob_count = req_max['OB']
de_count = req_max['DE']
op_count = req_max['OP']


# ---- Output finale ----
output = r"""\subsection{Tracciamento dei Casi d'Uso e Riepilogo}
\renewcommand{\arraystretch}{1.2}
\begin{longtable}{|
        >{\raggedright\arraybackslash}p{0.2\columnwidth} |
        >{\raggedright\arraybackslash}p{0.7\columnwidth} |
    }
    \hline
    \rowcolor[gray]{0.9}
    \textbf{Caso d'Uso$^G$} & \textbf{Requisiti} \\
    \hline
    \endfirsthead
    \hline
    \rowcolor[gray]{0.9}
    \textbf{Caso d'Uso$^G$} & \textbf{Requisiti} \\
    \hline
    \endhead
    % --- CONTENUTO ---
""" + tracking_content + r"""
    \caption{Tracciamento dei Requisiti Funzionali}
    \label{tab:tracciamento}
\end{longtable}
\subsection{Riepilogo dei Requisiti}
\renewcommand{\arraystretch}{1.2}
\begin{longtable}{| c | c | c | c |}
	\hline
	\rowcolor[gray]{0.9}
	\textbf{Tipologia} & \textbf{Obbligatori} & \textbf{Desiderabili} & \textbf{Opzionali} \\
	\hline
	\endfirsthead

	\hline
	\rowcolor[gray]{0.9}
	\textbf{Tipologia} & \textbf{Obbligatori} & \textbf{Desiderabili} & \textbf{Opzionali} \\
	\hline
	\endhead

	\hline
""" + f"""\t\\textbf{{Funzionali}} & {ob_count} & {de_count} & {op_count} \\\\
\t\\hline
\t\\textbf{{Qualità}} & {QUALITA_OB} & {QUALITA_DE} & {QUALITA_OP} \\\\
\t\\hline
\t\\textbf{{Vincolo}} & {VINCOLO_OB} & {VINCOLO_DE} & {VINCOLO_OP} \\\\
\t\\hline
""" + r"""
	\caption{Riepilogo dei Requisiti}
	\label{tab:riepilogo}

\end{longtable}
"""

with open('riepilogo.tex', 'w', encoding='utf-8') as f:
    f.write(output)

print(f"✅ riepilogo.tex generato con successo!")
print(f"   UC trovati:  {len(sorted_ucs)}")
print(f"   RF-OB: {ob_count}  |  RF-DE: {de_count}  |  RF-OP: {op_count}")
