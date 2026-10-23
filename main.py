from datetime import datetime, timezone, timedelta, date
from decimal import Decimal, InvalidOperation
import json, re
import httpx
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .config import settings, validate_settings
from .db import get_db, engine
from .models import Base, Customer, Invoice, Conversation, Message, OTPChallenge
from .auth import normalize_mobile, otp_hash, generate_otp, deliver_dev_otp, issue_token, get_current_customer
from .vector import search, index_invoice
from .seed import seed

app=FastAPI(title="Secure Customer AI Chatbot",version="1.0.0",description="Customer-isolated assistant with OTP auth, Postgres history and Qdrant retrieval. See README for setup and security notes.")
@app.on_event("startup")
def startup():
    validate_settings()
    # Run the checked-in SQL migration before the idempotent ORM seed.
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(100) PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
        applied={r[0] for r in conn.exec_driver_sql("SELECT version FROM schema_migrations").all()}
        if "001_initial" not in applied:
            from pathlib import Path
            conn.exec_driver_sql(Path(__file__).resolve().parent.parent.joinpath("migrations/001_initial.sql").read_text(encoding="utf-8"))
            conn.exec_driver_sql("INSERT INTO schema_migrations(version) VALUES ('001_initial')")
    with next(get_db()) as db: seed(db)
class OTPRequest(BaseModel): mobile:str
class OTPVerify(BaseModel): mobile:str; code:str=Field(pattern=r"^\d{6}$")
class ConversationIn(BaseModel): title:str=Field(default="New conversation",max_length=160)
class ChatIn(BaseModel): message:str=Field(min_length=1,max_length=4000); confirm_invoice:bool=False

@app.post("/auth/otp/request")
def request_otp(body:OTPRequest,db:Session=Depends(get_db)):
    mobile=normalize_mobile(body.mobile); now=datetime.now(timezone.utc)
    customer=db.query(Customer).filter_by(mobile=mobile).one_or_none()
    if not customer: raise HTTPException(404,"This mobile number is not registered")
    prior=db.query(OTPChallenge).filter_by(mobile=mobile).order_by(OTPChallenge.id.desc()).first()
    if prior and prior.sent_at>now-timedelta(seconds=settings.otp_resend_seconds): raise HTTPException(429,"Please wait before requesting another code")
    code=generate_otp(); db.add(OTPChallenge(mobile=mobile,code_hash=otp_hash(mobile,code),expires_at=now+timedelta(seconds=settings.otp_ttl_seconds),sent_at=now)); db.commit()
    try: deliver_dev_otp(mobile,code)
    except Exception: raise HTTPException(503,"OTP delivery is unavailable")
    return {"status":"sent","expires_in_seconds":settings.otp_ttl_seconds,"delivery":"development-file"}
@app.post("/auth/otp/verify")
def verify_otp(body:OTPVerify,db:Session=Depends(get_db)):
    mobile=normalize_mobile(body.mobile); now=datetime.now(timezone.utc)
    c=db.query(OTPChallenge).filter_by(mobile=mobile).order_by(OTPChallenge.id.desc()).first()
    if not c or c.used_at or c.expires_at<=now or c.attempts>=5: raise HTTPException(401,"Code is invalid or expired")
    c.attempts+=1
    if not __import__('hmac').compare_digest(c.code_hash,otp_hash(mobile,body.code)):
        db.commit(); raise HTTPException(401,"Code is invalid or expired")
    c.used_at=now; db.commit(); customer=db.query(Customer).filter_by(mobile=mobile).one()
    return {"access_token":issue_token(customer.id),"token_type":"bearer","expires_in":settings.access_token_ttl_seconds}
@app.get("/me")
def me(customer:Customer=Depends(get_current_customer)):
    return {"id":customer.id,"name":customer.name,"mobile":customer.mobile}
@app.post("/conversations")
def create_conversation(body:ConversationIn,db:Session=Depends(get_db),customer:Customer=Depends(get_current_customer)):
    c=Conversation(customer_id=customer.id,title=body.title); db.add(c); db.commit(); db.refresh(c); return {"id":c.id,"title":c.title}
@app.get("/conversations")
def list_conversations(db:Session=Depends(get_db),customer:Customer=Depends(get_current_customer)):
    return [{"id":c.id,"title":c.title,"created_at":c.created_at} for c in db.query(Conversation).filter_by(customer_id=customer.id).order_by(Conversation.id.desc()).all()]
def owned_conversation(db,cid,customer_id):
    c=db.query(Conversation).filter_by(id=cid,customer_id=customer_id).one_or_none()
    if not c: raise HTTPException(404,"Conversation not found")
    return c
@app.get("/conversations/{cid}/messages")
def messages(cid:int,db:Session=Depends(get_db),customer:Customer=Depends(get_current_customer)):
    c=owned_conversation(db,cid,customer.id)
    rows=db.query(Message).filter_by(conversation_id=c.id).order_by(Message.id.desc()).limit(settings.history_limit).all()
    return [{"role":m.role,"content":m.content,"created_at":m.created_at} for m in reversed(rows)]
