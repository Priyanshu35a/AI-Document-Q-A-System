import pytest
from app.db.models import User, Document, Chunk

def test_signup_and_login_flow(client):
    # 1. Sign up Alice
    signup_payload = {
        "username": "alice",
        "email": "alice@example.com",
        "password": "Password123!"
    }
    res = client.post("/api/auth/signup", json=signup_payload)
    assert res.status_code == 201
    data = res.json()
    assert "token" in data
    assert data["user"]["username"] == "alice"
    token = data["token"]

    # 2. Get profile /me
    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "alice@example.com"

    # 3. Duplicate signup rejected
    dup_res = client.post("/api/auth/signup", json=signup_payload)
    assert dup_res.status_code == 400

    # 4. Login Alice
    login_res = client.post("/api/auth/login", json={"identifier": "alice@example.com", "password": "Password123!"})
    assert login_res.status_code == 200
    assert "token" in login_res.json()

    # 5. Bad password rejected
    bad_login = client.post("/api/auth/login", json={"identifier": "alice@example.com", "password": "WrongPassword"})
    assert bad_login.status_code == 401

def test_multi_user_data_isolation(client, test_db):
    # Register Alice
    res_a = client.post("/api/auth/signup", json={
        "username": "alice_iso",
        "email": "alice_iso@example.com",
        "password": "Password123!"
    })
    token_a = res_a.json()["token"]
    user_a_id = res_a.json()["user"]["id"]

    # Register Bob
    res_b = client.post("/api/auth/signup", json={
        "username": "bob_iso",
        "email": "bob_iso@example.com",
        "password": "Password123!"
    })
    token_b = res_b.json()["token"]

    # Manually create a document belonging to Alice
    alice_doc = Document(
        user_id=user_a_id,
        filename="alice_secret_report.pdf",
        file_path="uploads/alice_secret.pdf",
        file_size=1024,
        page_count=2,
        chunk_count=3
    )
    test_db.add(alice_doc)
    test_db.commit()
    test_db.refresh(alice_doc)
    doc_id = alice_doc.id

    # Alice lists documents -> sees her document
    alice_docs_res = client.get("/api/documents", headers={"Authorization": f"Bearer {token_a}"})
    assert alice_docs_res.status_code == 200
    alice_docs = alice_docs_res.json()
    assert len(alice_docs) == 1
    assert alice_docs[0]["filename"] == "alice_secret_report.pdf"

    # Bob lists documents -> sees 0 documents!
    bob_docs_res = client.get("/api/documents", headers={"Authorization": f"Bearer {token_b}"})
    assert bob_docs_res.status_code == 200
    bob_docs = bob_docs_res.json()
    assert len(bob_docs) == 0

    # Bob attempts to delete Alice's document -> 404 Not Found!
    del_res = client.delete(f"/api/documents/{doc_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert del_res.status_code == 404

    # Alice can delete her own document
    del_alice_res = client.delete(f"/api/documents/{doc_id}", headers={"Authorization": f"Bearer {token_a}"})
    assert del_alice_res.status_code == 200
