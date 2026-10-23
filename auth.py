import base64, hashlib, hmac, json, re, secrets, time
from datetime import datetime, timezone, timedelta
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db
from .models import Customer

def normalize_mobile(mobile: str) -> str:
    digits=re.sub(r"\D", "", mobile)
    if len(digits)==10: digits="91"+digits
    if not re.fullmatch(r"91[6-9]\d{9}",digits): raise HTTPException(422,"Enter a valid Indian mobile number")
    return "+"+digits
def issue_token(customer_id: int) -> str:
    payload={"sub":customer_id,"exp":int(time.time())+settings.access_token_ttl_seconds}
    raw=base64.urlsafe_b64encode(json.dumps(payload,separators=(",",":")).encode()).rstrip(b"=")
    sig=hmac.new(settings.token_secret.encode(),raw,hashlib.sha256).digest()
    return raw.decode()+"."+base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
def get_current_customer(authorization: str|None=Header(default=None), db: Session=Depends(get_db)) -> Customer:
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(401,"Authentication required")
    try:
        raw,sig=authorization[7:].split(".",1); expected=base64.urlsafe_b64encode(hmac.new(settings.token_secret.encode(),raw.encode(),hashlib.sha256).digest()).rstrip(b"=").decode()
        if not hmac.compare_digest(sig,expected): raise ValueError()
        payload=json.loads(base64.urlsafe_b64decode(raw+"="*(-len(raw)%4)))
        if payload["exp"]<time.time(): raise ValueError()
        customer=db.get(Customer,int(payload["sub"]))
        if not customer: raise ValueError()
        return customer
    except Exception: raise HTTPException(401,"Invalid or expired access token")
def otp_hash(mobile, code): return hmac.new(settings.otp_secret.encode(),f"{mobile}:{code}".encode(),hashlib.sha256).hexdigest()
def generate_otp(): return f"{secrets.randbelow(1_000_000):06d}"
def deliver_dev_otp(mobile,code):
    if settings.app_env!="development" or not settings.dev_otp_delivery: raise RuntimeError("OTP delivery provider is not configured")
    from pathlib import Path
    path=Path(settings.dev_otp_file); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a",encoding="utf-8") as f: f.write(f"{datetime.now(timezone.utc).isoformat()} {mobile} {code}\n")
