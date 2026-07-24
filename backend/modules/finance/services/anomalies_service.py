"""
Serviço de detecção de anomalias entre imports Finance consecutivos.

Compara pares (import_atual, import_anterior_do_mesmo_tipo) e devolve
uma lista de anomalias com severidade (warning/critical) e estado
(active/validated). Cálculo on-the-fly — sem persistência das
anomalias em si (só as validações são gravadas em
`finance_anomaly_validations`).

Thresholds (iter 47 — Feb 2026, aprovados pelo utilizador):
  - total_overdue Δ > 20%  → CRÍTICO
  - clients_count Δ > 10%  → WARNING
  - documents_count Δ > 10% → WARNING
  - Noise floor: só flag se Δ absoluta de total_overdue > 500€
  - Noise floor: só flag se Δ absoluta de documents > 10
"""
import hashlib
import logging
from typing import Dict, List, Optional, Tuple

from db import db
from ..models import ImportType, ImportStatus

logger = logging.getLogger(__name__)

# Thresholds (percentagens em [0, 1])
TH_TOTAL_OVERDUE_CRITICAL = 0.20
TH_CLIENTS_WARNING = 0.10
TH_DOCS_WARNING = 0.10

# Noise floors — deltas absolutos abaixo destes não geram anomalia
NF_TOTAL_OVERDUE_EUR = 500.0
NF_DOCUMENTS = 10


def _make_anomaly_id(type_key: str, current_id: str, previous_id: str) -> str:
    """ID determinístico para permitir cross-lookup na coleção de validações."""
    h = hashlib.sha256(f'{type_key}|{current_id}|{previous_id}'.encode()).hexdigest()
    return h[:16]


def _pct_delta(current: float, previous: float) -> float:
    """Variação percentual [0, 1+]. Se previous==0 e current>0 → 1.0 (100%)."""
    if previous <= 0:
        return 1.0 if current > 0 else 0.0
    return abs(current - previous) / previous


def _detect_pair(type_key: str, current: Dict, previous: Dict) -> Optional[Dict]:
    """
    Compara par de imports do mesmo tipo. Devolve dict de anomalia ou
    None se nenhum threshold foi atingido.
    """
    c_totals = current.get('totals') or {}
    p_totals = previous.get('totals') or {}

    cur_total = float(c_totals.get('total_overdue') or 0)
    prev_total = float(p_totals.get('total_overdue') or 0)
    cur_clients = int(c_totals.get('clients') or 0)
    prev_clients = int(p_totals.get('clients') or 0)
    cur_docs = int(c_totals.get('documents') or 0)
    prev_docs = int(p_totals.get('documents') or 0)

    total_diff = cur_total - prev_total
    total_pct = _pct_delta(cur_total, prev_total)
    clients_diff = cur_clients - prev_clients
    clients_pct = _pct_delta(cur_clients, prev_clients)
    docs_diff = cur_docs - prev_docs
    docs_pct = _pct_delta(cur_docs, prev_docs)

    triggers: List[str] = []
    severity: Optional[str] = None

    # total_overdue crítico
    if (
        total_pct > TH_TOTAL_OVERDUE_CRITICAL
        and abs(total_diff) > NF_TOTAL_OVERDUE_EUR
    ):
        triggers.append(f'total_overdue Δ {total_pct*100:.1f}% (limiar 20%)')
        severity = 'critical'

    # clients warning
    if clients_pct > TH_CLIENTS_WARNING:
        triggers.append(f'clientes Δ {clients_pct*100:.1f}% (limiar 10%)')
        if severity != 'critical':
            severity = 'warning'

    # documents warning
    if (
        docs_pct > TH_DOCS_WARNING
        and abs(docs_diff) > NF_DOCUMENTS
    ):
        triggers.append(f'documentos Δ {docs_pct*100:.1f}% (limiar 10%)')
        if severity != 'critical':
            severity = 'warning'

    if not triggers or not severity:
        return None

    anomaly_id = _make_anomaly_id(type_key, current['id'], previous['id'])

    return {
        'id': anomaly_id,
        'import_type': type_key,
        'severity': severity,
        'triggers': triggers,
        'current': {
            'import_id': current['id'],
            'filename': current.get('filename'),
            'uploaded_at': current.get('uploaded_at'),
            'total_overdue': round(cur_total, 2),
            'clients': cur_clients,
            'documents': cur_docs,
        },
        'previous': {
            'import_id': previous['id'],
            'filename': previous.get('filename'),
            'uploaded_at': previous.get('uploaded_at'),
            'total_overdue': round(prev_total, 2),
            'clients': prev_clients,
            'documents': prev_docs,
        },
        'delta': {
            'total_overdue_abs': round(total_diff, 2),
            'total_overdue_pct': round(total_pct * 100, 2),
            'clients_abs': clients_diff,
            'clients_pct': round(clients_pct * 100, 2),
            'documents_abs': docs_diff,
            'documents_pct': round(docs_pct * 100, 2),
        },
    }


async def _load_validations() -> Dict[str, Dict]:
    """Carrega todas as validações activas por anomaly_id."""
    result: Dict[str, Dict] = {}
    async for v in db.finance_anomaly_validations.find({}, {'_id': 0}):
        result[v['anomaly_id']] = v
    return result


