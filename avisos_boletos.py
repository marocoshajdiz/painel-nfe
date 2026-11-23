"""Envia e-mail com os boletos pendentes que vencem hoje e amanhã.

Executado uma vez por dia pelo GitHub Actions (.github/workflows/avisos_boletos.yml).
Segredos (GitHub > Settings > Secrets and variables > Actions):
  DATABASE_URL      mesma URL do Supabase usada no Streamlit
  EMAIL_REMETENTE   Gmail que envia, ex.: avisos.spoleto@gmail.com
  EMAIL_SENHA_APP   senha de app de 16 letras gerada no Google (não é a senha normal)
  EMAIL_DESTINOS    e-mails que recebem, separados por vírgula
Opcional:
  EMAIL_SIMULAR=1   mostra o e-mail no log sem enviar (para teste)
"""
import html
import os
import smtplib
import sys
from datetime import datetime, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import psycopg2

FUSO = ZoneInfo("America/Sao_Paulo")
LIMITE_ANEXOS = 20 * 1024 * 1024  # o Gmail aceita até 25 MB por e-mail


def reais(valor):
    return "R$ " + f"{float(valor or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def tabela_html(titulo, cor, boletos):
    linhas = "".join(
        f"<tr><td style='padding:8px;border-bottom:1px solid #e5e7eb'><b>{html.escape(b['fornecedor'])}</b><br>"
        f"<span style='color:#64748b'>{html.escape(b['referencia'])}</span></td>"
        f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;text-align:right;white-space:nowrap'><b>{reais(b['valor'])}</b></td></tr>"
        f"<tr><td colspan='2' style='padding:4px 8px 12px;border-bottom:1px solid #e5e7eb;font-family:monospace;font-size:13px;color:#334155'>"
        f"{html.escape(b['codigo'] or 'Sem linha digitável cadastrada')}</td></tr>"
        for b in boletos)
    total = sum(b["valor"] for b in boletos)
    return (f"<h3 style='color:{cor};margin:24px 0 8px'>{titulo}</h3>"
            f"<table style='width:100%;border-collapse:collapse;font-size:14px'>{linhas}"
            f"<tr><td style='padding:8px'><b>Total</b></td><td style='padding:8px;text-align:right'><b>{reais(total)}</b></td></tr></table>")


def montar_email(hoje, amanha, venc_hoje, venc_amanha):
    partes = []
    if venc_hoje:
        partes.append(f"{len(venc_hoje)} vence{'m' if len(venc_hoje) > 1 else ''} hoje")
    if venc_amanha:
        partes.append(f"{len(venc_amanha)} vence{'m' if len(venc_amanha) > 1 else ''} amanhã")
    total = sum(b["valor"] for b in venc_hoje + venc_amanha)
    assunto = f"⚠️ Boletos: {' e '.join(partes)} — {reais(total)}"
    corpo = ["<div style='font-family:Arial,sans-serif;max-width:640px;color:#0f172a'>",
             "<h2 style='color:#102b51;margin-bottom:4px'>Spoleto Capry — aviso de boletos</h2>",
             "<p style='color:#64748b;margin-top:0'>Boletos pendentes cadastrados no Painel de Custos &amp; DRE.</p>"]
    if venc_hoje:
        corpo.append(tabela_html(f"🔴 Vencem HOJE ({hoje:%d/%m/%Y})", "#b91c1c", venc_hoje))
    if venc_amanha:
        corpo.append(tabela_html(f"🟡 Vencem AMANHÃ ({amanha:%d/%m/%Y})", "#b45309", venc_amanha))
    corpo.append("<p style='color:#64748b;font-size:12px;margin-top:24px'>Os números abaixo de cada boleto são a linha digitável "
                 "(copie e cole no app do banco). Boletos com arquivo original seguem em anexo. Depois de pagar, "
                 "marque como pago na tela de Boletos para não receber novos avisos.</p></div>")
    return assunto, "".join(corpo)