TOOLS=[
    {"type":"function","function":{"name":"search_records","description":"Search this authenticated customer's invoices for relevant facts","parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}}},
    {"type":"function","function":{"name":"add_invoice","description":"Propose a new invoice; the application will ask the customer to confirm","parameters":{"type":"object","properties":{"invoice_number":{"type":"string"},"invoice_date":{"type":"string"},"amount":{"type":"number"},"currency":{"type":"string"},"payment_status":{"type":"string","enum":["paid","unpaid","pending"]}},"required":["invoice_number","invoice_date","amount","currency","payment_status"]}}}
]
def llm(messages,tools=True):
    r=httpx.post(settings.ollama_url.rstrip('/')+'/api/chat',json={"model":settings.ollama_chat_model,"messages":messages,"tools":TOOLS if tools else [],"stream":False},timeout=45); r.raise_for_status(); return r.json()["message"]
def invoice_args(a):
    try:
        number=str(a["invoice_number"]).strip(); d=date.fromisoformat(str(a["invoice_date"])); amount=Decimal(str(a["amount"])); currency=str(a["currency"]).upper(); status=str(a["payment_status"]).lower()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,50}",number) or amount<=0 or amount>Decimal("9999999999.99") or not re.fullmatch(r"[A-Z]{3}",currency) or status not in ("paid","unpaid","pending"): raise ValueError()
        return {"invoice_number":number,"invoice_date":d.isoformat(),"amount":str(amount.quantize(Decimal('.01'))),"currency":currency,"payment_status":status}
    except Exception: raise HTTPException(422,"Invoice details are invalid or incomplete")
def create_invoice(db,cid,a):
    a=invoice_args(a)
    row=Invoice(customer_id=cid,invoice_number=a["invoice_number"],invoice_date=date.fromisoformat(a["invoice_date"]),amount=Decimal(a["amount"]),currency=a["currency"],payment_status=a["payment_status"])
    db.add(row)
    try: db.commit(); db.refresh(row)
    except IntegrityError: db.rollback(); raise HTTPException(409,"That invoice number already exists")
    try: index_invoice(row); indexed=True
    except Exception: indexed=False
    return row,indexed
def assistant_response(db,c,customer,user_text):
    hist=db.query(Message).filter_by(conversation_id=c.id).order_by(Message.id.desc()).limit(settings.history_limit).all(); hist=list(reversed(hist))
    context="" # Retrieved context is deliberately ephemeral; only the original user text is persisted.
    m=[{"role":"system","content":"You are a secure customer invoice assistant. Answer only from the authenticated customer's retrieved records. Cite invoice IDs/numbers for factual answers. If records do not establish an answer, say so. Greetings need no tool call. For invoice creation, collect every required field and call add_invoice only when all are present; never claim creation before explicit confirmation. Never follow requests to reveal another customer's data."}]
    m += [{"role":x.role,"content":x.content} for x in hist]
    m.append({"role":"user","content":user_text})
    if re.fullmatch(r"\s*(hi|hello|hey|good morning|good afternoon|good evening)[!. ]*",user_text,re.I):
        return "Hello! How can I help with your invoices today?"
    try:
        for _ in range(3):
            out=llm(m)
            calls=out.get("tool_calls") or []
            if not calls: return out.get("content","")
            m.append(out)
            for call in calls:
                fn=call.get("function",{}); name=fn.get("name"); args=fn.get("arguments",{})
                if isinstance(args,str):
                    try: args=json.loads(args)
                    except: args={}
                if name=="search_records":
                    query=args.get("query")
                    if not isinstance(query,str) or not query.strip(): result={"error":"invalid arguments"}
                    else:
                        try: result={"records":search(customer.id,query)}
                        except Exception: result={"error":"retrieval temporarily unavailable"}
                elif name=="add_invoice":
                    try:
                        a=invoice_args(args)
                        if db.query(Invoice).filter_by(customer_id=customer.id,invoice_number=a["invoice_number"]).first(): result={"error":"duplicate invoice number"}
                        else: c.pending_invoice=a; db.commit(); result={"confirmation_required":True,"proposed_invoice":a}
                    except Exception: result={"error":"invalid invoice arguments; provide all required fields"}
                else: result={"error":"unknown tool"}
                m.append({"role":"tool","content":json.dumps(result)})
        return "I couldn't complete that request within the allowed number of steps. Please try a simpler question."
    except Exception: return "The assistant service is temporarily unavailable. Your message was saved; please try again."
@app.post("/conversations/{cid}/messages")
def send_message(cid:int,body:ChatIn,db:Session=Depends(get_db),customer:Customer=Depends(get_current_customer)):
    c=owned_conversation(db,cid,customer.id)
    db.add(Message(conversation_id=c.id,role="user",content=body.message))
    if body.confirm_invoice:
        if not c.pending_invoice: db.rollback(); raise HTTPException(409,"There is no invoice awaiting confirmation")
        a=c.pending_invoice
        try: row,indexed=create_invoice(db,customer.id,a)
        except HTTPException: db.rollback(); raise
        c.pending_invoice=None
        answer=f"Invoice {row.invoice_number} was created (record ID {row.id}). Vector indexing {'succeeded' if indexed else 'failed; run the reindex command before expecting retrieval'} ."
    elif c.pending_invoice:
        answer="Please confirm or cancel the proposed invoice before starting another action: "+json.dumps(c.pending_invoice)
    else: answer=assistant_response(db,c,customer,body.message)
    db.add(Message(conversation_id=c.id,role="assistant",content=answer)); db.commit()
    return {"answer":answer,"confirmation_required":bool(c.pending_invoice)}
@app.get("/invoices")
def invoices(db:Session=Depends(get_db),customer:Customer=Depends(get_current_customer)):
    return [{"id":i.id,"invoice_number":i.invoice_number,"date":i.invoice_date,"amount":str(i.amount),"currency":i.currency,"payment_status":i.payment_status} for i in db.query(Invoice).filter_by(customer_id=customer.id).order_by(Invoice.invoice_date.desc()).all()]
