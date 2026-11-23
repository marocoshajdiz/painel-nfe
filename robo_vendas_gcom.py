"""Robô que busca no GCOM o faturamento de Balcão e Delivery e lança na DRE do Painel.

Roda pelo GitHub Actions (.github/workflows/vendas_gcom.yml). Usa um usuário do GCOM
com acesso apenas ao Consolidado de Venda.

Segredos (GitHub > Settings > Secrets and variables > Actions):
  GCOM_EMPRESA, GCOM_USUARIO, GCOM_SENHA   login do usuário só de consulta
  DATABASE_URL                             mesma URL do Supabase do Streamlit
  EMAIL_REMETENTE, EMAIL_SENHA_APP         Gmail usado para avisar o gerente se der erro
Opcional:
  MES_GCOM=AAAA-MM                         importa um mês específico (ex.: 2026-10)

SEGURANÇA: o repositório é público e os logs do GitHub ficam visíveis.
Por isso o robô NUNCA escreve valores, senhas ou e-mails no log.
Diagnósticos (prints de tela) vão só para o e-mail do gerente.
"""
import calendar
import json
import os
import re
import smtplib
import sys
import traceback
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import psycopg2
from playwright.sync_api import sync_playwright

from leitor_gcom import _num, ler_consolidado

FUSO = ZoneInfo("America/Sao_Paulo")
URL_LOGIN = "https://www2.gcom.com.br/Cloud/Home/Login.aspx"
URL_RELATORIO = "https://www2.gcom.com.br/gcom2/VENDAS/RELATORIOCONSOLIDADOVENDA.ASP"

# Marcas somadas no faturamento da loja (GIUSTO fica de fora).
MARCAS = ("SPOLETO", "RISOTOS DO SPOLETO", "SALADAS DO SPOLETO")
# Canais do GCOM usados em cada linha da DRE.
CANAIS_BALCAO = ("BALCÃO",)
CANAIS_IFOOD = ("TAKEAWAY INTEGRADO",)  # no GCOM, o iFood aparece como Takeaway integrado


def log(msg):
    # Só mensagens genéricas: o log do GitHub é público.
    print(f"[{datetime.now(FUSO):%H:%M:%S}] {msg}", flush=True)


# ----------------------------------------------------------------- leitura
def somar_canais(colunas, linhas):
    total = next((l for l in linhas if l and str(l[0]).upper().startswith("TOTAL")), None)
    if total is None:
        raise ValueError("Linha TOTAL GERAL não encontrada no relatório.")
    valores = {}
    for nome, celula in zip(colunas, total):
        if " | " in nome:
            canal, sub = nome.split(" | ", 1)
            if sub.startswith("VALOR"):
                valores[canal] = _num(celula) or 0.0
    if "BALCÃO" not in valores:
        raise ValueError("Coluna BALCÃO não encontrada; o layout do relatório mudou.")
    balcao = round(sum(valores.get(c, 0.0) for c in CANAIS_BALCAO), 2)
    ifood = round(sum(valores.get(c, 0.0) for c in CANAIS_IFOOD), 2)
    outros = round(sum(v for c, v in valores.items() if c not in CANAIS_BALCAO + CANAIS_IFOOD), 2)
    return balcao, ifood, outros


# ----------------------------------------------------------------- navegador
def _quadros(page):
    return [page.main_frame] + [f for f in page.frames if f != page.main_frame]


def _quadro_com_texto(page, texto, tempo=20000):
    fim = datetime.now() + timedelta(milliseconds=tempo)
    while datetime.now() < fim:
        for quadro in _quadros(page):
            try:
                if quadro.locator(f"text={texto}").count():
                    return quadro
            except Exception:
                pass
        page.wait_for_timeout(500)
    return None


