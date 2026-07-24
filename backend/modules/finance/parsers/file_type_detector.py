"""
Detector heurístico do tipo de ficheiro Finance a partir dos headers.

Lê as primeiras 15 linhas do xlsx e calcula um score para cada tipo,
retornando o mais provável com uma medida de confiança. Usa-se antes
do upload para avisar o utilizador quando o tipo seleccionado
diverge da estrutura real do ficheiro (o cenário que causou o bug
do 1492 clientes / 0 documentos em Feb 2026).
"""
from io import BytesIO
from typing import Dict, List, Tuple

import openpyxl

# Assinaturas de cabeçalho por tipo. Cada assinatura é uma lista de
# tokens que devem aparecer em pelo menos 1 das primeiras 15 linhas
# do sheet. Tokens são case-insensitive e substring-match.
TYPE_SIGNATURES: Dict[str, Dict[str, List[str]]] = {
    'overdue_balances': {
        'required': ['Cliente', 'Cód. Cliente', 'Importe Total Vencido'],
        'strong':   ['Saldo Cliente', 'Data Vencimento', 'Dias Vencidos'],
    },
    'open_documents': {
        'required': ['CodPersona', 'Descritivo', 'Saldo'],
        'strong':   ['Tipo D. Pagamento', 'Data Fat.', 'Data Venc.', 'Cobrado'],
    },
    'client_info': {
        'required': ['CodCliente', 'Cliente'],
        'strong':   ['Alm.', 'Saldo Conta', 'Carteira', 'Fat. Ano'],
    },
    'credit_evolution': {
        'required': ['CODCLIENTE', 'Cliente'],
        'strong':   ['Conta'],  # + colunas dinâmicas MM-YYYY (não incluídas)
    },
}


def _read_first_rows(file_content: bytes, n: int = 15) -> List[List[str]]:
    """Lê as primeiras N linhas do xlsx como strings, sem carregar tudo."""
    try:
        wb = openpyxl.load_workbook(BytesIO(file_content), data_only=True, read_only=True)
        sheet = wb.active
        rows = []
        for i, row in enumerate(sheet.iter_rows(values_only=True)):
            if i >= n:
                break
            rows.append([str(c).strip() if c is not None else '' for c in row])
        wb.close()
        return rows
    except Exception:
        return []


def _score_type(rows: List[List[str]], sig: Dict[str, List[str]]) -> Tuple[int, int, int]:
    """
    Devolve (required_hits, strong_hits, total_signature_size).
    Match é substring case-insensitive.
    """
    flat = ' '.join(' '.join(r) for r in rows).lower()
    required_hits = sum(1 for tok in sig['required'] if tok.lower() in flat)
    strong_hits = sum(1 for tok in sig['strong'] if tok.lower() in flat)
    total = len(sig['required']) + len(sig['strong'])
    return required_hits, strong_hits, total


def detect_file_type(file_content: bytes) -> Dict[str, object]:
    """
    Devolve dicionário com:
      - detected: melhor match (ou None se score insuficiente)
      - confidence: 'high' | 'medium' | 'low' | 'unknown'
      - scores: dict com breakdown por tipo (required_hits, strong_hits, total)
    """
    rows = _read_first_rows(file_content)
    if not rows:
        return {
            'detected': None,
            'confidence': 'unknown',
            'scores': {},
            'error': 'Não foi possível ler o ficheiro (xlsx inválido ou vazio).',
        }

    scores = {}
    for type_key, sig in TYPE_SIGNATURES.items():
        r, s, t = _score_type(rows, sig)
        scores[type_key] = {
            'required_hits': r,
            'required_total': len(sig['required']),
            'strong_hits': s,
            'strong_total': len(sig['strong']),
            'score': r * 10 + s,  # required tem 10x o peso
        }

    # Melhor candidato
    best_type = max(scores, key=lambda k: scores[k]['score'])
    best = scores[best_type]

    # Confiança:
    #   high   : todos os required + pelo menos 50% dos strong
    #   medium : todos os required
    #   low    : pelo menos 1 required, mas não todos
    #   unknown: nenhum required
    if best['required_hits'] == best['required_total']:
        if best['strong_hits'] * 2 >= best['strong_total']:
            confidence = 'high'
        else:
            confidence = 'medium'
    elif best['required_hits'] >= 1:
        confidence = 'low'
    else:
        confidence = 'unknown'
        best_type = None

    return {
        'detected': best_type,
        'confidence': confidence,
        'scores': scores,
    }
