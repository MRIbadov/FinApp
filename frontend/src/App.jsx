import React, { useEffect, useMemo, useState } from "react";
import {
  uploadFile,
  getDashboard,
  getReconciliations,
  getExceptions,
  getValidationErrors,
} from "./services/api";
import "./style.css";

const pages = [
  { id: "dashboard", label: "Dashboard", eyebrow: "Cash overview" },
  { id: "upload", label: "Upload Center", eyebrow: "CSV intake" },
  { id: "reconciliation", label: "Reconciliation", eyebrow: "Balance checks" },
  { id: "exceptions", label: "Exceptions", eyebrow: "Open breaks" },
  { id: "validation", label: "Data Quality", eyebrow: "Validation errors" },
];

const localAccountsKey = "finapp_accounts";

function App() {
  const [authMode, setAuthMode] = useState("login");
  const [user, setUser] = useState(null);
  const [authError, setAuthError] = useState("");
  const [activePage, setActivePage] = useState("dashboard");
  const [dashboard, setDashboard] = useState(null);
  const [reconciliations, setReconciliations] = useState([]);
  const [exceptions, setExceptions] = useState([]);
  const [validationErrors, setValidationErrors] = useState([]);
  const [message, setMessage] = useState("");
  const [apiError, setApiError] = useState("");
  const [isRefreshing, setIsRefreshing] = useState(false);

  const currentPage = useMemo(
    () => pages.find((page) => page.id === activePage) || pages[0],
    [activePage],
  );

  async function refreshData() {
    setIsRefreshing(true);

    try {
      const [dashboardData, reconciliationData, exceptionData, validationData] =
        await Promise.all([
          getDashboard(),
          getReconciliations(),
          getExceptions(),
          getValidationErrors(),
        ]);

      setDashboard(dashboardData);
      setReconciliations(reconciliationData);
      setExceptions(exceptionData);
      setValidationErrors(validationData);
      setApiError("");
    } catch (error) {
      setApiError(error.message || "Could not load app data.");
    } finally {
      setIsRefreshing(false);
    }
  }

  useEffect(() => {
    if (user) {
      refreshData();
    }
  }, [user]);

  function handleAuthSubmit(event) {
    event.preventDefault();

    const formData = new FormData(event.currentTarget);
    const name = String(formData.get("name") || "").trim();
    const email = String(formData.get("email") || "").trim().toLowerCase();
    const password = String(formData.get("password") || "");
    const accounts = loadLocalAccounts();

    setAuthError("");

    if (authMode === "signup") {
      if (accounts.some((account) => account.email === email)) {
        setAuthError("An account with this email already exists. Please sign in.");
        return;
      }

      const newAccount = {
        name,
        email,
        password,
      };

      saveLocalAccounts([...accounts, newAccount]);
      setUser({
        name,
        email,
      });
      return;
    }

    const existingAccount = accounts.find((account) => account.email === email);

    if (!existingAccount) {
      setAuthError("No account found for this email. Please sign up first.");
      return;
    }

    if (existingAccount.password !== password) {
      setAuthError("Incorrect password. Please try again.");
      return;
    }

    setUser({
      name: existingAccount.name,
      email,
    });
  }

  if (!user) {
    return (
      <AuthPage
        error={authError}
        mode={authMode}
        onModeChange={(nextMode) => {
          setAuthError("");
          setAuthMode(nextMode);
        }}
        onSubmit={handleAuthSubmit}
      />
    );
  }

  async function handleUpload(endpoint, event) {
    const file = event.target.files[0];

    if (!file) {
      return;
    }

    try {
      const result = await uploadFile(endpoint, file);
      setMessage(`${file.name}: ${result.status}. Rows processed: ${result.rows_processed || 0}`);
      setApiError("");
      await refreshData();
    } catch (error) {
      setMessage("");
      setApiError(error.message || "Upload failed.");
    } finally {
      event.target.value = "";
    }
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">FA</span>
          <div>
            <h1>FinApp</h1>
            <p>Finance Control</p>
          </div>
        </div>

        <div className="signed-in-user">
          <span>{user.name}</span>
          <button
            type="button"
            onClick={() => {
              setUser(null);
              setAuthMode("login");
              setAuthError("");
            }}
          >
            Sign out
          </button>
        </div>

        <nav className="nav-list" aria-label="Main navigation">
          {pages.map((page) => (
            <button
              key={page.id}
              className={page.id === activePage ? "nav-item active" : "nav-item"}
              type="button"
              onClick={() => setActivePage(page.id)}
            >
              <span>{page.label}</span>
              <small>{page.eyebrow}</small>
            </button>
          ))}
        </nav>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <p className="eyebrow">{currentPage.eyebrow}</p>
            <h2>{currentPage.label}</h2>
          </div>
          <button className="refresh-button" type="button" onClick={refreshData}>
            {isRefreshing ? "Refreshing..." : "Refresh"}
          </button>
        </header>

        <div className="mobile-tabs" aria-label="Mobile navigation">
          {pages.map((page) => (
            <button
              key={page.id}
              className={page.id === activePage ? "mobile-tab active" : "mobile-tab"}
              type="button"
              onClick={() => setActivePage(page.id)}
            >
              {page.label}
            </button>
          ))}
        </div>

        {apiError && <p className="api-error">{apiError}</p>}

        {activePage === "dashboard" && <DashboardPage dashboard={dashboard} />}
        {activePage === "upload" && (
          <UploadPage message={message} onUpload={handleUpload} />
        )}
        {activePage === "reconciliation" && (
          <ReconciliationPage reconciliations={reconciliations} />
        )}
        {activePage === "exceptions" && <ExceptionsPage exceptions={exceptions} />}
        {activePage === "validation" && (
          <ValidationPage validationErrors={validationErrors} />
        )}
      </main>
    </div>
  );
}

