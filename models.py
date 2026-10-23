from datetime import datetime, timezone
from sqlalchemy import String, Integer, Date, DateTime, Numeric, ForeignKey, Text, UniqueConstraint, Index, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

def now(): return datetime.now(timezone.utc)
class Base(DeclarativeBase): pass

class Customer(Base):
    __tablename__="customers"
    id: Mapped[int]=mapped_column(primary_key=True)
    name: Mapped[str]=mapped_column(String(100), nullable=False)
    mobile: Mapped[str]=mapped_column(String(16), unique=True, nullable=False)
    invoices: Mapped[list["Invoice"]]=relationship(back_populates="customer")
class Invoice(Base):
    __tablename__="invoices"
    __table_args__=(UniqueConstraint("customer_id","invoice_number",name="uq_invoice_customer_number"),)
    id: Mapped[int]=mapped_column(primary_key=True)
    customer_id: Mapped[int]=mapped_column(ForeignKey("customers.id",ondelete="CASCADE"),nullable=False,index=True)
    invoice_number: Mapped[str]=mapped_column(String(50),nullable=False)
    invoice_date: Mapped[object]=mapped_column(Date,nullable=False)
    amount: Mapped[object]=mapped_column(Numeric(12,2),nullable=False)
    currency: Mapped[str]=mapped_column(String(3),nullable=False)
    payment_status: Mapped[str]=mapped_column(String(16),nullable=False)
    customer: Mapped[Customer]=relationship(back_populates="invoices")
class Conversation(Base):
    __tablename__="conversations"
    id: Mapped[int]=mapped_column(primary_key=True)
    customer_id: Mapped[int]=mapped_column(ForeignKey("customers.id",ondelete="CASCADE"),nullable=False,index=True)
    title: Mapped[str]=mapped_column(String(160),default="New conversation")
    pending_invoice: Mapped[dict|None]=mapped_column(JSON,nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Message(Base):
    __tablename__="messages"
    id: Mapped[int]=mapped_column(primary_key=True)
    conversation_id: Mapped[int]=mapped_column(ForeignKey("conversations.id",ondelete="CASCADE"),nullable=False,index=True)
    role: Mapped[str]=mapped_column(String(16),nullable=False)
    content: Mapped[str]=mapped_column(Text,nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class OTPChallenge(Base):
    __tablename__="otp_challenges"
    id: Mapped[int]=mapped_column(primary_key=True)
    mobile: Mapped[str]=mapped_column(String(16),nullable=False,index=True)
    code_hash: Mapped[str]=mapped_column(String(64),nullable=False)
    expires_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    sent_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    attempts: Mapped[int]=mapped_column(Integer,default=0)
    used_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
Index("ix_messages_conversation_created",Message.conversation_id,Message.created_at)
