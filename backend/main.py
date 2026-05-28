from fastapi import FastAPI, UploadFile, File, Depends, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pandas.errors import EmptyDataError, ParserError
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
import pandas as pd
from io import StringIO
from pathlib import Path
import time
from typing import Dict, List

from config import settings
from database import Base, engine, get_db
from models import (
    Account,
    Balance,
    Transaction,
    ValidationError,
    ReconciliationResult,
    ExceptionItem,
    AuditLog,
)


def initialize_database(max_attempts: int = 30, delay_seconds: int = 2):
    for attempt in range(1, max_attempts + 1):
        try:
            Base.metadata.create_all(bind=engine)
            remove_transaction_id_unique_indexes()
            return
        except OperationalError:
            if attempt == max_attempts:
                raise
            time.sleep(delay_seconds)


def remove_transaction_id_unique_indexes():
    if engine.dialect.name != "mysql":
        return

    with engine.begin() as connection:
        indexes = connection.execute(text("""
            SELECT DISTINCT INDEX_NAME
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'transactions'
              AND COLUMN_NAME = 'transaction_id'
              AND NON_UNIQUE = 0
              AND INDEX_NAME <> 'PRIMARY'
        """)).scalars().all()

        for index_name in indexes:
            safe_index_name = index_name.replace("`", "``")
            connection.execute(text(f"ALTER TABLE transactions DROP INDEX `{safe_index_name}`"))


initialize_database()

app = FastAPI(title="FinApp API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.allowed_origins.split(",")],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


def require_api_key(x_api_key: str = Header(default="")):
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


def read_csv_upload(file: UploadFile) -> pd.DataFrame:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are allowed",
        )

    try:
        content = file.file.read().decode("utf-8")
        df = pd.read_csv(StringIO(content)).fillna("")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file must be UTF-8 encoded",
        )
    except EmptyDataError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file is empty",
        )
    except ParserError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file could not be parsed",
        )

    if len(df) > settings.max_upload_rows:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File has too many rows. Maximum allowed rows: {settings.max_upload_rows}",
        )

    return df


def parse_amount(value, column_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Column '{column_name}' must contain numeric values",
        )


def clear_table(db: Session, model):
    db.query(model).delete()
    db.commit()


def add_audit_log(db: Session, action: str, entity_type: str, details: str):
    db.add(AuditLog(action=action, entity_type=entity_type, details=details))
    db.commit()


@app.get("/health")
def health_check():
    return {"status": "running", "message": "FinApp API with MySQL"}


@app.post("/upload/accounts", dependencies=[Depends(require_api_key)])
def upload_accounts(file: UploadFile = File(...), db: Session = Depends(get_db)):
    df = read_csv_upload(file)

    required_columns = ["account_id", "bank_name", "account_name", "region", "currency", "entity"]
    missing_columns = [col for col in required_columns if col not in df.columns]

    if missing_columns:
        return {
            "status": "failed",
            "message": "Missing required columns",
            "missing_columns": missing_columns,
        }

    clear_table(db, Account)

    for _, row in df.iterrows():
        db.add(Account(
            account_id=str(row["account_id"]),
            bank_name=str(row["bank_name"]),
            account_name=str(row["account_name"]),
            region=str(row["region"]),
            currency=str(row["currency"]),
            entity=str(row["entity"]),
        ))

    db.commit()
    add_audit_log(db, "File uploaded", "accounts", f"{len(df)} account rows uploaded")

    return {
        "status": "processed",
        "file_type": "accounts",
        "rows_processed": len(df),
    }


@app.post("/upload/balances", dependencies=[Depends(require_api_key)])
def upload_balances(file: UploadFile = File(...), db: Session = Depends(get_db)):
    df = read_csv_upload(file)

    required_columns = ["report_date", "account_id", "opening_balance", "closing_balance", "currency"]
    missing_columns = [col for col in required_columns if col not in df.columns]

    if missing_columns:
        return {
            "status": "failed",
            "message": "Missing required columns",
            "missing_columns": missing_columns,
        }

    balances = []
    for _, row in df.iterrows():
        balances.append(Balance(
            report_date=str(row["report_date"]),
            account_id=str(row["account_id"]),
            opening_balance=parse_amount(row["opening_balance"], "opening_balance"),
            closing_balance=parse_amount(row["closing_balance"], "closing_balance"),
            currency=str(row["currency"]),
        ))

    clear_table(db, Balance)
    db.add_all(balances)
    db.commit()
    add_audit_log(db, "File uploaded", "balances", f"{len(df)} balance rows uploaded")
    validate_data(db)
    run_reconciliation(db)

    return {
        "status": "processed",
        "file_type": "balances",
        "rows_processed": len(df),
    }