async def compute_anomalies(
    status_filter: str = 'active',
    severity_filter: Optional[str] = None,
    limit_per_type: int = 20,
) -> List[Dict]:
    """
    Devolve lista de anomalias entre imports consecutivos por tipo.

    status_filter: 'active' | 'validated' | 'all'
    severity_filter: 'warning' | 'critical' | None
    limit_per_type: quantos pares mais recentes examinar por tipo
                    (o mais comum é a anomalia estar nos últimos 2-3
                    imports; 20 dá folga)
    """
    validations = await _load_validations()
    anomalies: List[Dict] = []

    for type_enum in ImportType:
        type_key = type_enum.value
        # Só considera imports que efectivamente aplicaram dados
        cursor = db.finance_imports.find(
            {'type': type_key, 'status': {'$in': [
                ImportStatus.IMPORTED.value,
                ImportStatus.ACCEPTED_WITH_WARNINGS.value,
            ]}},
            {'_id': 0}
        ).sort('uploaded_at', -1).limit(limit_per_type + 1)
        imports = await cursor.to_list(limit_per_type + 1)
        if len(imports) < 2:
            continue

        # Pares consecutivos (imports[i], imports[i+1]) — i mais recente
        for i in range(len(imports) - 1):
            current = imports[i]
            previous = imports[i + 1]
            anomaly = _detect_pair(type_key, current, previous)
            if not anomaly:
                continue

            validation = validations.get(anomaly['id'])
            anomaly['status'] = 'validated' if validation else 'active'
            if validation:
                anomaly['validation'] = {
                    'validated_by': validation.get('validated_by'),
                    'validated_by_name': validation.get('validated_by_name'),
                    'validated_at': validation.get('validated_at'),
                    'comment': validation.get('comment'),
                }

            # Filtros
            if status_filter == 'active' and anomaly['status'] != 'active':
                continue
            if status_filter == 'validated' and anomaly['status'] != 'validated':
                continue
            if severity_filter and anomaly['severity'] != severity_filter:
                continue

            anomalies.append(anomaly)

    # Ordenação estável: activas primeiro, depois críticas, depois data desc
    def _sort_key(a):
        status_rank = 0 if a['status'] == 'active' else 1
        sev_rank = 0 if a['severity'] == 'critical' else 1
        # Data mais recente primeiro → invertemos com sinal negativo (str ok invertendo)
        date_key = a['current']['uploaded_at'] or ''
        return (status_rank, sev_rank, date_key)
    anomalies.sort(key=lambda a: a['current']['uploaded_at'] or '', reverse=True)
    anomalies.sort(key=lambda a: (
        0 if a['status'] == 'active' else 1,
        0 if a['severity'] == 'critical' else 1,
    ))

    return anomalies


async def count_active_anomalies() -> Dict[str, int]:
    """Contagem rápida para o badge do dashboard."""
    active = await compute_anomalies(status_filter='active')
    critical = sum(1 for a in active if a['severity'] == 'critical')
    warning = sum(1 for a in active if a['severity'] == 'warning')
    return {'active_total': len(active), 'critical': critical, 'warning': warning}


async def validate_anomaly(
    anomaly_id: str,
    user: Dict,
    comment: str,
) -> Dict:
    """
    Regista validação de uma anomalia. Requer comentário obrigatório.
    Guarda snapshot dos dados no momento da validação para audit trail.

    Levanta ValueError se:
      - anomaly_id não corresponde a nenhuma anomalia activa;
      - comentário vazio;
      - já foi validada.
    """
    from datetime import datetime, timezone
    comment = (comment or '').strip()
    if not comment:
        raise ValueError('Comentário obrigatório para validar anomalia.')

    # Encontra anomalia (recalcula tudo — barato porque limit_per_type é pequeno)
    anomalies = await compute_anomalies(status_filter='all')
    target = next((a for a in anomalies if a['id'] == anomaly_id), None)
    if not target:
        raise ValueError('Anomalia não encontrada (pode já não estar entre os imports recentes).')
    if target['status'] == 'validated':
        raise ValueError('Anomalia já validada anteriormente.')

    now = datetime.now(timezone.utc).isoformat()
    validation_doc = {
        'anomaly_id': anomaly_id,
        'import_type': target['import_type'],
        'severity': target['severity'],
        'validated_by': user.get('id'),
        'validated_by_name': user.get('name') or user.get('email'),
        'validated_at': now,
        'comment': comment,
        'snapshot': {
            'current': target['current'],
            'previous': target['previous'],
            'delta': target['delta'],
            'triggers': target['triggers'],
        },
    }
    await db.finance_anomaly_validations.insert_one(validation_doc)
    logger.info(
        f'Anomaly {anomaly_id} validated by {user.get("email")}: {comment[:60]}'
    )
    target['status'] = 'validated'
    target['validation'] = {
        'validated_by': validation_doc['validated_by'],
        'validated_by_name': validation_doc['validated_by_name'],
        'validated_at': now,
        'comment': comment,
    }
    return target
