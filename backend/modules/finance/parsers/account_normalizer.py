"""
Normalização de Conta contabilística → código de cliente (genes_code).

Regra: no PGC português, contas de clientes conta corrente começam por
`21111` (classe 21 Clientes, subclasse 111 conta corrente). O código real
do cliente vem depois, com zeros à esquerda.

Exemplos:
  '2111100163' → '163'
  '2111103092' → '3092'
  '2111122485' → '22485'
  '2111100001' → '1'

Se a Conta não corresponder ao padrão, devolvemos None — o parser
regista warning em vez de inventar um código.
"""
import re
from typing import Optional

_ACCOUNT_RE = re.compile(r'^21111(\d+)$')


def normalize_account_to_client_code(account: Optional[str]) -> Optional[str]:
    if account is None:
        return None
    s = str(account).strip()
    if not s:
        return None
    m = _ACCOUNT_RE.match(s)
    if not m:
        return None
    suffix = m.group(1).lstrip('0')
    return suffix or '0'
