import pytest
from app.db.models import Document, Chunk

def test_sheets_endpoints_and_csv_export(client, test_db):
    # 1. Register test user
    signup_res = client.post("/api/auth/signup", json={
        "username": "sheet_user",
        "email": "sheet_user@example.com",
        "password": "Password123!"
    })
    token = signup_res.json()["token"]
    user_id = signup_res.json()["user"]["id"]
    auth_header = {"Authorization": f"Bearer {token}"}

    # 2. Add sample doc and chunks directly to test_db
    doc = Document(
        user_id=user_id,
        filename="financial_q3.pdf",
        file_path="uploads/financial_q3.pdf",
        file_size=204800,
        page_count=5,
        chunk_count=2
    )
    test_db.add(doc)
    test_db.commit()
    test_db.refresh(doc)

    c1 = Chunk(document_id=doc.id, page_number=1, chunk_index=0, content="Revenue rose by 34% to $42.5 million.", vector_id=1)
    c2 = Chunk(document_id=doc.id, page_number=2, chunk_index=1, content="Gross margin reached 72.4% with solid ARR.", vector_id=2)
    test_db.add_all([c1, c2])
    test_db.commit()

    # 3. Test /api/sheets/summary
    summary_res = client.get("/api/sheets/summary", headers=auth_header)
    assert summary_res.status_code == 200
    summary = summary_res.json()
    assert summary["total_documents"] == 1
    assert summary["total_chunks"] == 2
    assert summary["total_pages"] == 5

    # 4. Test /api/sheets/documents
    docs_sheet_res = client.get("/api/sheets/documents", headers=auth_header)
    assert docs_sheet_res.status_code == 200
    rows = docs_sheet_res.json()
    assert len(rows) == 1
    assert rows[0]["filename"] == "financial_q3.pdf"
    assert rows[0]["row_index"] == 1

    # 5. Test /api/sheets/chunks with search
    chunks_sheet_res = client.get("/api/sheets/chunks?search=Revenue", headers=auth_header)
    assert chunks_sheet_res.status_code == 200
    chunk_data = chunks_sheet_res.json()
    assert chunk_data["total"] == 1
    assert "Revenue rose" in chunk_data["rows"][0]["full_content"]

    # 6. Test /api/sheets/export-csv
    csv_res = client.get("/api/sheets/export-csv?sheet_type=chunks", headers=auth_header)
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    assert "financial_q3.pdf" in csv_res.text
    assert "Revenue rose" in csv_res.text
