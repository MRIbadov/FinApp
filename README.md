# Treasury Cash Position & Reconciliation Platform

This version uses MySQL instead of in-memory storage.

The app is still simple and readable, but now the uploaded data is stored in real database tables.


## Tech stack

- Python
- FastAPI
- SQLAlchemy
- MySQL
- pandas
- React
- Docker

## How to run

From the project folder:

```bash
docker compose up --build
```

Open the frontend:

```text
http://localhost:5173
```