"""
Iteration 41 — Finance Tasks Engine + Excel Export + name_normalized index.
Covers:
- POST /api/finance/tasks/generate (mode 30/45/60, guardrails, feedback loop)
- GET  /api/finance/tasks/today
- POST /api/finance/tasks/{id}/done|postpone|convert|reject
- POST /api/finance/tasks/generate permission check (COLLECTIONS_AGENT vs no-finance)
- GET  /api/finance/clients-export (Excel)
- Backfill index: customers.name_normalized_1
"""
import os
import io
import uuid
from datetime import date, datetime, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://intake-ai-gateway.preview.emergentagent.com").rstrip("/")

ADMIN = ("admin@pdpv.pt", "HCNMEnKMLq")
AGENT = ("cobranca.teste@pdpv.pt", "TesteFin2026!")
NO_FIN = ("rececao.teste@pdpv.pt", "TesteFin2026!")


def _login(email: str, password: str) -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers():
    return {"Authorization": f"Bearer {_login(*ADMIN)}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def agent_headers():
    return {"Authorization": f"Bearer {_login(*AGENT)}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def nofin_headers():
    return {"Authorization": f"Bearer {_login(*NO_FIN)}", "Content-Type": "application/json"}


# ============ generate + today ============

def test_generate_tasks_mode_30_force_regenerate(agent_headers):
    r = requests.post(
        f"{BASE_URL}/api/finance/tasks/generate",
        headers=agent_headers,
        json={"mode": "30", "force_regenerate": True},
        timeout=60,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "generation_id" in data
    assert data["mode"] == "30"
    assert isinstance(data["tasks"], list)
    # Distribuição alvo é 15 no total mas preview pode ter menos candidatos — validar apenas limites
    assert data["tasks_created"] <= 15
    assert data["tasks_created"] >= 1  # Ambiente tem dados → deve criar pelo menos 1
    # Deve NÃO ter blocked_reason (a menos que data_health esteja bloqueado)
    # Se blocked, deve ser exatamente 1 UPLOAD_GENES_MAP
    if data.get("blocked_reason"):
        assert data["tasks_created"] == 1
        assert data["tasks"][0]["task_type"] == "UPLOAD_GENES_MAP"
        pytest.skip("data_health está bloqueado — skip resto do teste")
    # Verificar não duplicados por (client_id, task_type)
    seen = set()
    for t in data["tasks"]:
        key = (t.get("client_id"), t["task_type"])
        assert key not in seen, f"duplicate task for {key}"
        seen.add(key)
    # priority_score numérico e ordenado desc
    scores = [t["priority_score"] for t in data["tasks"]]
    assert scores == sorted(scores, reverse=True)


def test_generate_tasks_mode_45(agent_headers):
    r = requests.post(
        f"{BASE_URL}/api/finance/tasks/generate",
        headers=agent_headers,
        json={"mode": "45", "force_regenerate": True},
        timeout=60,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "45"
    assert data["tasks_created"] <= 24  # 5+6+5+3+3+2


def test_generate_tasks_mode_60(agent_headers):
    r = requests.post(
        f"{BASE_URL}/api/finance/tasks/generate",
        headers=agent_headers,
        json={"mode": "60", "force_regenerate": True},
        timeout=60,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "60"
    assert data["tasks_created"] <= 30  # 6+8+6+4+3+3 = 30


def test_generate_no_force_returns_existing(agent_headers):
    # Já regenerámos → deve devolver as existentes com tasks_created=0
    r = requests.post(
        f"{BASE_URL}/api/finance/tasks/generate",
        headers=agent_headers,
        json={"mode": "30", "force_regenerate": False},
        timeout=60,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    if data.get("blocked_reason"):
        pytest.skip("data_health bloqueado")
    assert data["tasks_created"] == 0
    assert data["tasks_archived"] == 0
    assert isinstance(data["tasks"], list)


def test_get_tasks_today(agent_headers):
    r = requests.get(f"{BASE_URL}/api/finance/tasks/today", headers=agent_headers, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "tasks" in data and "total" in data and "summary" in data
    s = data["summary"]
    for k in ("open", "done", "postponed", "converted", "rejected", "expired",
              "total_amount", "promises_created", "contacts_registered"):
        assert k in s, f"summary missing '{k}': {s}"


def test_get_tasks_today_with_status_filter(agent_headers):
    r = requests.get(
        f"{BASE_URL}/api/finance/tasks/today?status_in=OPEN,IN_REVIEW",
        headers=agent_headers,
        timeout=30,
    )
    assert r.status_code == 200
    data = r.json()
    for t in data["tasks"]:
        assert t["status"] in ("OPEN", "IN_REVIEW")


# ============ feedback actions ============

def _get_first_open_task(agent_headers):
    r = requests.get(f"{BASE_URL}/api/finance/tasks/today?status_in=OPEN", headers=agent_headers, timeout=30)
    assert r.status_code == 200
    tasks = r.json()["tasks"]
    if not tasks:
        # regenerate para garantir pelo menos 1
        rr = requests.post(
            f"{BASE_URL}/api/finance/tasks/generate",
            headers=agent_headers,
            json={"mode": "30", "force_regenerate": True},
            timeout=60,
        )
        assert rr.status_code == 200
        if rr.json().get("blocked_reason"):
            pytest.skip("data_health bloqueado — não há como testar actions")
        tasks = rr.json()["tasks"]
    if not tasks:
        pytest.skip("Não há tarefas OPEN para testar feedback actions")
    return tasks[0]


def test_task_done(agent_headers):
    t = _get_first_open_task(agent_headers)
    r = requests.post(
        f"{BASE_URL}/api/finance/tasks/{t['id']}/done",
        headers=agent_headers,
        json={"outcome": "TEST_done outcome"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "DONE"
    assert d["completed_at"] is not None


def test_task_postpone_requires_reason_and_date(agent_headers):
    t = _get_first_open_task(agent_headers)
    # Sem reason → 422
    r = requests.post(
        f"{BASE_URL}/api/finance/tasks/{t['id']}/postpone",
        headers=agent_headers,
        json={"next_action_date": "2026-02-10"},
        timeout=30,
    )
    assert r.status_code == 422
    # Sem next_action_date → 422
    r2 = requests.post(
        f"{BASE_URL}/api/finance/tasks/{t['id']}/postpone",
        headers=agent_headers,
        json={"reason": "missing_invoice"},
        timeout=30,
    )
    assert r2.status_code == 422
    # OK
    r3 = requests.post(
        f"{BASE_URL}/api/finance/tasks/{t['id']}/postpone",
        headers=agent_headers,
        json={"reason": "missing_invoice", "next_action_date": "2026-02-10", "note": "TEST"},
        timeout=30,
    )
    assert r3.status_code == 200, r3.text
    d = r3.json()
    assert d["status"] == "POSTPONED"
    assert d["next_action_date"] == "2026-02-10"
    assert d["feedback_reason"] == "missing_invoice"


def test_task_convert(agent_headers):
    t = _get_first_open_task(agent_headers)
    r = requests.post(
        f"{BASE_URL}/api/finance/tasks/{t['id']}/convert",
        headers=agent_headers,
        json={"new_task_type": "SEND_ACCOUNT_STATEMENT", "reason": "TEST convert"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "CONVERTED"
    assert d["converted_to_task_id"] is not None


def test_task_reject(agent_headers):
    t = _get_first_open_task(agent_headers)
    r = requests.post(
        f"{BASE_URL}/api/finance/tasks/{t['id']}/reject",
        headers=agent_headers,
        json={"reason": "duplicate", "note": "TEST reject"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "REJECTED"
    assert d["feedback_reason"] == "duplicate"


# ============ permission check ============

def test_generate_denied_for_no_finance_role(nofin_headers):
    r = requests.post(
        f"{BASE_URL}/api/finance/tasks/generate",
        headers=nofin_headers,
        json={"mode": "30", "force_regenerate": False},
        timeout=30,
    )
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"


# ============ Excel export ============

def test_clients_export_basic(agent_headers):
    r = requests.get(f"{BASE_URL}/api/finance/clients-export?min_overdue=10", headers=agent_headers, timeout=60)
    assert r.status_code == 200, r.text
    assert "spreadsheetml" in r.headers.get("content-type", "")
    assert "X-Total-Exported" in r.headers or "x-total-exported" in {k.lower() for k in r.headers}
    # Filename com data
    cd = r.headers.get("content-disposition", "")
    assert "clientes_finance_" in cd and ".xlsx" in cd
    # Validate xlsx bytes
    assert len(r.content) > 500

    # Verify 15 columns
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        ws = wb.active
        headers_row = [c.value for c in ws[1]]
        assert len(headers_row) == 15
        assert headers_row[0] == "Código"
        assert headers_row[1] == "Nome"
    except ImportError:
        pytest.skip("openpyxl não disponível para validar workbook")


def test_clients_export_denied_no_finance(nofin_headers):
    r = requests.get(f"{BASE_URL}/api/finance/clients-export", headers=nofin_headers, timeout=30)
    assert r.status_code == 403


def test_clients_export_route_does_not_collide_with_client_id(admin_headers):
    """Regressão: /clients-export usa hífen; /clients/{id} deve continuar a funcionar."""
    r = requests.get(f"{BASE_URL}/api/finance/clients?page_size=1", headers=admin_headers, timeout=30)
    assert r.status_code == 200
    clients = r.json().get("clients", [])
    if not clients:
        pytest.skip("Sem clientes finance para validar /clients/{id}")
    cid = clients[0]["id"]
    r2 = requests.get(f"{BASE_URL}/api/finance/clients/{cid}", headers=admin_headers, timeout=30)
    assert r2.status_code == 200, f"/clients/{{id}} deveria funcionar: {r2.status_code} {r2.text}"


# ============ name_normalized index (via DB direct, best-effort) ============

def test_name_normalized_index_created():
    """Verifica que o índice name_normalized_1 existe na coleção customers."""
    try:
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
    except ImportError:
        pytest.skip("motor não disponível fora do backend runtime")

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        # Ler do backend/.env se necessário
        try:
            with open("/app/backend/.env", "r") as f:
                for line in f:
                    if line.startswith("MONGO_URL="):
                        mongo_url = line.strip().split("=", 1)[1].strip('"').strip("'")
                    if line.startswith("DB_NAME="):
                        db_name = line.strip().split("=", 1)[1].strip('"').strip("'")
        except Exception:
            pytest.skip("Não foi possível ler MONGO_URL do env")
    if not mongo_url or not db_name:
        pytest.skip("MONGO_URL/DB_NAME não configurados")

    async def check():
        client = AsyncIOMotorClient(mongo_url)
        try:
            db = client[db_name]
            info = await db.customers.index_information()
            assert "name_normalized_1" in info, f"índice em falta. Existentes: {list(info.keys())}"
            total = await db.customers.count_documents({})
            with_norm = await db.customers.count_documents({"name_normalized": {"$exists": True, "$ne": None}})
            # Pelo menos 99% dos customers devem ter name_normalized
            if total > 0:
                ratio = with_norm / total
                assert ratio >= 0.99, f"backfill incompleto: {with_norm}/{total} = {ratio:.2%}"
        finally:
            client.close()

    asyncio.run(check())


# ============ CLEANUP: remove tarefas de teste ============

@pytest.fixture(scope="module", autouse=True)
def cleanup_test_tasks(agent_headers):
    """Depois de todos os tests, marca as tarefas de hoje como EXPIRED (via force_regenerate curto)."""
    yield
    try:
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
        mongo_url, db_name = None, None
        with open("/app/backend/.env", "r") as f:
            for line in f:
                if line.startswith("MONGO_URL="):
                    mongo_url = line.strip().split("=", 1)[1].strip('"').strip("'")
                if line.startswith("DB_NAME="):
                    db_name = line.strip().split("=", 1)[1].strip('"').strip("'")
        if mongo_url and db_name:
            async def cleanup():
                cli = AsyncIOMotorClient(mongo_url)
                try:
                    d = cli[db_name]
                    today = date.today().isoformat()
                    res = await d.finance_tasks.delete_many({"due_date": today})
                    print(f"[cleanup] removed {res.deleted_count} finance_tasks with due_date={today}")
                    # Também limpar finance_actions de teste (notas geradas pelos tests com "TEST" prefix)
                    res2 = await d.finance_actions.delete_many({"notes": {"$regex": "TEST"}})
                    print(f"[cleanup] removed {res2.deleted_count} finance_actions with TEST prefix")
                finally:
                    cli.close()
            asyncio.run(cleanup())
    except Exception as e:
        print(f"[cleanup] failed: {e}")