function loadLocalAccounts() {
  try {
    return JSON.parse(localStorage.getItem(localAccountsKey)) || [];
  } catch {
    return [];
  }
}

function saveLocalAccounts(accounts) {
  localStorage.setItem(localAccountsKey, JSON.stringify(accounts));
}

function AuthPage({ error, mode, onModeChange, onSubmit }) {
  const isSignup = mode === "signup";

  return (
    <main className="auth-shell">
      <section className="auth-panel">
        <div className="auth-brand">
          <span className="brand-mark">FA</span>
          <div>
            <h1>FinApp</h1>
            <p>Secure workspace access</p>
          </div>
        </div>

        <div className="auth-heading">
          <h2>{isSignup ? "Create account" : "Sign in"}</h2>
          <p>
            {isSignup
              ? "Create a simple local profile to enter the FinApp workspace."
              : "Sign in with an account created on this device."}
          </p>
        </div>

        <form className="auth-form" onSubmit={onSubmit}>
          {isSignup && (
            <label>
              Name
              <input name="name" type="text" placeholder="Alex Morgan" required />
            </label>
          )}

          <label>
            Email
            <input name="email" type="email" placeholder="alex@company.com" required />
          </label>

          <label>
            Password
            <input name="password" type="password" placeholder="Enter password" required />
          </label>

          <button className="auth-submit" type="submit">
            {isSignup ? "Create account" : "Sign in"}
          </button>
        </form>

        {error && <p className="auth-error">{error}</p>}

        <p className="auth-switch">
          {isSignup ? "Already have an account?" : "Need an account?"}
          <button
            type="button"
            onClick={() => onModeChange(isSignup ? "login" : "signup")}
          >
            {isSignup ? "Sign in" : "Sign up"}
          </button>
        </p>
      </section>
    </main>
  );
}

function DashboardPage({ dashboard }) {
  return (
    <section className="page">
      <div className="page-heading">
        <h3>Financial Cash Position</h3>
        <p>Track cash, exceptions, reconciliation, and data-quality indicators in one operating view.</p>
      </div>

      <div className="metric-grid">
        <MetricCard title="Total Cash" value={formatMoney(dashboard?.total_cash || 0)} />
        <MetricCard title="Failed Reconciliations" value={dashboard?.failed_reconciliations || 0} />
        <MetricCard title="Open Exceptions" value={dashboard?.open_exceptions || 0} />
        <MetricCard title="Data Quality Score" value={`${dashboard?.data_quality_score || 100}%`} />
      </div>

      <div className="summary-band">
        <SummaryItem label="Operating status" value={dashboard?.open_exceptions ? "Review needed" : "Clear"} />
        <SummaryItem label="Next workflow" value="Upload accounts, then transactions, then balances" />
        <SummaryItem label="Review focus" value="Failed reconciliations and high-priority data errors" />
      </div>
    </section>
  );
}

