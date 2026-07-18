# Repository Guidelines

## Project Structure & Module Organization

`agenttrace/` is the Python package. The public SDK lives in `agenttrace/sdk/`; the FastAPI application, SQLAlchemy models, Pydantic schemas, pricing logic, templates, and static files live in `agenttrace/server/`. Keep server-rendered HTML in `agenttrace/server/templates/` and browser assets in `agenttrace/server/static/`. Tests are grouped by concern in `tests/test_api.py`, `tests/test_sdk.py`, and `tests/test_pricing.py`. `examples/research_pipeline.py` is the executable demo. The local `agenttrace.db`, `.venv/`, and `plan/` are development artifacts and must remain untracked.

## Build, Test, and Development Commands

Use PowerShell from the repository root and work inside the virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn agenttrace.server.main:app --reload
.\.venv\Scripts\python.exe -m pytest
python examples\research_pipeline.py --runs 10 --fail-rate 0.2
```

The Uvicorn command serves the dashboard and API at `http://127.0.0.1:8000`. Pytest runs the complete suite; target one case with `python -m pytest tests/test_api.py -k test_name`. The example seeds a running server with representative traces.

## Coding Style & Naming Conventions

Follow standard Python conventions: four-space indentation, `snake_case` for functions and modules, `PascalCase` for classes, and uppercase names for constants. Add type hints where they clarify API or model boundaries. Keep Pydantic request/response schemas separate from SQLAlchemy persistence models. No formatter or linter is currently configured, so match nearby code and keep imports grouped and explicit. Preserve the SDK rule that tracing failures must never break the user's workflow.

## Testing Guidelines

Pytest is the test framework. Name files `test_*.py` and tests `test_<behavior>`. Add focused regression tests alongside every behavior change. API tests should use the existing isolated in-memory database fixture; do not depend on `agenttrace.db`. There is no enforced coverage threshold, but SDK failure handling, API responses, pricing fallbacks, and rendered dashboard behavior should remain covered.

## Commit & Pull Request Guidelines

Recent commits use short, lowercase, action-oriented subjects, such as `update README quickstart` and `record passive retry metadata in sdk`. Keep each commit focused. Prefer a feature branch and pull request over direct work on `main`. PRs should explain the user-visible change, list tests run, link relevant issues, and include screenshots for dashboard or template changes. Call out database-model changes because local databases may need recreation.
