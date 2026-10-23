import hashlib
from qdrant_client import QdrantClient, models as qm
from .config import settings

client=QdrantClient(url=settings.qdrant_url,timeout=5)
COLLECTION=settings.qdrant_collection

def embed(text: str) -> list[float]:
    import httpx
    try:
        r=httpx.post(settings.ollama_url.rstrip("/")+"/api/embeddings",json={"model":settings.ollama_embed_model,"prompt":text},timeout=30); r.raise_for_status()
        v=r.json()["embedding"]
        if not v: raise ValueError("Empty embedding")
        return v
    except Exception as e: raise RuntimeError("Embedding provider unavailable") from e
def ensure_collection(dim: int):
    if not client.collection_exists(COLLECTION):
        client.create_collection(COLLECTION,vectors_config=qm.VectorParams(size=dim,distance=qm.Distance.COSINE))
def record_text(row):
    return f"Invoice {row.invoice_number}, date {row.invoice_date}, amount {row.currency} {row.amount}, payment status {row.payment_status}."
def index_invoice(row):
    text=record_text(row); vector=embed(text); ensure_collection(len(vector))
    point_id=int(hashlib.sha256(f"invoice:{row.id}".encode()).hexdigest()[:15],16)
    client.upsert(COLLECTION,points=[qm.PointStruct(id=point_id,vector=vector,payload={"owner_id":row.customer_id,"record_id":row.id,"record_type":"invoice","text":text,"invoice_number":row.invoice_number})],wait=True)
def search(customer_id: int, query: str, limit=5):
    v=embed(query); ensure_collection(len(v))
    hits=client.search(COLLECTION,query_vector=v,query_filter=qm.Filter(must=[qm.FieldCondition(key="owner_id",match=qm.MatchValue(value=customer_id))]),limit=limit,with_payload=True)
    return [{"record_id":h.payload["record_id"],"record_type":h.payload["record_type"],"text":h.payload["text"],"score":h.score} for h in hits]
