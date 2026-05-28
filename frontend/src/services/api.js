const API_BASE_URL = "http://localhost:8000";
const API_KEY = "dev-secret-key";

function securityHeaders() {
  return {
    "X-API-Key": API_KEY,
  };
}

async function parseResponse(response) {
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.detail || "Request failed");
  }

  return data;
}

export async function uploadFile(endpoint, file) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: "POST",
    headers: securityHeaders(),
    body: formData,
  });

  return parseResponse(response);
}

export async function getDashboard() {
  const response = await fetch(`${API_BASE_URL}/dashboard`, {
    headers: securityHeaders(),
  });
  return parseResponse(response);
}

export async function getReconciliations() {
  const response = await fetch(`${API_BASE_URL}/reconciliations`, {
    headers: securityHeaders(),
  });
  return parseResponse(response);
}

export async function getExceptions() {
  const response = await fetch(`${API_BASE_URL}/exceptions`, {
    headers: securityHeaders(),
  });
  return parseResponse(response);
}

export async function getValidationErrors() {
  const response = await fetch(`${API_BASE_URL}/validation-errors`, {
    headers: securityHeaders(),
  });
  return parseResponse(response);
}
