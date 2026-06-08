# CarDiagnostic AI

Single-page diagnostic assistant with a Node API and PostgreSQL storage.

## Run locally

1. Install dependencies:

```powershell
npm install
```

2. Create `.env` from `.env.example` and set your PostgreSQL connection:

```powershell
Copy-Item .env.example .env
```

3. Create the database if it does not exist yet:

```sql
create database car_diagnostic;
```

4. Start the app:

```powershell
npm run dev
```

Open `http://localhost:3000`.

The server applies `db/schema.sql` on startup and stores diagnostic request history in PostgreSQL.
