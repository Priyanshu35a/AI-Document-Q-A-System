import pytest

def get_auth_headers(client):
    signup_res = client.post("/api/auth/signup", json={
        "username": "api_test_user",
        "email": "api_test@example.com",
        "password": "Password123!"
    })
    token = signup_res.json()["token"]
    return {"Authorization": f"Bearer {token}"}

def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "database" in data
    assert "embedding_model" in data

def test_upload_non_pdf_file(client):
    headers = get_auth_headers(client)
    files = {"file": ("test.txt", b"Hello world", "text/plain")}
    response = client.post("/api/documents/upload", files=files, headers=headers)
    assert "Supported formats" in response.json()["detail"]

def test_upload_empty_pdf_file(client):
    headers = get_auth_headers(client)
    files = {"file": ("empty.pdf", b"", "application/pdf")}
    response = client.post("/api/documents/upload", files=files, headers=headers)
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()

def test_chat_without_documents(client):
    headers = get_auth_headers(client)
    response = client.post("/api/chat", json={"question": "What is in the document?"}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "No documents have been uploaded" in data["answer"]
    assert len(data["citations"]) == 0

def test_chat_history_and_clear(client):
    headers = get_auth_headers(client)
    # Fetch history initially
    res1 = client.get("/api/chat/history", headers=headers)
    assert res1.status_code == 200
    assert isinstance(res1.json(), list)

    # Clear history
    res2 = client.delete("/api/chat/history", headers=headers)
    assert res2.status_code == 200
    assert res2.json()["status"] == "success"
