.PHONY: up down migrate seed test test-backend test-frontend loadtest

# --- run ---
up:            ## Build + start the full stack
	docker compose up --build

down:
	docker compose down

migrate:       ## Apply DB migrations (run after `up`)
	docker compose exec backend alembic upgrade head

seed:          ## Seed demo analyst + fraud network (prints otpauth for TOTP)
	docker compose exec backend python -m scripts.seed_demo

# --- db snapshot (demo restore point; file is gitignored — has TOTP secrets) ---
db-save:       ## Snapshot the current DB to backend/snapshots/demo_state.sql
	@mkdir -p backend/snapshots
	docker compose exec -T postgres pg_dump -U afm -d afm --clean --if-exists > backend/snapshots/demo_state.sql
	@echo "saved backend/snapshots/demo_state.sql"

db-restore:    ## Restore the DB from backend/snapshots/demo_state.sql
	docker compose exec -T postgres psql -U afm -d afm < backend/snapshots/demo_state.sql
	@echo "restored from backend/snapshots/demo_state.sql"

# --- test ---
test: test-backend test-frontend

test-backend:  ## Backend unit + contract tests
	cd backend && pytest

test-frontend: ## Frontend type-check, build, component tests
	cd frontend && npm run build && npm test

# --- load test (run against a LIVE instance: `make up` first) ---
# API is light at the target scale (<=10K videos/day); this verifies p95 under load.
loadtest:
	python3 .claude/skills/senior-backend/scripts/api_load_tester.py \
		http://localhost:8000/health --concurrency 50 --duration 30
