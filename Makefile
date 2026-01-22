# Convo Backend Makefile
# Multi-tenant booking system

.PHONY: help test-phase6 test-phase7 test-all seed-test init-test-db

help:
	@echo "Convo Backend - Available Commands"
	@echo "==================================="
	@echo ""
	@echo "Test Database Management:"
	@echo "  make init-test-db    Initialize convo_test schema"
	@echo "  make seed-test       Seed convo_test with sample data"
	@echo "  make test-phase6     Run Phase 6 onboarding tests"
	@echo "  make test-phase7     Run Phase 7 security tests"
	@echo "  make test-all        Run all Phase 6 + 7 tests"
	@echo ""
	@echo "Requirements:"
	@echo "  - Local Postgres running"
	@echo "  - convo_test database created: createdb convo_test"
	@echo "  - DATABASE_URL set to local test DB"

init-test-db:
	@echo "🔧 Initializing test database schema..."
	@export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test" && \
	python3 Backend/scripts/init_test_db.py

seed-test:
	@echo "🌱 Seeding test database..."
	@export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test" && \
	python3 Backend/scripts/seed_convo_test.py

test-phase6:
	@echo "🧪 Running Phase 6 tests..."
	@export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test" && \
	python3 Backend/scripts/init_test_db.py && \
	cd Backend && pytest tests/test_phase6_onboarding.py -v

test-phase7:
	@echo "🧪 Running Phase 7 security tests..."
	@export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test" && \
	python3 Backend/scripts/init_test_db.py && \
	cd Backend && pytest tests/test_phase7_security.py -v

test-all:
	@echo "🧪 Running all Phase 6 + Phase 7 tests..."
	@export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test" && \
	python3 Backend/scripts/init_test_db.py && \
	cd Backend && pytest tests/test_phase6_onboarding.py tests/test_phase7_security.py -v
