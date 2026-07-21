"""Guardrail tests: data_health blocking mode."""
import asyncio
import os
import requests
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = "https://intake-ai-gateway.preview.emergentagent.com"

def get_env():
    mongo_url, db_name = None, None
    with open("/app/backend/.env", "r") as f:
        for line in f:
            if line.startswith("MONGO_URL="):
                mongo_url = line.strip().split("=", 1)[1].strip('"').strip("'")
            if line.startswith("DB_NAME="):
                db_name = line.strip().split("=", 1)[1].strip('"').strip("'")
    return mongo_url, db_name


def login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    return r.json()["token"]


async def test_data_health_guardrail():
    mongo_url, db_name = get_env()
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    token = login("cobranca.teste@pdpv.pt", "TesteFin2026!")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    marker_id = "TEST_HEALTH_GUARDRAIL"
    try:
        # Inserir doc temporário em finance_data_health com blocking_collections=True
        await db.finance_data_health.insert_one({
            "id": marker_id,
            "type": "overdue_balances",
            "as_of_date": "2020-01-01",
            "blocking_collections": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        print("[setup] inserted blocking finance_data_health doc")

        r = requests.post(
            f"{BASE_URL}/api/finance/tasks/generate",
            headers=headers,
            json={"mode": "30", "force_regenerate": True},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        print(f"[result] tasks_created={data['tasks_created']} blocked_reason={data.get('blocked_reason')}")
        assert data.get("blocked_reason"), "esperava blocked_reason mas veio None"
        assert data["tasks_created"] == 1, f"esperava 1 task, veio {data['tasks_created']}"
        assert len(data["tasks"]) == 1
        upload_task = data["tasks"][0]
        assert upload_task["task_type"] == "UPLOAD_GENES_MAP", f"veio {upload_task['task_type']}"
        assert upload_task["priority_score"] == 999.0
        assert upload_task["client_id"] is None
        print("[PASS] data_health guardrail correcto: UPLOAD_GENES_MAP com priority=999")
    finally:
        # Limpar marker + limpar UPLOAD_GENES_MAP task criada
        await db.finance_data_health.delete_one({"id": marker_id})
        from datetime import date
        await db.finance_tasks.delete_many({
            "due_date": date.today().isoformat(),
            "task_type": "UPLOAD_GENES_MAP",
        })
        print("[cleanup] removed marker + UPLOAD_GENES_MAP tasks")
        client.close()

asyncio.run(test_data_health_guardrail())
print("DONE")
