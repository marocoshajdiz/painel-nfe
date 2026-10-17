"""Leitor fiscal offline. XML exato; PDF/texto/OCR exigem conferência humana."""
import io
import re
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation


def numero(valor):
    if valor is None: return 0.0
    t = str(valor).strip().replace('R$', '').replace(' ', '')
    if ',' in t: t = t.replace('.', '').replace(',', '.')
    try: return float(Decimal(t))
    except (InvalidOperation, ValueError): return 0.0


def classificar(nome, regras):
    chave = ' '.join(nome.upper().split())
    regras_normalizadas = {' '.join(str(k).upper().split()):v for k,v in (regras or {}).items()}
    return regras_normalizadas.get(chave, 'Demais Alimentos')


def ler_xml(conteudo, regras):
    if b'<!DOCTYPE' in conteudo.upper() or b'<!ENTITY' in conteudo.upper():
        raise ValueError('XML com entidades não permitido.')
    raiz = ET.fromstring(conteudo)
    def tag(e): return e.tag.rsplit('}',1)[-1]
    def filho(e,n): return next((x for x in e if tag(x)==n),None) if e is not None else None
    def txt(e,n):
        f=filho(e,n)
        return (f.text or '').strip() if f is not None else ''
    inf=next((e for e in raiz.iter() if tag(e)=='infNFe'),None)
    if inf is None: raise ValueError('NF-e/NFC-e não encontrada.')
    emit=filho(inf,'emit'); total=filho(filho(inf,'total'),'ICMSTot')
    itens=[]
    for det in inf:
        if tag(det)!='det': continue
        prod=filho(det,'prod')
        if prod is None or not txt(prod,'xProd'): continue
        nome=txt(prod,'xProd')
        itens.append({'Produto':nome,'Quantidade':numero(txt(prod,'qCom')),
            'Unid':txt(prod,'uCom') or 'UN','PrecoUnitario':numero(txt(prod,'vUnCom')),
            'TotalItem':numero(txt(prod,'vProd')),'Categoria':classificar(nome,regras)})
    if not itens: raise ValueError('XML sem produtos.')
    return {'razao_social':txt(emit,'xNome') or 'Fornecedor não identificado',
        'cnpj':txt(emit,'CNPJ') or txt(emit,'CPF') or 'Não informado',
        'valor_total':numero(txt(total,'vNF')),'itens':itens,'origem_leitura':'XML fiscal'}

# NFC-e lines with optional code, quantity/unit, x, unit price and total.
VALOR=r'(?:\d{1,3}(?:\.\d{3})+,\d{2,4}|\d+[,.]\d{2,4})'
PADROES=[
 re.compile(r'^\s*(?:\d{1,6}\s+)?(?P<nome>[A-ZÀ-ÿ][\wÀ-ÿ\s./%()\-+]{2,}?)\s+(?P<qtd>\d+(?:[,.]\d{1,3})?)\s*(?P<un>UN|UND|KG|G|LT|L|PC|PCT|CX|FD|ML|BD|SC|FR|DZ)?\s*(?:[Xx*]\s*)?(?P<unit>'+VALOR+r')\s+(?P<total>'+VALOR+r')\s*$',re.I),
 re.compile(r'^\s*(?:\d{1,6}\s+)?(?P<nome>[A-ZÀ-ÿ][\wÀ-ÿ\s./%()\-+]{2,}?)\s+(?P<qtd>\d+(?:[,.]\d{1,3})?)\s*(?P<un>UN|UND|KG|G|LT|L|PC|PCT|CX|FD|ML|BD|SC|FR|DZ)\s*[Xx*]\s*(?P<unit>'+VALOR+r')\s+(?P<total>'+VALOR+r')\s*$',re.I),
]
EXCLUI=('TOTAL','DESCONTO','TRIBUTO','TROCO','PAGAMENTO','SUBTOTAL','IMPOSTO','VALOR A PAGAR')


def interpretar_texto(texto,regras):
    texto=texto.replace('\xa0',' ').replace('×',' X ')
    linhas=[' '.join(l.split()) for l in texto.splitlines() if l.strip()]
    itens=[]
    for linha in linhas:
        for padrao in PADROES:
            m=padrao.match(linha)
            if not m: continue
            nome=m.group('nome').strip(' -:')
            if any(p in nome.upper() for p in EXCLUI): break
            qtd,preco,total=(numero(m.group(x)) for x in ('qtd','unit','total'))
            if qtd<=0 or preco<=0 or total<=0: break
            if abs(qtd*preco-total)>max(.11,total*.025): break
            itens.append({'Produto':nome,'Quantidade':qtd,'Unid':(m.group('un') or 'UN').upper(),
                'PrecoUnitario':preco,'TotalItem':total,'Categoria':classificar(nome,regras)})
            break
    if not itens: raise ValueError('Nenhuma linha de produto reconhecida com confiança; revise manualmente.')
    cnpj=re.search(r'\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b',texto)
    soma=round(sum(x['TotalItem'] for x in itens),2)
    # Total is a sum of recovered items, NOT asserted as original fiscal total.
    return {'razao_social':'Fornecedor não identificado','cnpj':cnpj.group() if cnpj else 'Não informado',
        'valor_total':soma,'itens':itens,'origem_leitura':'OCR/texto parcial - CONFERIR TOTAL E ITENS',
        'aviso_conferencia':'Total estimado pelos itens reconhecidos; confira descontos, frete e itens ausentes.'}


def _ocr_pil(img):
    import pytesseract
    from PIL import ImageOps,ImageEnhance,ImageFilter
    img=ImageOps.exif_transpose(img).convert('RGB')
    if img.width<1600:
        fator=min(3,1600/max(img.width,1))
        img=img.resize((int(img.width*fator),int(img.height*fator)))
    gray=ImageOps.grayscale(img)
    candidatos=[ImageEnhance.Contrast(gray).enhance(1.7),
                gray.filter(ImageFilter.MedianFilter(3)),
                gray.point(lambda x:255 if x>160 else 0)]
    textos=[]
    for imagem in candidatos:
        for psm in (6,3):
            try: textos.append(pytesseract.image_to_string(imagem,lang='por',config=f'--psm {psm}'))
