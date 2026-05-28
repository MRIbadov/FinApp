import os

os.environ["DATABASE_URL"] = "sqlite:///./test_treasury.db"
os.environ["API_KEY"] = "test-secret-key"

from fastapi.testclient import TestClient

from database import Base, engine
from main import app


client = TestClient(app)


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def csv_file(content: str):
    return ("upload.csv", content.encode("utf-8"), "text/csv")


def auth_headers():
    return {"X-API-Key": "test-secret-key"}


def upload_csv(endpoint: str, content: str):
    return client.post(
        endpoint,
        headers=auth_headers(),
        files={"file": csv_file(content)},
    )


def test_dashboard_is_protected_by_the_api_key():
    response = client.get("/dashboard")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key"


def test_accounts_upload_explains_which_columns_are_missing():
    response = upload_csv(
        "/upload/accounts",
        "account_id,bank_name\nA100,Example Bank\n",
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "failed",
        "message": "Missing required columns",
        "missing_columns": ["account_name", "region", "currency", "entity"],
    }


def test_happy_path_uploads_data_and_reconciles_without_exceptions():
    upload_csv(
        "/upload/accounts",
        "\n".join(
            [
                "account_id,bank_name,account_name,region,currency,entity",
                "A100,Example Bank,Operating Account,EMEA,EUR,Treasury Ltd",
            ]
        ),
    )
    upload_csv(
        "/upload/transactions",
        "\n".join(
            [
                "transaction_id,account_id,transaction_date,type,amount,currency,counterparty,description",
                "T100,A100,2026-05-27,inflow,200,EUR,Customer,Invoice paid",
                "T101,A100,2026-05-27,outflow,50,EUR,Supplier,Vendor payment",
            ]
        ),
    )

    balance_response = upload_csv(
        "/upload/balances",
        "\n".join(
            [
                "report_date,account_id,opening_balance,closing_balance,currency",
                "2026-05-27,A100,100,250,EUR",
            ]
        ),
    )

    dashboard = client.get("/dashboard", headers=auth_headers()).json()
    reconciliations = client.get("/reconciliations", headers=auth_headers()).json()
    exceptions = client.get("/exceptions", headers=auth_headers()).json()
    validation_errors = client.get("/validation-errors", headers=auth_headers()).json()

    assert balance_response.status_code == 200
    assert balance_response.json()["rows_processed"] == 1
    assert dashboard == {
        "total_cash": 250.0,
        "failed_reconciliations": 0,
        "open_exceptions": 0,
        "data_quality_score": 100.0,
    }
    assert reconciliations[0]["status"] == "Passed"
    assert reconciliations[0]["difference"] == 0.0
    assert exceptions == []
    assert validation_errors == []


def test_reconciliation_break_creates_a_clear_exception():
    upload_csv(
        "/upload/accounts",
        "\n".join(
            [
                "account_id,bank_name,account_name,region,currency,entity",
                "A200,Example Bank,Collections Account,NA,USD,Treasury Inc",
            ]
        ),
    )
    upload_csv(
        "/upload/transactions",
        "\n".join(
            [
                "transaction_id,account_id,transaction_date,type,amount,currency,counterparty,description",
                "T200,A200,2026-05-27,inflow,500,USD,Customer,Receipt",
            ]
        ),
    )
    upload_csv(
        "/upload/balances",
        "\n".join(
            [
                "report_date,account_id,opening_balance,closing_balance,currency",
                "2026-05-27,A200,100,650,USD",
            ]
        ),
    )

    dashboard = client.get("/dashboard", headers=auth_headers()).json()
    reconciliations = client.get("/reconciliations", headers=auth_headers()).json()
    exceptions = client.get("/exceptions", headers=auth_headers()).json()

    assert dashboard["failed_reconciliations"] == 1
    assert dashboard["open_exceptions"] == 1
    assert reconciliations[0]["status"] == "Failed"
    assert reconciliations[0]["difference"] == 50.0
    assert exceptions[0]["exception_type"] == "Balance reconciliation break"
    assert exceptions[0]["severity"] == "Medium"


def test_duplicate_transactions_are_reported_as_validation_errors():
    upload_csv(
        "/upload/accounts",
        "\n".join(
            [
                "account_id,bank_name,account_name,region,currency,entity",
                "A300,Example Bank,Main Account,EMEA,EUR,Treasury Ltd",
            ]
        ),
    )

    response = upload_csv(
        "/upload/transactions",
        "\n".join(
            [
                "transaction_id,account_id,transaction_date,type,amount,currency,counterparty,description",
                "T300,A300,2026-05-27,inflow,100,EUR,Customer,Receipt",
                "T300,A300,2026-05-27,outflow,20,EUR,Supplier,Duplicate transaction",
            ]
        ),
    )

    validation_errors = client.get("/validation-errors", headers=auth_headers()).json()

    assert response.status_code == 200
    assert response.json()["rows_processed"] == 2
    assert validation_errors == [
        {
            "type": "Duplicate transaction",
            "severity": "High",
            "details": "Transaction ID T300 appears more than once",
        }
    ]


def test_invalid_numeric_values_return_a_clear_client_error():
    response = upload_csv(
        "/upload/balances",
        "\n".join(
            [
                "report_date,account_id,opening_balance,closing_balance,currency",
                "2026-05-27,A400,not-a-number,100,EUR",
            ]
        ),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Column 'opening_balance' must contain numeric values"


def test_invalid_balance_upload_does_not_replace_existing_balances():
    upload_csv(
        "/upload/balances",
        "\n".join(
            [
                "report_date,account_id,opening_balance,closing_balance,currency",
                "2026-05-27,A500,10,20,EUR",
            ]
        ),
    )

    response = upload_csv(
        "/upload/balances",
        "\n".join(
            [
                "report_date,account_id,opening_balance,closing_balance,currency",
                "2026-05-27,A500,not-a-number,30,EUR",
            ]
        ),
    )
    balances = client.get("/balances", headers=auth_headers()).json()

    assert response.status_code == 400
    assert len(balances) == 1
    assert balances[0]["opening_balance"] == 10.0
    assert balances[0]["closing_balance"] == 20.0
