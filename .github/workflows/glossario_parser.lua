local function exists(path)
  local f = io.open(path, "r")
  if f then
    f:close()
    return true
  end
  return false
end

local INPUT_DIR

if exists("src/PB/Documenti Interni/Glossario/Glossario.tex") then
  INPUT_DIR = "src/PB/Documenti Interni/Glossario/content/letters/"
else
  INPUT_DIR = "src/RTB/Documenti Interni/Glossario/content/letters/"
end

local OUTPUT_FILE = "website/glossario/glossario.html"

local LETTERS = {
  "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
  "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z"
}

local function read_file(path)
  local file = io.open(path, "r")
  if not file then
    return nil
  end
  local content = file:read("*all")
  file:close()
  return content
end

local function write_file(path, content)
  local file = io.open(path, "w")
  if not file then
    error("Impossibile creare il file: " .. path)
  end
  file:write(content)
  file:close()
end

-- Helper per estrarre contenuto bilanciato tra graffe
local function extract_braced_content(str, start_pos)
    local balance = 1
    local i = start_pos
    while i <= #str and balance > 0 do
        local c = str:sub(i, i)
        if c == '{' then
            balance = balance + 1
        elseif c == '}' then
            balance = balance - 1
            if balance == 0 then
                return str:sub(start_pos, i - 1), i
            end
        end
        i = i + 1
    end
    return nil, start_pos
end

-- Converte comandi LaTeX (con graffe annidate) in HTML
local function convert_latex_to_html(text)
    local commands = {
        { latex = "\\textit", html_open = "<i>", html_close = "</i>" },
        { latex = "\\textbf", html_open = "<b>", html_close = "</b>" },
        { latex = "\\emph",   html_open = "<em>", html_close = "</em>" },
        { latex = "\\texttt", html_open = "<code>", html_close = "</code>" },
        { latex = "\\textsc", html_open = '<span class="smallcaps">', html_close = "</span>" },
    }

    for _, cmd in ipairs(commands) do
        local pos = 1
        while true do
            local start_idx = text:find(cmd.latex .. "{", pos, true)
            if not start_idx then break end
            local after_cmd = start_idx + #cmd.latex + 1 -- dopo '{'
            local content, end_brace = extract_braced_content(text, after_cmd)
            if content then
                local before = text:sub(1, start_idx - 1)
                local after = text:sub(end_brace + 1)
                -- Ricorsione sul contenuto per gestire comandi annidati
                local inner_html = convert_latex_to_html(content)
                text = before .. cmd.html_open .. inner_html .. cmd.html_close .. after
                pos = start_idx + #cmd.html_open + #inner_html + #cmd.html_close
            else
                pos = start_idx + 1
            end
        end
    end

    -- Altri comandi LaTeX personali
    text = text:gsub("\\vr%s*%{(.-)%}", "“%1”")
    text = text:gsub("\\vrs%s*%{(.-)%}", "‘%1’")
    text = text:gsub("&", "&amp;")
    text = text:gsub("<([^i/])", "&lt;%1")
    text = text:gsub("<$", "&lt;")
    text = text:gsub("([^i])>", "%1&gt;")
    text = text:gsub("^>", "&gt;")
    text = text:gsub('"', "&quot;")
    text = text:gsub("'", "&#39;")
    text = text:gsub("\\_", "&#95;")
    text = text:gsub("\\\\", "")

    return text
end

-- Parsing dei termini dal contenuto del file .tex
local function parse_terms(content)
  local terms = {}

  -- Trova il pattern \term{TERMINE}definizione
  for term, definition in content:gmatch("\\term%{([^}]+)%}%s*([^\n]+)") do
    term = term:match("^%s*(.-)%s*$")
    definition = definition:match("^%s*(.-)%s*$")

    if term ~= "" and definition ~= "" then
      table.insert(terms, {
        term = term,
        definition = definition,
      })
    end
  end

  -- Sorting alfabetico dei termini di una singola lettera
  table.sort(terms, function(a, b)
    return a.term:lower() < b.term:lower()
  end)
  return terms
end

local function generate_html(all_terms)
  local html = {
    [[
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Glossario</title>
    <link rel="icon" href="../images/logo.png" type="image/x-icon">
    <link rel="stylesheet" href="../styles.css">
    <link rel="stylesheet" href="glossario.css">
    <script src="../script.js" defer></script>
</head>
<body>
<header>
    <nav aria-label="Navigazione principale">
        <ul id="nav-navigation">
    ]],
  }

  -- Generazione navigazione lettere
  for _, letter in ipairs(LETTERS) do
    local upper = letter:upper()
    -- Se si deciderà di mettere tutte le lettere nella navbar allora basta commentare questo if qua
    if all_terms[upper] and #all_terms[upper] > 0 then
      table.insert(html, string.format('            <li><a href="#%s">%s</a></li>\n', letter, upper))
    end
  end

  table.insert(html, [[
        </ul>
    </nav>
</header>
<main>
    <a href="../../index.html" id="home">Home</a>
]])

  -- Generazione sezioni per lettera
  for _, letter in ipairs(LETTERS) do
    local upper = letter:upper()
    table.insert(html, string.format('    <section id="%s">\n', letter))
    table.insert(html, string.format("        <h2>%s</h2>\n", upper))
    if all_terms[upper] then
      table.insert(html, "        <dl>\n")
      for _, term_data in ipairs(all_terms[upper]) do
        table.insert(html, string.format("            <dt>%s</dt>\n", convert_latex_to_html(term_data.term)))
        table.insert(html, string.format("            <dd>%s</dd>\n\n", convert_latex_to_html(term_data.definition)))
      end
      table.insert(html, "        </dl>\n")
    end
    table.insert(html, "    </section>\n\n")
  end

  table.insert(html, [[
</main>
</body>
</html>]])

  return table.concat(html)
end

local function write_terms_file(path, terms, letter)
  local file = io.open(path, "w")
  if not file then
    error("Impossibile riscrivere il file: " .. path)
  end

  local upper = letter:upper()
  file:write(string.format("\\begin{center}\n\\section*{%s}\n\\end{center}\n", upper))
  file:write(string.format("\\addcontentsline{toc}{section}{%s}\n\n", upper))

  for _, t in ipairs(terms) do
    file:write(string.format("\\term{%s}\n%s\n\n", t.term, t.definition))
  end

  print(string.format("Sto scrivendo in %s", path))
  file:close()
end

local function main()
  local all_terms = {}
  local tot_terms = 0

  for _, letter in ipairs(LETTERS) do
    local filename = string.format("%s/%s.tex", INPUT_DIR, letter)
    local content = read_file(filename)

    if content then
      local terms = parse_terms(content)
      if #terms > 0 then
        write_terms_file(filename, terms, letter)
        local upper = letter:upper()
        all_terms[upper] = terms
        tot_terms = tot_terms + #terms
      else
        print(string.format("0 termini in %s.tex", letter))
      end
    end
  end

  if tot_terms == 0 then
    print("Nessun termine trovato")
    return
  end

  print("Parsing terminato")
  local html_content = generate_html(all_terms)
  write_file(OUTPUT_FILE, html_content)
end

main()