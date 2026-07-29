"""
Focused verification for Iteration 51 user bug:
CodPersona (e.g. 120) must not create/keep duplicate finance clients when
Conta 2111100163 proves the real client code is 163.

This script uses an isolated Mongo database for the destructive merge-script
checks, so it does not mutate the preview app database while still executing
the real /app/backend/scripts/merge_duplicate_finance_clients.py script.
"""
import asyncio
import io
import os
import subprocess
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from openpyxl import Workbook

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

from modules.finance.parsers.account_normalizer import normalize_account_to_client_code
from modules.finance.parsers import parse_client_info, parse_credit_evolution, parse_open_documents


MONGO_URL = os.environ["MONGO_URL"]
BASE_DB_NAME = os.environ["DB_NAME"]
TEST_DB_NAME = f"{BASE_DB_NAME}_iter51_focus_verification"
SCRIPT = "/app/backend/scripts/merge_duplicate_finance_clients.py"


def workbook_bytes(headers, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def check_parsers():
    print("[1] Checking normalizer and parsers ignore CodPersona and use Conta suffix")
    cases = {
        "2111100163": "163",
        "2111103092": "3092",
        "2111122485": "22485",
        "2111100001": "1",
        "120": None,
        "": None,
        None: None,
    }
    failures = []
    for raw, expected in cases.items():
        actual = normalize_account_to_client_code(raw)
        if actual != expected:
            failures.append(f"normalizer({raw!r}) returned {actual!r}, expected {expected!r}")

    docs_xlsx = workbook_bytes(
        [
            "CodPersona", "Conta", "Tipo D. Pagamento", "Forma Pagamento",
            "Data Fat.", "Data Venc.", "Cliente", "Descritivo", "Saldo",
            "Quantia", "Vencido", "Cobrado",
        ],
        [
            [120, "2111100163", "TB", "30D", datetime(2026, 6, 15), datetime(2026, 7, 15),
             "PROEF EURICO", "VTO. FAT./FT 026/4645", 44109.18, 274, 274, 0],
            [2343, "2111103092", "TB", "30D", datetime(2026, 4, 21), datetime(2026, 5, 21),
             "3LD COMERCIO", "VTO. FAT./FT 026/3119", 327.94, 125.41, 125.41, 0],
        ],
    )
    parsed_docs = parse_open_documents(docs_xlsx)
    doc_codes = {d["genes_code"] for d in parsed_docs["documents"]}
    if doc_codes != {"163", "3092"} or "120" in doc_codes or "2111100163" in doc_codes:
        failures.append(f"open docs parser returned codes {doc_codes}, expected only {{'163','3092'}}")

    info_xlsx = workbook_bytes(
        ["CodCliente", "Conta", "Cliente", "Saldo Conta", "Carteira", "Domiciliações", "Risco"],
        [[120, "2111100163", "PROEF EURICO", 43615, 44109, 0, 5000]],
    )
    parsed_info = parse_client_info(info_xlsx)
    if parsed_info["errors"] or not parsed_info["clients"] or parsed_info["clients"][0]["genes_code"] != "163":
        failures.append(f"client_info Conta=2111100163 did not return genes_code 163: {parsed_info}")

    bad_info = workbook_bytes(
        ["CodPersona", "Conta", "Cliente"],
        [[120, "120", "PROEF EURICO"]],
    )
    parsed_bad_info = parse_client_info(bad_info)
    if parsed_bad_info["clients"] or not parsed_bad_info["warnings"]:
        failures.append(
            "client_info invalid Conta=120 with CodPersona=120 should warn/skip and never use CodPersona, "
            f"but returned: {parsed_bad_info}"
        )

    evolution_xlsx = workbook_bytes(
        ["CODCLIENTE", "Conta", "Cliente", "03-2026", "06-2026"],
        [[120, "2111100163", "PROEF EURICO", 100, 150]],
    )
    parsed_evo = parse_credit_evolution(evolution_xlsx)
    if parsed_evo["errors"] or not parsed_evo["clients"] or parsed_evo["clients"][0]["genes_code"] != "163":
        failures.append(f"evolution Conta=2111100163 did not return genes_code 163: {parsed_evo}")
    if failures:
        print("    FAILURES:")
        for f in failures:
            print("      - " + f)
    else:
        print("    PASS: parser layer maps Conta 2111100163 -> genes_code 163 and ignores CodPersona 120")
    return failures


async def seed_exact_codpersona_duplicate(db):
    now = datetime.now(timezone.utc).isoformat()
    await db.finance_clients.delete_many({"id": {"$in": ["qa51-master-163", "qa51-dup-120"]}})
    for col in [
        "finance_credit_evolution", "finance_documents", "finance_actions", "finance_promises",
        "finance_regularizations", "finance_tasks", "finance_block_requests", "finance_blocks",
    ]:
        await db[col].delete_many({"client_id": {"$in": ["qa51-master-163", "qa51-dup-120"]}})
        await db[col].delete_many({"genes_code": {"$in": ["163", "120"]}})

    base = {
        "name": "PROEF EURICO FERREIRA QA51",
        "total_balance": 0,
        "overdue_balance_accounting": 0,
        "overdue_balance_collectable": 0,
        "residual_balance": 0,
        "oldest_overdue_days": 0,
        "collection_index": 0,
        "financial_status": "OK",
        "traffic_light": "GREEN",
        "is_residual_only": False,
        "is_blocked": False,
        "manual_marks": [],
        "created_at": now,
        "updated_at": now,
    }
    await db.finance_clients.insert_one({
        **base,
        "id": "qa51-master-163",
        "genes_code": "163",
        "finance_email": "master163@example.test",
    })
    # Exact historical bug shape: duplicate client key came from CodPersona=120,
    # but the accounting account available on the record proves it belongs to 163.
    await db.finance_clients.insert_one({
        **base,
        "id": "qa51-dup-120",
        "genes_code": "120",
        "genes_account": "2111100163",
        "account": "2111100163",
        "carteira": 44109.18,
        "domiciliacoes": 0,
        "forma_pagamento": "Pagamento a 30 dias",
        "finance_email": "dup120@example.test",
    })
    await db.finance_credit_evolution.insert_one({
        "genes_code": "120",
        "account": "2111100163",
        "client_name": "PROEF EURICO FERREIRA QA51",
        "periods": {"03-2026": 100, "06-2026": 150},
        "evolution": {"03-2026": 100, "06-2026": 150},
        "updated_at": now,
    })
    await db.finance_actions.insert_one({"id": "qa51-action", "client_id": "qa51-dup-120", "created_at": now})
    await db.finance_promises.insert_one({"id": "qa51-promise", "client_id": "qa51-dup-120", "status": "open", "created_at": now})
    await db.finance_tasks.insert_one({"id": "qa51-task", "client_id": "qa51-dup-120", "created_at": now})
    await db.finance_block_requests.insert_one({"id": "qa51-block-request", "client_id": "qa51-dup-120", "status": "pending", "suggested_at": now})


async def check_exact_codpersona_duplicate_merge():
    print("[2] Checking merge script handles existing CodPersona duplicate 120 -> master 163")
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[TEST_DB_NAME]
    await client.drop_database(TEST_DB_NAME)
    await seed_exact_codpersona_duplicate(db)

    env = os.environ.copy()
    env["MONGO_URL"] = MONGO_URL
    env["DB_NAME"] = TEST_DB_NAME
    r = subprocess.run([sys.executable, SCRIPT, "--confirm"], env=env, capture_output=True, text=True, timeout=60)
    print("    merge stdout:\n" + r.stdout)
    if r.stderr:
        print("    merge stderr:\n" + r.stderr)
    assert r.returncode == 0, r.stderr

    master = await db.finance_clients.find_one({"id": "qa51-master-163"})
    dup = await db.finance_clients.find_one({"id": "qa51-dup-120"})
    evo_163 = await db.finance_credit_evolution.find_one({"genes_code": "163"})
    evo_120 = await db.finance_credit_evolution.find_one({"genes_code": "120"})
    action_on_master = await db.finance_actions.find_one({"id": "qa51-action", "client_id": "qa51-master-163"})
    promise_on_master = await db.finance_promises.find_one({"id": "qa51-promise", "client_id": "qa51-master-163"})
    task_on_master = await db.finance_tasks.find_one({"id": "qa51-task", "client_id": "qa51-master-163"})
    block_request_on_master = await db.finance_block_requests.find_one({"id": "qa51-block-request", "client_id": "qa51-master-163"})

    failures = []
    if not dup.get("is_merged_duplicate"):
        failures.append("duplicate genes_code=120 was not marked is_merged_duplicate")
    if dup.get("merged_into") != "qa51-master-163":
        failures.append("duplicate genes_code=120 was not linked to master 163")
    if master.get("carteira") != 44109.18:
        failures.append("master 163 did not receive enrichment from duplicate 120")
    if evo_163 is None or evo_120 is not None:
        failures.append("credit evolution was not remapped from genes_code 120 to 163")
    if action_on_master is None:
        failures.append("finance_actions client_id was not remapped from duplicate 120 to master 163")
    if promise_on_master is None:
        failures.append("finance_promises client_id was not remapped from duplicate 120 to master 163")
    if task_on_master is None:
        failures.append("finance_tasks client_id was not remapped from duplicate 120 to master 163")
    if block_request_on_master is None:
        failures.append("finance_block_requests client_id was not remapped from duplicate 120 to master 163")

    await client.drop_database(TEST_DB_NAME)
    client.close()

    if failures:
        print("    FAILURES:")
        for f in failures:
            print("      - " + f)
    else:
        print("    PASS: existing CodPersona duplicate 120 merged into 163")
    return failures


def main():
    failures = []
    failures.extend(check_parsers())
    failures.extend(asyncio.run(check_exact_codpersona_duplicate_merge()))
    if failures:
        raise SystemExit("Focused verification failed:\n- " + "\n- ".join(failures))


if __name__ == "__main__":
    main()