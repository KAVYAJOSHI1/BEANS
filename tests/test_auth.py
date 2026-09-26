"""Login, roles and the four-eyes approval of legal drafts."""
import pytest
from fastapi.testclient import TestClient

PW = "correct-horse-battery"


@pytest.fixture(scope="module")
def app_db(tmp_path_factory, dataset):
    from beans.config import settings
    settings.DB_PATH = tmp_path_factory.mktemp("db") / "auth.duckdb"
    from beans.api.main import app
    from beans.ingest.pipeline import ForensicPipeline
    from beans.store.duck import DuckStore
    ForensicPipeline(DuckStore(settings.DB_PATH)).load_sidecars(dataset)
    c = TestClient(app)
    with open(dataset / "transactions.csv", "rb") as fh:   # ingest while still in single-user mode
        assert c.post("/api/ingest/upload", files={"file": ("f.csv", fh, "text/csv")}).status_code == 200
    assert c.get("/api/auth/me").json() == {"auth_enabled": False, "user": c.get("/api/auth/me").json()["user"],
                                            "roles": ["VIEWER", "ANALYST", "SUPERVISOR", "ADMIN"]}
    from beans.api import auth
    conn = DuckStore().get_connection()
    for name, role in (("admin", "ADMIN"), ("ana", "ANALYST"), ("sup", "SUPERVISOR"), ("sup2", "SUPERVISOR"), ("vic", "VIEWER")):
        auth.create_user(conn, name, PW, role)
    with pytest.raises(ValueError):
        auth.create_user(conn, "weak", "short", "ANALYST")
    conn.close()
    return app


def _login(app, user):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": user, "password": PW})
    assert r.status_code == 200, r.text
    return c


def test_login_required_once_users_exist(app_db):
    anon = TestClient(app_db)
    assert anon.get("/api/alerts").status_code == 401
    assert anon.get("/api/health").status_code == 200 and anon.get("/api/config").status_code == 200
    assert anon.get("/api/auth/me").json()["user"] is None
    assert anon.post("/api/auth/login", json={"username": "ana", "password": "nope-nope-nope"}).status_code == 401
    ana = _login(app_db, "ana")
    assert ana.get("/api/alerts").status_code == 200
    assert ana.get("/api/auth/me").json()["user"]["role"] == "ANALYST"
    assert ana.post("/api/auth/logout").status_code == 200
    assert ana.get("/api/alerts").status_code == 401


def test_lockout_after_repeated_failures(app_db):
    c = TestClient(app_db)
    for _ in range(5):
        assert c.post("/api/auth/login", json={"username": "vic", "password": "wrong-password"}).status_code == 401
    assert c.post("/api/auth/login", json={"username": "vic", "password": PW}).status_code == 429
    from beans.api import auth
    auth._failures.clear()


def test_roles(app_db):
    vic, ana, sup, admin = (_login(app_db, u) for u in ("vic", "ana", "sup", "admin"))
    a = vic.get("/api/alerts").json()[0]
    assert vic.patch(f"/api/alerts/{a['alert_id']}/status", json={"status": "INVESTIGATING"}).status_code == 403
    assert ana.patch(f"/api/alerts/{a['alert_id']}/status", json={"status": "INVESTIGATING"}).status_code == 200
    hook = {"url": "http://127.0.0.1:9/", "fmt": "json"}
    assert ana.post("/api/webhooks", json=hook).status_code == 403
    h = sup.post("/api/webhooks", json=hook).json()
    sup.delete(f"/api/webhooks/{h['id']}")
    assert sup.get("/api/users").status_code == 403
    assert admin.post("/api/users", json={"username": "newbie", "password": PW, "role": "ANALYST"}).status_code == 200
    assert admin.patch("/api/users/admin", json={"active": False}).status_code == 409
    assert admin.patch("/api/users/newbie", json={"active": False}).status_code == 200
    assert TestClient(app_db).post("/api/auth/login", json={"username": "newbie", "password": PW}).status_code == 401
    audit = admin.get("/api/audit").json()
    assert any(r["action"] == "ALERT_STATUS" and r["investigator"] == "ana" for r in audit)


def test_four_eyes_approval_of_legal_drafts(app_db):
    ana, sup = _login(app_db, "ana"), _login(app_db, "sup")
    alert = next(x for x in ana.get("/api/alerts?limit=1000").json()
                 if any(h["in_jurisdiction"] for h in x["recommended_action"].get("vasp_exposure", [])))
    r = ana.post(f"/api/alerts/{alert['alert_id']}/legal/section94", json={"fir_no": "7/2026"}).json()
    req = r["request"]
    assert req["status"] == "PENDING_APPROVAL" and req["created_by"] == "ana"
    assert "PENDING SUPERVISOR APPROVAL" in r["html"]
    assert ana.post(f"/api/legal-requests/{req['id']}/decision", json={"decision": "APPROVE"}).status_code == 403
    assert sup.post(f"/api/legal-requests/{req['id']}/decision", json={"decision": "REJECT"}).status_code == 422
    ok = sup.post(f"/api/legal-requests/{req['id']}/decision", json={"decision": "APPROVE", "comment": "checked"}).json()
    assert ok["status"] == "APPROVED" and ok["decided_by"] == "sup"
    doc = ana.get(f"/api/legal-requests/{req['id']}?fmt=html").text
    assert "APPROVED FOR ISSUE by supervisor sup" in doc and "PENDING" not in doc
    assert sup.post(f"/api/legal-requests/{req['id']}/decision", json={"decision": "REJECT", "comment": "x"}).status_code == 409

    # a supervisor's own draft needs a different supervisor
    mine = sup.post(f"/api/alerts/{alert['alert_id']}/legal/section94", json={}).json()["request"]
    assert sup.post(f"/api/legal-requests/{mine['id']}/decision", json={"decision": "APPROVE"}).status_code == 403
    sup2 = _login(app_db, "sup2")
    rej = sup2.post(f"/api/legal-requests/{mine['id']}/decision", json={"decision": "REJECT", "comment": "wrong FIR"}).json()
    assert rej["status"] == "REJECTED"
    assert "REJECTED by sup2: wrong FIR" in sup.get(f"/api/legal-requests/{mine['id']}?fmt=html").text
    assert {x["status"] for x in sup.get("/api/legal-requests").json()} == {"APPROVED", "REJECTED"}
