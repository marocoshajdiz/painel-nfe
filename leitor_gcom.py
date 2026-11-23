"""Lê o 'Consolidado de Venda' exportado pelo GCOM (HTML salvo como .xls)."""
import re
from bs4 import BeautifulSoup


def _num(txt):
    txt = (txt or "").strip()
    if not re.fullmatch(r"-?[\d.]+,\d+|-?\d+", txt):
        return None
    return float(txt.replace(".", "").replace(",", "."))


def _grade(tabela):
    """Monta a grade da tabela respeitando colspan/rowspan."""
    grade, ocupado = [], {}
    for r, tr in enumerate(tabela.find_all("tr")):
        linha, c = [], 0
        for td in tr.find_all(["td", "th"], recursive=False):
            while (r, c) in ocupado:
                linha.append(ocupado[(r, c)]); c += 1
            txt = " ".join(td.get_text(" ", strip=True).split())
            cs, rs = int(td.get("colspan", 1) or 1), int(td.get("rowspan", 1) or 1)
            for dc in range(cs):
                linha.append(txt)
                for dr in range(1, rs):
                    ocupado[(r + dr, c + dc)] = txt
            c += cs
        while (r, c) in ocupado:
            linha.append(ocupado[(r, c)]); c += 1
        grade.append(linha)
    return grade


def ler_consolidado(conteudo):
    if isinstance(conteudo, bytes):
        try:
            texto = conteudo.decode("utf-8")
        except UnicodeDecodeError:
            texto = conteudo.decode("latin-1")
    else:
        texto = conteudo
    soup = BeautifulSoup(texto, "html.parser")
    alvo = next((t for t in soup.find_all("table")
                 if "BALC" in t.get_text() and "TOTAL GERAL" in t.get_text()), None)
    if alvo is None:
        raise ValueError("Não encontrei a tabela do Consolidado de Venda (colunas BALCÃO / TOTAL GERAL).")
    grade = _grade(alvo)
    cab1, cab2 = grade[0], grade[1]
    colunas = [f"{a} | {b}" if a != b else a for a, b in zip(cab1, cab2)]
    marca = re.search(r"MARCA:\s*(.+?)\s+CONSOLIDADO DE VENDA", soup.get_text(" "))
    periodo = re.search(r"PER[IÍ]ODO:\s*(\d{2}/\d{2}/\d{4})\s*[ÀA]:?\s*(\d{2}/\d{2}/\d{4})", soup.get_text(" "))
    return colunas, grade[2:], (periodo.groups() if periodo else (None, None)), (marca.group(1).strip() if marca else None)