def fazer_login(page):
    log("Abrindo a tela de login do GCOM.")
    page.goto(URL_LOGIN, wait_until="domcontentloaded", timeout=60000)
    campos = page.locator("input:visible:not([type=password]):not([type=submit])"
                          ":not([type=button]):not([type=hidden]):not([type=checkbox])")
    if campos.count() < 2:
        raise RuntimeError("Campos de Empresa/Usuário não encontrados na tela de login.")
    campos.nth(0).fill(os.environ["GCOM_EMPRESA"])
    campos.nth(1).fill(os.environ["GCOM_USUARIO"])
    page.locator("input[type=password]:visible").first.fill(os.environ["GCOM_SENHA"])
    botao = page.locator("input[type=submit]:visible, button:visible, input[type=button]:visible").filter(
        has_text=re.compile("login|entrar", re.I))
    if botao.count():
        botao.first.click()
    else:
        page.locator("input[value*='ogin' i]:visible").first.click()
    try:
        page.wait_for_url(lambda u: "login.aspx" not in u.lower(), timeout=45000)
    except Exception:
        raise RuntimeError("O GCOM não aceitou o login (empresa, usuário ou senha) ou pediu verificação extra.")
    page.wait_for_load_state("networkidle", timeout=60000)
    log("Login realizado.")


def abrir_relatorio(page):
    log("Abrindo o Consolidado de Venda.")
    page.goto(URL_RELATORIO, wait_until="domcontentloaded", timeout=60000)
    quadro = _quadro_com_texto(page, "Período de", 20000)
    if quadro is None:
        # Plano B: abrir pelo endereço do novo ERP, que carrega a página dentro de um quadro.
        page.goto("https://www2.gcom.com.br/novoerp/#/novoerp/aspview/" + URL_RELATORIO.replace(":", "%3A").replace("/", "%2F"),
                  wait_until="domcontentloaded", timeout=60000)
        quadro = _quadro_com_texto(page, "Período de", 40000)
    if quadro is None:
        raise RuntimeError("A tela do Consolidado de Venda não abriu (sem acesso ou endereço mudou).")
    return quadro


def preencher_periodo(quadro, inicio, fim):
    # Acha os dois campos de data logo depois do texto "Período de:".
    ok = quadro.evaluate("""([ini, fim]) => {
        const andar = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let rotulo = null;
        while (andar.nextNode()) { if (/Per[ií]odo de/i.test(andar.currentNode.nodeValue)) { rotulo = andar.currentNode; break; } }
        if (!rotulo) return false;
        const campos = [...document.querySelectorAll('input')].filter(i =>
            (!i.type || i.type === 'text') &&
            (rotulo.compareDocumentPosition(i) & Node.DOCUMENT_POSITION_FOLLOWING));
        if (campos.length < 2) return false;
        for (const [campo, valor] of [[campos[0], ini], [campos[1], fim]]) {
            campo.focus(); campo.value = valor;
            campo.dispatchEvent(new Event('input', {bubbles: true}));
            campo.dispatchEvent(new Event('change', {bubbles: true}));
            campo.dispatchEvent(new Event('blur', {bubbles: true}));
        }
        return true;
    }""", [inicio.strftime("%d%m%Y"), fim.strftime("%d%m%Y")])
    if not ok:
        raise RuntimeError("Campos de período não encontrados no relatório.")


def selecionar_marca(page, quadro, marca):
    """Escolhe a Marca Empresarial e marca as unidades próprias."""
    seletor = None
    for sel in quadro.locator("select").all():
        rotulos = [o.strip().upper() for o in sel.locator("option").all_inner_texts()]
        if marca in rotulos:
            seletor = sel
            break
    if seletor is None:
        raise RuntimeError(f"A marca {marca} não aparece na lista de Marca Empresarial.")
    seletor.select_option(label=next(o for o in seletor.locator("option").all_inner_texts() if o.strip().upper() == marca))
    page.wait_for_timeout(1500)
    try:
        page.wait_for_load_state("networkidle", timeout=30000)
    except Exception:
        pass
    quadro = _quadro_com_texto(page, "Período de", 30000) or quadro
    # Marca a caixa "Unidades Próprias", que seleciona as lojas da empresa.
    quadro.evaluate("""() => {
        const andar = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        while (andar.nextNode()) {
            if (/Unidades Pr[óo]prias/i.test(andar.currentNode.nodeValue)) {
                const caixa = [...document.querySelectorAll('input[type=checkbox]')].find(c =>
                    andar.currentNode.compareDocumentPosition(c) & Node.DOCUMENT_POSITION_FOLLOWING);
                if (caixa && !caixa.checked) caixa.click();
                break;
            }
        }
    }""")
    page.wait_for_timeout(2500)
    try:
        page.wait_for_load_state("networkidle", timeout=30000)
    except Exception:
        pass
    return _quadro_com_texto(page, "Período de", 30000) or quadro