@app.post("/upload/transactions", dependencies=[Depends(require_api_key)])
def upload_transactions(file: UploadFile = File(...), db: Session = Depends(get_db)):
    df = read_csv_upload(file)

    required_columns = [
        "transaction_id",
        "account_id",
        "transaction_date",
        "type",
        "amount",
        "currency",
        "counterparty",
        "description",
    ]
    missing_columns = [col for col in required_columns if col not in df.columns]

    if missing_columns:
        return {
            "status": "failed",
            "message": "Missing required columns",
            "missing_columns": missing_columns,
        }

    transactions = []
    for _, row in df.iterrows():
        transactions.append(Transaction(
            transaction_id=str(row["transaction_id"]),
            account_id=str(row["account_id"]),
            transaction_date=str(row["transaction_date"]),
            type=str(row["type"]),
            amount=parse_amount(row["amount"], "amount"),
            currency=str(row["currency"]),
            counterparty=str(row["counterparty"]),
            description=str(row["description"]),
        ))

    clear_table(db, Transaction)
    db.add_all(transactions)
    db.commit()
    add_audit_log(db, "File uploaded", "transactions", f"{len(df)} transaction rows uploaded")
    validate_data(db)
    run_reconciliation(db)

    return {
        "status": "processed",
        "file_type": "transactions",
        "rows_processed": len(df),
    }


def validate_data(db: Session):
    clear_table(db, ValidationError)

    accounts = db.query(Account).all()
    balances = db.query(Balance).all()
    transactions = db.query(Transaction).all()

    account_ids = {account.account_id for account in accounts}
    transaction_ids = set()
    errors = []

    for transaction in transactions:
        if transaction.account_id not in account_ids:
            errors.append(ValidationError(
                error_type="Unknown account",
                severity="High",
                details=f"Transaction {transaction.transaction_id} uses unknown account {transaction.account_id}",
            ))

        if transaction.transaction_id in transaction_ids:
            errors.append(ValidationError(
                error_type="Duplicate transaction",
                severity="High",
                details=f"Transaction ID {transaction.transaction_id} appears more than once",
            ))

        transaction_ids.add(transaction.transaction_id)

        if transaction.amount <= 0:
            errors.append(ValidationError(
                error_type="Invalid amount",
                severity="Medium",
                details=f"Transaction {transaction.transaction_id} has non-positive amount",
            ))

    for balance in balances:
        if balance.account_id not in account_ids:
            errors.append(ValidationError(
                error_type="Unknown account",
                severity="High",
                details=f"Balance row uses unknown account {balance.account_id}",
            ))

        if balance.closing_balance < 0:
            errors.append(ValidationError(
                error_type="Negative balance",
                severity="Medium",
                details=f"Account {balance.account_id} has negative closing balance",
            ))

    db.add_all(errors)
    db.commit()

    if errors:
        add_audit_log(db, "Validation completed", "validation_errors", f"{len(errors)} validation errors found")
    else:
        add_audit_log(db, "Validation completed", "validation_errors", "No validation errors found")


def run_reconciliation(db: Session):
    clear_table(db, ReconciliationResult)
    clear_table(db, ExceptionItem)

    balances = db.query(Balance).all()
    transactions = db.query(Transaction).all()

    transactions_by_account_and_date: Dict[str, List[Transaction]] = {}

    for transaction in transactions:
        key = f"{transaction.account_id}|{transaction.transaction_date}"
        transactions_by_account_and_date.setdefault(key, []).append(transaction)

    results = []
    exceptions = []

    for balance in balances:
        key = f"{balance.account_id}|{balance.report_date}"
        related_transactions = transactions_by_account_and_date.get(key, [])

        inflows = sum(
            txn.amount for txn in related_transactions
            if txn.type.lower() == "inflow"
        )

        outflows = sum(
            txn.amount for txn in related_transactions
            if txn.type.lower() == "outflow"
        )

        expected_closing_balance = balance.opening_balance + inflows - outflows
        difference = round(balance.closing_balance - expected_closing_balance, 2)
        status_value = "Passed" if difference == 0 else "Failed"

        results.append(ReconciliationResult(
            account_id=balance.account_id,
            report_date=balance.report_date,
            opening_balance=balance.opening_balance,
            total_inflows=inflows,
            total_outflows=outflows,
            expected_closing_balance=expected_closing_balance,
            actual_closing_balance=balance.closing_balance,
            difference=difference,
            status=status_value,
        ))

        if status_value == "Failed":
            exceptions.append(ExceptionItem(
                account_id=balance.account_id,
                report_date=balance.report_date,
                exception_type="Balance reconciliation break",
                severity="High" if abs(difference) > 10000 else "Medium",
                amount_difference=difference,
                status="Open",
                owner="Unassigned",
            ))

    db.add_all(results)
    db.add_all(exceptions)
    db.commit()
    add_audit_log(db, "Reconciliation completed", "reconciliation_results", f"{len(results)} accounts reconciled")


