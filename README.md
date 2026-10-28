# MSP Operations & Reporting Platform

A Python backend for MSP operations, third-party IT integrations, Microsoft 365 security and compliance reporting, and automated client report generation.

The service exposes REST APIs built with FastAPI. It collects organization data from connected platforms, stores application data in PostgreSQL, and can produce client-ready PDF and PowerPoint reports. Optional OpenAI integration supports AI-generated report content.

## What it does

- Connects to IT management, endpoint protection, backup, DNS filtering, and security platforms through integration clients and data processors.
- Provides APIs for Microsoft 365 security assessments, including MFA, secure score, risky users and sign-ins, and compliance status.
- Organizes account, client organization, integration credential, and report data in a PostgreSQL-backed data model.
- Encrypts stored integration credentials before they are persisted.
- Generates editable PowerPoint reports with integration-specific sections, charts, and tables.
- Generates PDF reports and supports report delivery through Microsoft Graph email integration.
- Offers LLM-assisted report content generation when an OpenAI API key is configured.
- Protects the interactive API documentation at `/docs` and `/redoc` with HTTP Basic authentication.

## Technology

| Area | Tools |
| --- | --- |
| API | Python, FastAPI, Uvicorn, Pydantic |
| Database | PostgreSQL, SQLAlchemy, Alembic, Supabase services |
| Integrations | Microsoft Graph, OAuth/MSAL, vendor REST APIs, `aiohttp` and `httpx` |
| Reports | `python-pptx`, Matplotlib, Puppeteer, PDF tooling |
| AI | OpenAI API (optional) |
| Deployment | Docker; Render blueprint included |

## Architecture

```text
API routes
   ├── Security and compliance endpoints
   ├── Client, account, and integration endpoints
   └── Report and document endpoints
          ↓
Services and integration orchestrator
   ├── Vendor clients and data processors
   ├── Credential encryption and organization services
   └── PowerPoint, PDF, and optional LLM report generation
          ↓
PostgreSQL / Supabase and external platform APIs
```

## Repository layout

```text
app/
  clients/       Third-party API clients
  core/          Configuration, authentication, and database setup
  models/        SQLAlchemy data models
  processors/    Integration data processing
  routes/        FastAPI route modules
  schemas/       API request and response schemas
  services/      Integrations, encryption, AI, email, and reports
alembic/         Database migrations
docs/database/   Database schema reference
Dockerfile       Container build and start configuration
render.yaml      Render deployment blueprint
run.py           Local development entry point
```

## Run locally

### Requirements

- Python 3.11
- Node.js 20 and npm (used by the PDF tooling)
- A PostgreSQL database
- Supabase project credentials used by the application

### 1. Create a virtual environment and install packages

PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
npm install
```

### 2. Configure environment variables

Create a `.env` file in the repository root. Add the values for your own development services; never commit this file.

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_KEY=YOUR_SUPABASE_KEY
ENCRYPTION_KEY=YOUR_ENCRYPTION_KEY
DOCS_USERNAME=YOUR_DOCS_USERNAME
DOCS_PASSWORD=YOUR_STRONG_DOCS_PASSWORD
ALLOWED_ORIGINS=*
```

Some features require additional credentials only when used:

```dotenv
OPENAI_API_KEY=
CONVERTHUB_API_KEY=
SUPABASE_SERVICE_ROLE_KEY=
MS_TENANT_ID=
MS_CLIENT_ID=
MS_CLIENT_SECRET=
MS_SENDER_EMAIL=
DEMO_USER_ID=
DEFAULT_CREDENTIAL_ID=
```

Use a secure, unique `ENCRYPTION_KEY` and keep all secrets in environment variables or your deployment provider's secret settings. Do not use the default documentation credentials (`admin` / `changeme`) outside local experimentation.

### 3. Apply database migrations

```powershell
alembic upgrade head
```

### 4. Start the API

```powershell
python run.py
```

The local development server listens at `http://127.0.0.1:8080`. The health check route is available at `/api/health-check` and requires the query parameters expected by that endpoint. Interactive API documentation is at `/docs` and `/redoc`; both require the documentation username and password configured above.

## Docker

Build and run the container after configuring the required environment variables:

```powershell
docker build -t msp-operations-platform .
docker run --env-file .env -p 8011:8011 msp-operations-platform
```

The container starts Uvicorn on port `8011`. The repository also includes a `render.yaml` blueprint; review its settings and configure secrets in the hosting dashboard before deploying.

## Database

Alembic migration files are in `alembic/versions/`. A schema reference is available at [`docs/database/schema.sql`](docs/database/schema.sql). The schema file is for reference; use Alembic migrations to update a running database.

## Security and configuration

- Never commit `.env` files, API keys, database passwords, client secrets, or real customer data.
- Use synthetic or anonymized data in screenshots, examples, and demos.
- Restrict `ALLOWED_ORIGINS` to trusted frontend origins in deployed environments.
- Use strong, unique documentation credentials and protect deployment secrets in the hosting provider.
- Review permissions granted to Microsoft Graph applications and third-party integration accounts.

## Notes

This repository contains backend services and API endpoints; a separate frontend may be required for a complete user-facing dashboard. Integrations, report exports, and AI features depend on their corresponding credentials and external services.