def gerar_excel(page, quadro):
    botao = quadro.locator("text=Gerar Excel").first
    try:
        with page.expect_download(timeout=120000) as baixado:
            botao.click()
        return open(baixado.value.path(), "rb").read()
    except Exception:
        # Alguns sistemas abrem o "Excel" numa aba nova em vez de baixar.
        for outra in page.context.pages:
            if outra != page and "CONSOLIDADO" in (outra.content() or "").upper():
                conteudo = outra.content().encode("utf-8")
                outra.close()
                return conteudo
        raise RuntimeError("O GCOM não entregou o arquivo Excel do relatório.")


def buscar_relatorios(inicio, fim, diagnostico):
    """Entra uma vez e gera o relatório de cada marca. Retorna {marca: conteúdo}."""
    resultado = {}
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        contexto = navegador.new_context(accept_downloads=True, locale="pt-BR",
                                         viewport={"width": 1366, "height": 900})
        page = contexto.new_page()
        try:
            fazer_login(page)
            for marca in MARCAS:
                diagnostico["etapa"] = f"marca {marca}"
                log(f"Gerando o relatório da marca {MARCAS.index(marca) + 1} de {len(MARCAS)}.")
                quadro = abrir_relatorio(page)
                quadro = selecionar_marca(page, quadro, marca)
                preencher_periodo(quadro, inicio, fim)
                resultado[marca] = gerar_excel(page, quadro)
            return resultado
        except Exception:
            try:
                diagnostico["print"] = page.screenshot(full_page=True)
                campos = []
                for q in _quadros(page):
                    for c in q.locator("input, select, button").all()[:80]:
                        tipo = c.get_attribute("type") or ""
                        valor = "***" if tipo == "password" else (c.get_attribute("value") or "")[:30]
                        campos.append(f"{q.url[:90]} | {c.evaluate('e => e.tagName')} name={c.get_attribute('name')} "
                                      f"id={c.get_attribute('id')} type={tipo} value={valor}")
                diagnostico["campos"] = "\n".join(campos)
                diagnostico["url"] = page.url
            except Exception:
                pass
            raise
        finally:
            navegador.close()


# ----------------------------------------------------------------- banco
def lancar_na_dre(mes, balcao, delivery, inicio, fim, detalhe):
    with psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=15, sslmode="require") as conn:
        with conn.cursor() as cur:
            for conta, valor in (("Faturamento Balcão", balcao), ("Faturamento Delivery", delivery)):
                cur.execute("""INSERT INTO ajustes_dre (mes_referencia, conta, valor) VALUES (%s,%s,%s)
                               ON CONFLICT (mes_referencia, conta) DO UPDATE SET valor=EXCLUDED.valor""",
                            (mes, conta, valor))
            cur.execute("""CREATE TABLE IF NOT EXISTS importacoes_gcom (
                mes_referencia TEXT PRIMARY KEY, periodo_inicio DATE, periodo_fim DATE,
                balcao NUMERIC(14,2), delivery NUMERIC(14,2), atualizado_em TIMESTAMPTZ DEFAULT NOW())""")
            cur.execute("ALTER TABLE importacoes_gcom ADD COLUMN IF NOT EXISTS detalhe_marcas JSONB")
            cur.execute("""INSERT INTO importacoes_gcom (mes_referencia, periodo_inicio, periodo_fim, balcao, delivery,
                                                         detalhe_marcas, atualizado_em)
                           VALUES (%s,%s,%s,%s,%s,%s,NOW())
                           ON CONFLICT (mes_referencia) DO UPDATE SET periodo_inicio=EXCLUDED.periodo_inicio,
                           periodo_fim=EXCLUDED.periodo_fim, balcao=EXCLUDED.balcao, delivery=EXCLUDED.delivery,
                           detalhe_marcas=EXCLUDED.detalhe_marcas, atualizado_em=NOW()""",
                        (mes, inicio, fim, balcao, delivery, json.dumps(detalhe, ensure_ascii=False)))
        conn.commit()


