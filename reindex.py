"""Retry Qdrant indexing from the PostgreSQL source of truth."""
from app.db import SessionLocal
from app.models import Invoice
from app.vector import index_invoice

with SessionLocal() as db:
    rows=db.query(Invoice).order_by(Invoice.id).all()
    failed=[]
    for row in rows:
        try: index_invoice(row)
        except Exception as e:
            failed.append(row.id); print(f"index failed for invoice record {row.id}: {type(e).__name__}")
    print(f"Indexed {len(rows)-len(failed)}/{len(rows)} PostgreSQL invoices; failed IDs: {failed}")
    if failed: raise SystemExit(1)