function UploadPage({ message, onUpload }) {
  return (
    <section className="page">
      <div className="page-heading">
        <h3>Upload Center</h3>
        <p>Upload files in sequence so validation and reconciliation can run cleanly.</p>
      </div>

      <div className="upload-grid">
        <UploadBox step="01" title="Accounts CSV" endpoint="/upload/accounts" onUpload={onUpload} />
        <UploadBox step="02" title="Transactions CSV" endpoint="/upload/transactions" onUpload={onUpload} />
        <UploadBox step="03" title="Balances CSV" endpoint="/upload/balances" onUpload={onUpload} />
      </div>

      {message && <p className="message">{message}</p>}
    </section>
  );
}

function ReconciliationPage({ reconciliations }) {
  return (
    <section className="page">
      <div className="page-heading">
        <h3>Reconciliation Results</h3>
        <p>Compare opening balance, cash movement, and closing balance at account level.</p>
      </div>

      <Table
        data={reconciliations}
        columns={[
          "account_id",
          "report_date",
          "opening_balance",
          "total_inflows",
          "total_outflows",
          "expected_closing_balance",
          "actual_closing_balance",
          "difference",
          "status",
        ]}
      />
    </section>
  );
}

function ExceptionsPage({ exceptions }) {
  return (
    <section className="page">
      <div className="page-heading">
        <h3>Exception Queue</h3>
        <p>Review breaks created by failed reconciliations for ownership and follow-up.</p>
      </div>

      <Table
        data={exceptions}
        columns={[
          "account_id",
          "report_date",
          "exception_type",
          "severity",
          "amount_difference",
          "status",
          "owner",
        ]}
      />
    </section>
  );
}

function ValidationPage({ validationErrors }) {
  return (
    <section className="page">
      <div className="page-heading">
        <h3>Data Quality Errors</h3>
        <p>Review input issues found during validation, including unknown accounts and invalid amounts.</p>
      </div>

      <Table data={validationErrors} columns={["type", "severity", "details"]} />
    </section>
  );
}

function MetricCard({ title, value }) {
  return (
    <div className="metric-card">
      <p>{title}</p>
      <strong>{value}</strong>
    </div>
  );
}

function SummaryItem({ label, value }) {
  return (
    <div className="summary-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function UploadBox({ step, title, endpoint, onUpload }) {
  return (
    <div className="upload-box">
      <span className="step">{step}</span>
      <h4>{title}</h4>
      <input type="file" accept=".csv" onChange={(event) => onUpload(endpoint, event)} />
    </div>
  );
}

function Table({ data, columns }) {
  if (!data || data.length === 0) {
    return <p className="empty">No data available yet.</p>;
  }

  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{formatColumn(column)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, index) => (
            <tr key={index}>
              {columns.map((column) => (
                <td key={column}>{formatCell(row[column], column)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatCell(value, column) {
  if (value === null || value === undefined) {
    return "";
  }

  if (typeof value === "number" && column.includes("balance")) {
    return formatMoney(value);
  }

  if (typeof value === "number" && column.includes("amount")) {
    return formatMoney(value);
  }

  const translations = {
    Passed: "Passed",
    Failed: "Failed",
    Open: "Open",
    Medium: "Medium",
    High: "High",
    Unassigned: "Unassigned",
    "Balance reconciliation break": "Balance reconciliation break",
  };

  return translations[value] || String(value);
}

function formatColumn(text) {
  const labels = {
    account_id: "Account ID",
    report_date: "Report Date",
    opening_balance: "Opening Balance",
    total_inflows: "Total Inflows",
    total_outflows: "Total Outflows",
    expected_closing_balance: "Expected Closing",
    actual_closing_balance: "Actual Closing",
    difference: "Difference",
    status: "Status",
    exception_type: "Exception Type",
    severity: "Severity",
    amount_difference: "Amount Difference",
    owner: "Owner",
    type: "Type",
    details: "Details",
  };

  return labels[text] || text.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatMoney(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(value);
}

export default App;