# ----------------------------------------------------------------- avisos
def avisar_gerente(assunto, texto, anexo=None):
    remetente, senha = os.environ.get("EMAIL_REMETENTE"), os.environ.get("EMAIL_SENHA_APP")
    if not remetente or not senha:
        return
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = assunto, f"Painel Spoleto <{remetente}>", remetente
    msg.set_content(texto)
    if anexo:
        msg.add_attachment(anexo, maintype="image", subtype="png", filename="tela_gcom.png")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(remetente, senha.replace(" ", ""))
        smtp.send_message(msg)


def periodos_a_importar():
    hoje = datetime.now(FUSO).date()
    escolhido = os.environ.get("MES_GCOM", "").strip()
    if escolhido:
        ano, mes = map(int, escolhido.split("-"))
        fim = date(ano, mes, calendar.monthrange(ano, mes)[1])
        return [(f"{ano:04d}-{mes:02d}", date(ano, mes, 1), min(fim, hoje))]
    ontem = hoje - timedelta(days=1)
    periodos = [(f"{ontem:%Y-%m}", ontem.replace(day=1), ontem)]
    # Nos primeiros dias do mês, refaz o mês anterior inteiro para pegar ajustes de fechamento.
    if hoje.day <= 5:
        ultimo_anterior = hoje.replace(day=1) - timedelta(days=1)
        if f"{ultimo_anterior:%Y-%m}" != periodos[0][0]:
            periodos.append((f"{ultimo_anterior:%Y-%m}", ultimo_anterior.replace(day=1), ultimo_anterior))
    return periodos


def main():
    erros = 0
    for mes, inicio, fim in periodos_a_importar():
        log(f"Importando o mês {mes}.")
        diagnostico = {}
        try:
            relatorios = buscar_relatorios(inicio, fim, diagnostico)
            esperado = (inicio.strftime("%d/%m/%Y"), fim.strftime("%d/%m/%Y"))
            detalhe, total_balcao, total_ifood = {}, 0.0, 0.0
            for marca, conteudo in relatorios.items():
                diagnostico["etapa"] = f"leitura da marca {marca}"
                try:
                    colunas, linhas, periodo, marca_lida = ler_consolidado(conteudo)
                except ValueError:
                    texto = conteudo.decode("latin-1", "ignore").upper()
                    if "NENHUM" in texto or "NÃO HÁ" in texto or "NAO HA" in texto:
                        detalhe[marca] = {"balcao": 0.0, "ifood": 0.0, "outros": 0.0}
                        continue  # marca sem vendas no período
                    raise
                if periodo != (None, None) and periodo != esperado:
                    raise RuntimeError(f"O relatório da marca {marca} veio com período diferente do pedido.")
                if marca_lida and marca_lida.upper() != marca:
                    raise RuntimeError(f"Pedi a marca {marca}, mas o relatório veio da marca {marca_lida}.")
                balcao, ifood, outros = somar_canais(colunas, linhas)
                detalhe[marca] = {"balcao": balcao, "ifood": ifood, "outros": outros}
                total_balcao += balcao
                total_ifood += ifood
            lancar_na_dre(mes, round(total_balcao, 2), round(total_ifood, 2), inicio, fim, detalhe)
            log(f"Mês {mes} lançado na DRE com sucesso ({len(detalhe)} marcas).")
        except Exception as erro:
            erros += 1
            log(f"Falha ao importar {mes}: {type(erro).__name__}. Diagnóstico enviado ao e-mail do gerente.")
            try:
                avisar_gerente(
                    f"❌ Robô GCOM: falha ao importar vendas de {mes}",
                    f"O robô não conseguiu importar o faturamento de {mes}.\n\n"
                    f"Etapa: {diagnostico.get('etapa', '-')}\nErro: {erro}\n\n"
                    f"Endereço da tela: {diagnostico.get('url', '-')}\n\n"
                    f"Campos encontrados na tela:\n{diagnostico.get('campos', '-')}\n\n"
                    f"Detalhes técnicos:\n{traceback.format_exc()[-3000:]}",
                    diagnostico.get("print"))
            except Exception:
                log("Também não foi possível enviar o e-mail de diagnóstico.")
    if erros:
        sys.exit(1)


if __name__ == "__main__":
    main()
