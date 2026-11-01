# Kairos — Charity Ledger CRM

A Django-based CRM and financial accounting system for managing supporters, field agents, bank statement imports, and transaction matching.

---

## Table of Contents

- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Setup Method 1 — Local Development (No Docker)](#setup-method-1--local-development-no-docker)
- [Setup Method 2 — Docker Development](#setup-method-2--docker-development)
- [Setup Method 3 — Docker Production](#setup-method-3--docker-production)
- [Environment Variable Reference](#environment-variable-reference)

---

## Tech Stack

| Layer | Technology |
| :--- | :--- |
| **Backend** | Django 6.0.5 (Python 3.12) |
| **Database** | PostgreSQL 16 |
| **Package Manager** | [uv](https://docs.astral.sh/uv/) |
| **WSGI Server** | Gunicorn (production) |
| **Reverse Proxy** | Nginx (production) |
| **Containerisation** | Docker & Docker Compose |

---

## Project Structure

```
kairos/
├── config/              # Django settings and URL configuration
├── finance/             # Bank transactions, ledger, statement parsing
├── people/              # Supporters, agents, interactions
├── templates/           # Global HTML templates
├── docker/
│   ├── entrypoint.sh    # Container startup script (migrate → collectstatic → gunicorn)
│   └── nginx/
│       └── nginx.conf   # Nginx reverse proxy configuration
├── Dockerfile
├── docker-compose.yml       # Development (Docker)
├── docker-compose.prod.yml  # Production (Docker)
├── .env                     # Local dev secrets (never commit)
├── .env.prod                # Production secrets (never commit)
└── .env.example             # Template — copy to create your .env
```

---

## Setup Method 1 — Local Development (No Docker)

Use this when you want to run the Django development server directly on your machine with hot-reload.

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) installed
- PostgreSQL 16 installed and running locally

### Steps

**1. Clone the repository**
```bash
git clone <repository-url>
cd kairos
```

**2. Install dependencies**
```bash
uv sync
```

**3. Create your `.env` file**
```bash
cp .env.example .env
```

Edit `.env` with your local settings:
```env
# Django Core
SECRET_KEY="your-secret-key-here"
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# PostgreSQL — pointing to your local Postgres
DB_NAME=kairos_dev
DB_USER=postgres
DB_PASSWORD=your_local_postgres_password
DB_HOST=localhost
DB_PORT=5432
```

**4. Create the PostgreSQL database**

Open a `psql` shell or use pgAdmin:
```sql
CREATE DATABASE kairos_dev;
```

**5. Run migrations**
```bash
uv run python manage.py migrate
```

**6. Create a superuser (admin account)**
```bash
uv run python manage.py createsuperuser
```

**7. Start the development server**
```bash
uv run python manage.py runserver
```

The application is now running at **http://localhost:8000**

> [!NOTE]
> The Django Admin is available at **http://localhost:8000/admin/**

---

## Setup Method 2 — Docker Development

Use this to run the full stack (Django + PostgreSQL) inside Docker containers, without installing PostgreSQL locally.

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running

### Steps

**1. Clone the repository**
```bash
git clone <repository-url>
cd kairos
```

**2. Create your `.env` file**
```bash
cp .env.example .env
```

Edit `.env`:
```env
SECRET_KEY="your-secret-key-here"
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

DB_NAME=kairos_db_dev
DB_USER=postgres
DB_PASSWORD=your_password_here
DB_HOST=localhost
DB_PORT=5432
```

> [!NOTE]
> `DB_HOST=localhost` is only used when running Django **outside** Docker. Inside Docker, the compose file automatically overrides `DB_HOST` to `db` (the Postgres container name).

**3. Build and start the containers**
```bash
docker compose up --build
```

Docker will automatically:
- Start the PostgreSQL container and wait for it to be healthy
- Build the Django image
- Run `migrate` on first startup
- Start the application

The application is now running at **http://localhost:8000**

**4. Create a superuser**

In a separate terminal, while the containers are running:
```bash
docker compose exec web uv run python manage.py createsuperuser
```

**Stopping the containers:**
```bash
docker compose down
```

**Stopping and removing all data (full reset):**
```bash
docker compose down -v
```

---

## Setup Method 3 — Docker Production

Use this to deploy to a server. The recipient only needs Docker installed — no Python, no PostgreSQL, no uv required.

### Architecture

```
Internet → Nginx (port 80) → Gunicorn (port 8000) → Django → PostgreSQL
```

Nginx handles all static file serving. Gunicorn handles multiple concurrent requests. The database is never exposed to the public internet.

### Prerequisites (on the server)

- [Docker](https://docs.docker.com/engine/install/) and Docker Compose installed
- The project files copied to the server

### Steps

**1. Copy the project to the server**
```bash
# Example using scp — transfer project files
scp -r ./kairos user@your-server-ip:/home/user/kairos
```

**2. Create the `.env.prod` file on the server**

> [!CAUTION]
> **Never commit `.env.prod` to Git.** Create it directly on the server.

```bash
cd /home/user/kairos
nano .env.prod
```

Fill in real production values:
```env
SECRET_KEY=your-50-character-random-secret-key
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
CSRF_TRUSTED_ORIGINS=http://yourdomain.com,https://yourdomain.com

DB_NAME=kairos_prod
DB_USER=kairos_user
DB_PASSWORD=very-strong-random-password
DB_PORT=5432
```

To generate a secure `SECRET_KEY`, run:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

**3. Build and start production containers**
```bash
docker compose -f docker-compose.prod.yml up -d --build
```

The `-f` flag selects the production compose file. The `-d` flag runs everything in the background.

Docker will automatically:
- Start PostgreSQL (not exposed to the internet)
- Build the Django image
- Run `migrate` and `collectstatic`
- Start Gunicorn (3 workers)
- Start Nginx on port 80

The application is now running at **http://yourdomain.com**

**4. Create a superuser**
```bash
docker compose -f docker-compose.prod.yml exec web uv run python manage.py createsuperuser
```

**Viewing live logs:**
```bash
docker compose -f docker-compose.prod.yml logs -f
```

**Stopping the production stack:**
```bash
docker compose -f docker-compose.prod.yml down
```

**Updating the application (redeploy):**
```bash
docker compose -f docker-compose.prod.yml up -d --build
```

---

## Environment Variable Reference

| Variable | Required | Description | Example |
| :--- | :--- | :--- | :--- |
| `SECRET_KEY` | ✅ | Django's cryptographic secret key | `"abc123...xyz"` |
| `DEBUG` | ✅ | `True` for development, `False` for production | `False` |
| `ALLOWED_HOSTS` | ✅ | Comma-separated list of allowed hostnames | `yourdomain.com,www.yourdomain.com` |
| `CSRF_TRUSTED_ORIGINS` | ✅ Prod | Comma-separated trusted origins for CSRF | `https://yourdomain.com` |
| `DB_NAME` | ✅ | PostgreSQL database name | `kairos_prod` |
| `DB_USER` | ✅ | PostgreSQL username | `kairos_user` |
| `DB_PASSWORD` | ✅ | PostgreSQL password | `strong-password` |
| `DB_HOST` | ✅ | Database host (`localhost` for local, `db` inside Docker) | `localhost` |
| `DB_PORT` | ✅ | PostgreSQL port | `5432` |

---

## Quick Reference

| Goal | Command |
| :--- | :--- |
| Run locally (no Docker) | `uv run python manage.py runserver` |
| Start dev Docker stack | `docker compose up --build` |
| Start prod Docker stack | `docker compose -f docker-compose.prod.yml up -d --build` |
| Create admin user (local) | `uv run python manage.py createsuperuser` |
| Create admin user (dev Docker) | `docker compose exec web uv run python manage.py createsuperuser` |
| Create admin user (prod Docker) | `docker compose -f docker-compose.prod.yml exec web uv run python manage.py createsuperuser` |
| View prod logs | `docker compose -f docker-compose.prod.yml logs -f` |
| Full reset (delete all data) | `docker compose down -v` |

