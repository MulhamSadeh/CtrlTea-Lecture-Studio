import pytest
from fastapi.testclient import TestClient
from ctrltea import store
from ctrltea.api import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    with TestClient(app) as c:
        yield c


@pytest.fixture
def lecture(client):
    c = client.post("/api/courses", json={"name": "التحكم الآلي", "doctor": "اسم الدكتور"}).json()
    l = client.post(
        f'/api/courses/{c["id"]}/lectures', json={"title": "الإشارات وتحويل لابلاس"}
    ).json()
    return c, l
