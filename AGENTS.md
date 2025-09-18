# Repository Guidelines

## Project Structure & Module Organization
- `web_server/app`: Flask app factory with `routes`, `services`, `exchanges`, shared models/templates.
- `scripts/`: operational helpers (`start.sh`, `init_db.py`) used by automation and Docker.
- `migrations/`: Alembic metadata; keep in sync with db schema changes.
- `tests/` + `web_server/tests/`: unit coverage for order validation and integration routes.
- `config/` + `docker-compose.yml`: container stack (app, Postgres, nginx); adjust env overrides here.
- `run.py`: orchestrator CLI for setup, start/stop, and environment resets.

## Build, Test & Development Commands
- `python -m venv venv && source venv/bin/activate` to create a local env.
- `pip install -r web_server/requirements.txt` installs Flask app dependencies.
- `flask --app web_server.app:create_app --debug run --port 5001` launches the dev server against your local `.env`.
- `docker-compose up --build` starts the full stack (app + Postgres + nginx) mirroring production defaults.
- `flask db upgrade` applies migrations; pair with `python scripts/init_db.py` for seeding admin credentials.
- `python run.py start|stop|status` leverages the orchestration wizard; add `setup` to regenerate `.env`.

## Coding Style & Naming Conventions
- Target Python 3.10, 4-space indentation, and standard PEP 8 spacing; favour type hints for new services.
- Modules and functions use `snake_case`; classes use `PascalCase`; template and static assets live under `web_server/app/templates` and `.../static`.
- Reuse existing blueprint structures when adding routes (`web_server/app/routes`); group exchange adapters under `exchanges/`.

## Testing Guidelines
- Use pytest: `pytest tests web_server/tests` covers both unit and integration suites.
- Name new files `test_<feature>.py` and follow fixture patterns in `tests/test_stop_order_validation.py`.
- Provide exchange-mocking helpers for order flows; assert database side-effects with temporary sessions.
- Keep meaningful coverage for error branches before submitting PRs.

## Commit & Pull Request Guidelines
- Follow conventional prefixes from history (`feat:`, `fix:`, `chore:`, `security:`) and keep commits focused per feature.
- Describe behavioural changes and impacted modules in PR summaries; note migration steps or env additions.
- Include reproduction or verification steps, attach screenshots for UI/template tweaks, and link tracking issues.

## Security & Configuration Tips
- Store secrets in `.env`; never commit credentials or TLS keys from `certs/`.
- Run `python run.py setup` when rotating secrets—wizard regenerates keys and Docker settings safely.
- Enforce HTTPS in production via `config/nginx-ssl.conf`; keep `ENABLE_SSL` false only for local debugging.