@app.get("/dashboard", dependencies=[Depends(require_api_key)])
def get_dashboard(db: Session = Depends(get_db)):
    balances = db.query(Balance).all()
    reconciliations = db.query(ReconciliationResult).all()
    validation_errors = db.query(ValidationError).all()
    exceptions = db.query(ExceptionItem).all()

    total_cash = sum(balance.closing_balance for balance in balances)

    failed_reconciliations = len([
        row for row in reconciliations
        if row.status == "Failed"
    ])

    open_exceptions = len([
        row for row in exceptions
        if row.status == "Open"
    ])

    total_checks = len(reconciliations) + len(validation_errors)
    failed_checks = failed_reconciliations + len(validation_errors)

    if total_checks == 0:
        data_quality_score = 100
    else:
        data_quality_score = round(100 - ((failed_checks / total_checks) * 100), 2)

    return {
        "total_cash": total_cash,
        "failed_reconciliations": failed_reconciliations,
        "open_exceptions": open_exceptions,
        "data_quality_score": data_quality_score,
    }


@app.get("/accounts", dependencies=[Depends(require_api_key)])
def get_accounts(db: Session = Depends(get_db)):
    return [
        {
            "account_id": row.account_id,
            "bank_name": row.bank_name,
            "account_name": row.account_name,
            "region": row.region,
            "currency": row.currency,
            "entity": row.entity,
        }
        for row in db.query(Account).all()
    ]


@app.get("/balances", dependencies=[Depends(require_api_key)])
def get_balances(db: Session = Depends(get_db)):
    return [
        {
            "report_date": row.report_date,
            "account_id": row.account_id,
            "opening_balance": row.opening_balance,
            "closing_balance": row.closing_balance,
            "currency": row.currency,
        }
        for row in db.query(Balance).all()
    ]


@app.get("/transactions", dependencies=[Depends(require_api_key)])
def get_transactions(db: Session = Depends(get_db)):
    return [
        {
            "transaction_id": row.transaction_id,
            "account_id": row.account_id,
            "transaction_date": row.transaction_date,
            "type": row.type,
            "amount": row.amount,
            "currency": row.currency,
            "counterparty": row.counterparty,
            "description": row.description,
        }
        for row in db.query(Transaction).all()
    ]


@app.get("/validation-errors", dependencies=[Depends(require_api_key)])
def get_validation_errors(db: Session = Depends(get_db)):
    return [
        {
            "type": row.error_type,
            "severity": row.severity,
            "details": row.details,
        }
        for row in db.query(ValidationError).all()
    ]


@app.get("/reconciliations", dependencies=[Depends(require_api_key)])
def get_reconciliations(db: Session = Depends(get_db)):
    return [
        {
            "account_id": row.account_id,
            "report_date": row.report_date,
            "opening_balance": row.opening_balance,
            "total_inflows": row.total_inflows,
            "total_outflows": row.total_outflows,
            "expected_closing_balance": row.expected_closing_balance,
            "actual_closing_balance": row.actual_closing_balance,
            "difference": row.difference,
            "status": row.status,
        }
        for row in db.query(ReconciliationResult).all()
    ]


@app.get("/exceptions", dependencies=[Depends(require_api_key)])
def get_exceptions(db: Session = Depends(get_db)):
    return [
        {
            "account_id": row.account_id,
            "report_date": row.report_date,
            "exception_type": row.exception_type,
            "severity": row.severity,
            "amount_difference": row.amount_difference,
            "status": row.status,
            "owner": row.owner,
        }
        for row in db.query(ExceptionItem).all()
    ]


@app.get("/audit-logs", dependencies=[Depends(require_api_key)])
def get_audit_logs(db: Session = Depends(get_db)):
    return [
        {
            "action": row.action,
            "entity_type": row.entity_type,
            "details": row.details,
            "created_at": row.created_at,
        }
        for row in db.query(AuditLog).order_by(AuditLog.id.desc()).all()
    ]


static_dir = Path(__file__).resolve().parent / "static"

if static_dir.exists():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
