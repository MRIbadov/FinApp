from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from sqlalchemy.sql import func
from database import Base


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(String(50), unique=True, index=True, nullable=False)
    bank_name = Column(String(100), nullable=False)
    account_name = Column(String(150), nullable=False)
    region = Column(String(100), nullable=False)
    currency = Column(String(10), nullable=False)
    entity = Column(String(100), nullable=False)


class Balance(Base):
    __tablename__ = "balances"

    id = Column(Integer, primary_key=True, index=True)
    report_date = Column(String(20), index=True, nullable=False)
    account_id = Column(String(50), index=True, nullable=False)
    opening_balance = Column(Float, nullable=False)
    closing_balance = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False)


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String(100), index=True, nullable=False)
    account_id = Column(String(50), index=True, nullable=False)
    transaction_date = Column(String(20), index=True, nullable=False)
    type = Column(String(20), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False)
    counterparty = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)


class ValidationError(Base):
    __tablename__ = "validation_errors"

    id = Column(Integer, primary_key=True, index=True)
    error_type = Column(String(100), nullable=False)
    severity = Column(String(50), nullable=False)
    details = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ReconciliationResult(Base):
    __tablename__ = "reconciliation_results"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(String(50), index=True, nullable=False)
    report_date = Column(String(20), index=True, nullable=False)
    opening_balance = Column(Float, nullable=False)
    total_inflows = Column(Float, nullable=False)
    total_outflows = Column(Float, nullable=False)
    expected_closing_balance = Column(Float, nullable=False)
    actual_closing_balance = Column(Float, nullable=False)
    difference = Column(Float, nullable=False)
    status = Column(String(20), nullable=False)


class ExceptionItem(Base):
    __tablename__ = "exceptions"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(String(50), index=True, nullable=False)
    report_date = Column(String(20), index=True, nullable=False)
    exception_type = Column(String(100), nullable=False)
    severity = Column(String(50), nullable=False)
    amount_difference = Column(Float, nullable=False)
    status = Column(String(50), nullable=False, default="Open")
    owner = Column(String(100), nullable=False, default="Unassigned")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(100), nullable=False)
    details = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
