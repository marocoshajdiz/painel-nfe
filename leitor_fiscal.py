"""Leitor fiscal local: XML NF-e/NFC-e, PDF textual e OCR opcional.
Não consulta SEFAZ; resultados de OCR exigem revisão humana.
"""
import io
import re
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation


def numero(valor):
    if valor is None:
        return 0.0
    t = str(valor).strip().replace('R$', '').replace(' ', '')
    if ',' in t:
        t = t.replace('.', '').replace(',', '.')
    try:
        return float(Decimal(t))
    except (InvalidOperation, ValueError):
        return 0.0


def classificar(nome, regras):
    return regras.get(nome.strip().upper(), 'Demais Alimentos')


def ler_xml(conteudo, regras):
    if b'<!DOCTYPE' in conteudo.upper() or b'<!ENTITY' in conteudo.upper():
        raise ValueError('XML com entidades externas não é permitido.')
    raiz = ET.fromstring(conteudo)
    def tag(e):
        return e.tag.rsplit('}', 1)[-1]
    def filho(e, nome):
        return next((x for x in e if tag(x) == nome), None) if e is not None else None
    def txt(e, nome):
        f = filho(e, nome)
        return (f.text or '').strip() if f is not None else ''
    inf = next((e for e in raiz.iter() if tag(e) == 'infNFe'), None)
    if inf is None:
        raise ValueError('Não foi encontrada uma NF-e/NFC-e válida neste XML.')
    emit = filho(inf, 'emit')
    total = filho(filho(inf, 'total'), 'ICMSTot')
    itens = []
    for det in inf:
        if tag(det) != 'det':
            continue
        prod = filho(det, 'prod')
        if prod is None:
            continue
        nome = txt(prod, 'xProd')
        if not nome:
            continue
        itens.append({
            'Produto': nome,
            'Quantidade': numero(txt(prod, 'qCom')),
            'Unid': txt(prod, 'uCom') or 'UN',
            'PrecoUnitario': numero(txt(prod, 'vUnCom')),
            'TotalItem': numero(txt(prod, 'vProd')),
            'Categoria': classificar(nome, regras),
        })
    if not itens:
        raise ValueError('O XML não contém itens de produtos.')
    return {
        'razao_social': txt(emit, 'xNome') or 'Fornecedor não identificado',
        'cnpj': txt(emit, 'CNPJ') or txt(emit, 'CPF') or 'Não informado',
        'valor_total': numero(txt(total, 'vNF')),
        'itens': itens,
        'origem_leitura': 'XML fiscal',
    }


# Padrão frequente de NFC-e: 001 PRODUTO 2,000 UN X 3,50 7,00
LINHA_ITEM = re.compile(
    r'^\s*(?:\d{1,4}\s+)?(?P<nome>[A-ZÀ-Úa-zà-ú][\wÀ-ÿ\s./%()\-]{2,}?)\s+'
    r'(?P<qtd>\d+[.,]\d{1,3}|\d+)\s*'
    r'(?P<un>UN|UND|KG|G|LT|L|PC|PCT|CX|FD|ML)?\s*'
    r'(?:[Xx*]\s*)?(?P<unit>\d+[.,]\d{2,4})\s+'
    r'(?P<total>\d+[.,]\d{2})\s*$', re.IGNORECASE
)


def interpretar_texto(texto, regras):
    itens = []
    for linha in texto.splitlines():
        linha = ' '.join(linha.split())
        m = LINHA_ITEM.match(linha)
        if not m:
            continue
        nome = m.group('nome').strip(' -')
        if any(p in nome.upper() for p in ('TOTAL', 'DESCONTO', 'TRIBUTO', 'TROCO', 'PAGAMENTO')):
            continue
        qtd, unit, total = (numero(m.group(k)) for k in ('qtd', 'unit', 'total'))
        if qtd <= 0 or total <= 0 or abs(qtd * unit - total) > max(0.10, total * 0.03):
            continue
        itens.append({
            'Produto': nome, 'Quantidade': qtd, 'Unid': (m.group('un') or 'UN').upper(),
            'PrecoUnitario': unit, 'TotalItem': total,
            'Categoria': classificar(nome, regras),
        })
    if not itens:
        raise ValueError('Não foi possível separar os itens com segurança. Use a IA ou o lançamento manual.')
    cnpj = re.search(r'\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b', texto)
    return {
        'razao_social': 'Fornecedor não identificado',
        'cnpj': cnpj.group() if cnpj else 'Não informado',
        'valor_total': round(sum(i['TotalItem'] for i in itens), 2),
        'itens': itens, 'origem_leitura': 'Texto / OCR (revisar obrigatoriamente)',
    }


def ler_pdf(conteudo, regras):
    import pypdf
    pdf = pypdf.PdfReader(io.BytesIO(conteudo))
    texto = '\n'.join(p.extract_text() or '' for p in pdf.pages[:20])
    if not texto.strip():
        raise ValueError('PDF digitalizado sem texto. Utilize OCR ou leitura por IA.')
    return interpretar_texto(texto, regras)


def ler_imagem_ocr(conteudo, regras):
    try:
        import pytesseract
        from PIL import Image, ImageOps, ImageEnhance
    except ImportError as e:
        raise ValueError('OCR não instalado. Adicione pytesseract e Pillow às dependências.') from e
    try:
        imagem = Image.open(io.BytesIO(conteudo))
        imagem = ImageOps.grayscale(imagem)
        imagem = ImageEnhance.Contrast(imagem).enhance(1.8)
        texto = pytesseract.image_to_string(imagem, lang='por')
    except pytesseract.TesseractNotFoundError as e:
        raise ValueError('Motor Tesseract não instalado no servidor.') from e
    except pytesseract.TesseractError as e:
        raise ValueError('Idioma português do OCR indisponível no servidor.') from e
    return interpretar_texto(texto, regras)
