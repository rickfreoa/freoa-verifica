"""Confronto de identidade declarada, sem inferir identidade de URL."""
from __future__ import annotations
import re
import json
from freoa_verifica.aliases import WorkKey
from freoa_verifica.citation import extract, _MONTHS

class IdentityMismatch(ValueError):
    pass

def declared_identity(document):
    # Somente epígrafe; remissões no corpo não identificam o ato capturado.
    if document.profile == 'senado_norma':
        try:
            data = json.loads(document.text)
            ident = data.get('identificacao') or data
            number = ident.get('numero') or data.get('numero')
            kind = ident.get('tipo') or data.get('tipo')
            date = ident.get('dataassinatura') or data.get('dataassinatura')
            year = ident.get('anoassinatura') or data.get('anoassinatura')
            if date:
                from freoa_verifica.connectors.senado import _parse_br_date
                date = _parse_br_date(str(date))
                year = (date or '')[:4] or year
            kinds = {'LEI':'lei','LCP':'lei_complementar','DEL':'decreto_lei','DEC':'decreto','MPV':'medida_provisoria'}
            if number and kind and year:
                return WorkKey('federal',kinds.get(str(kind).upper().split('-')[0],str(kind).lower()),str(number).replace('.','').lstrip('0'),int(year)),date
        except (ValueError,TypeError,AttributeError):
            pass
    title = document.title or ''
    if document.profile == 'cvm_pdf':
        epigraph = re.split(r'\bArt\.?\s*1[ºo°]?[.\s]',document.text[:4000],maxsplit=1,flags=re.I)[0]
        epigraph = re.sub(r'\bN\s+o\s+(?=\d)', 'Nº ', epigraph, flags=re.I)
        candidates = [c for c in extract(epigraph) if c.work and c.work.authority == 'cvm']
        if candidates:
            title = epigraph[candidates[0].span[0]:candidates[0].span[1]+200]
    title = re.split(r'COM\s+(?:AS\s+)?ALTERA', title, flags=re.I)[0]
    # Variações da epígrafe: ordinal no dia, 'DE' omitido e ano espaçado no PDF.
    title = re.sub(r'\b(\d{3})\s+(\d)\b', r'\1\2', title)
    cites = [c for c in extract(title) if c.work]
    if cites:
        key = cites[0].work
        date = None
        m = re.search(r'(\d{1,2})[º°o]?\s+(?:de\s+)?(\w+)\s+de\s+(\d{4})', title, re.I)
        if m and m[2].lower() in _MONTHS:
            date = f'{int(m[3]):04}-{_MONTHS[m[2].lower()]:02}-{int(m[1]):02}'
            key = WorkKey(key.authority,key.kind,key.number,int(m[3]))
        numeric_date = re.search(r'\bde\s+(\d{1,2})/(\d{1,2})/(\d{4})',title,re.I)
        if numeric_date:
            date = f'{int(numeric_date[3]):04}-{int(numeric_date[2]):02}-{int(numeric_date[1]):02}'
            key = WorkKey(key.authority,key.kind,key.number,int(numeric_date[3]))
        bcb = re.match(r'\[tipo=([^;]+); numero=([^;]+); data=([^;]+);', document.text)
        if bcb and not key.year and re.match(r'\d{4}-',bcb[3]):
            date = bcb[3][:10]
            key = WorkKey(key.authority,key.kind,key.number,int(date[:4]))
        if not key.year and document.profile == 'cvm_html':
            # Data do ato exibida antes da ementa; nunca anos de remissões.
            first = document.text.splitlines()[1:2]
            stamp = re.fullmatch(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\w+\s+(\d{4})',
                                 first[0].strip() if first else '')
            if stamp:
                key = WorkKey(key.authority,key.kind,key.number,int(stamp[1]))
        return key, date
    # BCB: campos da resposta capturada, anteriores ao texto normativo.
    m = re.match(r'\[tipo=([^;]+); numero=([^;]+); data=([^;]+);', document.text)
    if m:
        cs = [c for c in extract(f'{m[1]} {int(float(m[2]))}') if c.work]
        if cs:
            k=cs[0].work
            return WorkKey(k.authority,k.kind,k.number,int(m[3][:4])), m[3][:10]
    return None, None

def validate_identity(requested, document, requested_date=None):
    declared, date = declared_identity(document)
    if declared is None:
        return None
    if (requested.kind != declared.kind or requested.number.lstrip('0') != declared.number.lstrip('0')
        or (requested.year and declared.year and requested.year != declared.year)
        or requested.authority != declared.authority
        or (requested_date and date and requested_date != date)):
        raise IdentityMismatch('IDENTIDADE_DIVERGENTE')
    if (requested.year and not declared.year) or (requested_date and not date):
        return None
    return declared


def requested_date(text):
    m = re.search(r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})',text,re.I)
    if m and m[2].lower() in _MONTHS:
        return f'{int(m[3]):04}-{_MONTHS[m[2].lower()]:02}-{int(m[1]):02}'
    return None
