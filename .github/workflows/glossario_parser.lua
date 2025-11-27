local INPUT_DIR = "src/RTB/Documenti Interni/Glossario/content/letters/"
local OUTPUT_FILE = "website/glossario/glossario.html"
local LETTERS = {
	"a",
	"b",
	"c",
	"d",
	"e",
	"f",
	"g",
	"h",
	"i",
	"j",
	"k",
	"l",
	"m",
	"n",
	"o",
	"p",
	"q",
	"r",
	"s",
	"t",
	"u",
	"v",
	"w",
	"x",
	"y",
	"z",
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

-- Converte funzioni latex e gestisce escaping HTML
local function convert_latex_to_html(text)
	text = text:gsub("\\textit%{([^}]+)%}", function(content)
		return "<i>" .. content .. "</i>"
	end)

	text = text:gsub("&", "&amp;")
	text = text:gsub("<([^i/])", "&lt;%1")
	text = text:gsub("<$", "&lt;")
	text = text:gsub("([^i])>", "%1&gt;")
	text = text:gsub("^>", "&gt;")
	text = text:gsub('"', "&quot;")
	text = text:gsub("'", "&#39;")

	return text
end

--Parsing dei termini dal contenuto del file .tex
local function parse_terms(content)
	local terms = {}

	--Trova il pattern \term{TERMINE}definizione
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

	--Sorting alfabetico dei termini di una singola lettera
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

	table.insert(
		html,
		[[        </nav>
				</header>
			
				<main>
				<a href="../../index.html" id="home">Home</a>

]]
	)

	-- Generazione sezioni per lettera
	for _, letter in ipairs(LETTERS) do
		local upper = letter:upper()
		table.insert(html, string.format('    <section id="%s">\n', letter))
		table.insert(html, string.format("	<h2>%s</h2>\n", upper))
		if all_terms[upper] then
			table.insert(html, string.format("	  <dl>\n"))

			for _, term_data in ipairs(all_terms[upper]) do
				table.insert(html, string.format("	      <dt>%s</dt>\n", convert_latex_to_html(term_data.term)))
				table.insert(html, string.format("	      <dd>%s</dd>\n\n", convert_latex_to_html(term_data.definition)))
			end
			table.insert(html, "        </dl>\n")
		end
		table.insert(html, "    </section>\n\n")
	end
	table.insert(
		html,
		[[
</body>
</html>]]
	)
	return table.concat(html)
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
				local upper = letter:upper()
				all_terms[upper] = terms
				tot_terms = tot_terms + #terms
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