def main():
    destinos = [d.strip() for d in os.environ.get("EMAIL_DESTINOS", "").split(",") if d.strip()]
    if not destinos:
        sys.exit("Configure EMAIL_DESTINOS com pelo menos um e-mail.")
    simular = os.environ.get("EMAIL_SIMULAR") == "1"
    hoje = datetime.now(FUSO).date()
    amanha = hoje + timedelta(days=1)
    with psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=15, sslmode="require") as conn:
        with conn.cursor() as cur:
            # Registro dos avisos: impede e-mail repetido se o robô rodar duas vezes no dia.
            cur.execute("""CREATE TABLE IF NOT EXISTS avisos_email_boletos (
                boleto_id BIGINT NOT NULL, tipo TEXT NOT NULL, destino TEXT NOT NULL,
                enviado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (boleto_id, tipo, destino))""")
            conn.commit()
            cur.execute("""SELECT id, fornecedor_nome, descricao, valor, vencimento, linha_digitavel,
                                  codigo_barras, documento_nome, arquivo_conteudo
                           FROM boletos_horte_spoleto
                           WHERE status='PENDENTE' AND vencimento IN (%s, %s)
                           ORDER BY vencimento, fornecedor_nome, id""", (hoje, amanha))
            boletos = [{"id": r[0], "fornecedor": r[1] or "Fornecedor", "referencia": r[2] or "Sem referência",
                        "valor": float(r[3] or 0), "tipo": "DIA" if r[4] == hoje else "VESPERA",
                        "codigo": r[5] or r[6] or "", "arquivo_nome": r[7], "arquivo": r[8]} for r in cur.fetchall()]
            if not boletos:
                print("Nenhum boleto pendente vence hoje ou amanhã.")
                return
            for destino in destinos:
                cur.execute("""SELECT boleto_id, tipo FROM avisos_email_boletos
                               WHERE destino=%s AND boleto_id = ANY(%s)""", (destino, [b["id"] for b in boletos]))
                ja_avisados = set(cur.fetchall())
                novos = [b for b in boletos if (b["id"], b["tipo"]) not in ja_avisados]
                if not novos:
                    print(f"{destino}: avisos de hoje já enviados.")
                    continue
                assunto, corpo = montar_email(hoje, amanha,
                                              [b for b in novos if b["tipo"] == "DIA"],
                                              [b for b in novos if b["tipo"] == "VESPERA"])
                msg = EmailMessage()
                msg["Subject"] = assunto
                msg["From"] = f"Painel Spoleto <{os.environ.get('EMAIL_REMETENTE', 'simulacao@local')}>"
                msg["To"] = destino
                msg.set_content("Seu leitor de e-mail não exibe HTML. Abra o Painel Spoleto para ver os boletos.")
                msg.add_alternative(corpo, subtype="html")
                tamanho = 0
                for b in novos:
                    if b["arquivo"] and tamanho + len(b["arquivo"]) <= LIMITE_ANEXOS:
                        nome = b["arquivo_nome"] or f"boleto_{b['id']}.pdf"
                        tipo = ("application", "pdf") if nome.lower().endswith(".pdf") else \
                               ("image", "png") if nome.lower().endswith(".png") else ("image", "jpeg")
                        msg.add_attachment(bytes(b["arquivo"]), maintype=tipo[0], subtype=tipo[1], filename=nome)
                        tamanho += len(b["arquivo"])
                if simular:
                    print(f"[SIMULAÇÃO] Para {destino} | {assunto} | {len(novos)} boleto(s), anexos: {tamanho // 1024} KB")
                    continue
                with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
                    smtp.login(os.environ["EMAIL_REMETENTE"], os.environ["EMAIL_SENHA_APP"].replace(" ", ""))
                    smtp.send_message(msg)
                cur.executemany("""INSERT INTO avisos_email_boletos (boleto_id, tipo, destino)
                                   VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""",
                                [(b["id"], b["tipo"], destino) for b in novos])
                conn.commit()
                print(f"OK: e-mail enviado para {destino} ({len(novos)} boleto(s))")


if __name__ == "__main__":
    main()
