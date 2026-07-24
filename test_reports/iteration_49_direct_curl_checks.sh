#!/usr/bin/env bash
set -euo pipefail

API="${TEST_BASE_URL:-http://localhost:8001}/api"
TOKEN="$({ curl -sS -X POST "$API/auth/login" -H 'Content-Type: application/json' -d '{"email":"admin@pdpv.pt","password":"HCNMEnKMLq"}' | python -c 'import json,sys; print(json.load(sys.stdin)["token"])'; })"

curl -sS "$API/finance/imports?limit=20&offset=0" -H "Authorization: Bearer $TOKEN" \
  | python -c 'import json,sys; data=json.load(sys.stdin); req={"rows_processed","clients_found","clients_matched","clients_updated","clients_ignored","documents_created"}; imps=data["imports"]; ci=next(i for i in imps if i["type"]=="client_info"); ce=next(i for i in imps if i["type"]=="credit_evolution"); assert req <= set(ci["totals"]), ci; assert req|{"periods"} <= set(ce["totals"]), ce; print({"client_info": ci["totals"], "credit_evolution": ce["totals"]})'

curl -sS "$API/finance/clients/qa-ret48-628cd7a2-cf25-4a31-8102-22072dc17227/credit-evolution" -H "Authorization: Bearer $TOKEN" \
  | python -c 'import json,sys; d=json.load(sys.stdin); assert d["available"] is True and len(d["series"])==6, d; print({"available": d["available"], "periods": [x["period"] for x in d["series"]], "peak": d["peak"], "last": d["last"], "previous": d["previous"], "quarter_diff_abs": d["quarter_diff_abs"], "quarter_diff_pct": d["quarter_diff_pct"], "trend": d["trend"]})'