#!/bin/bash
# Test Phase 6 onboarding endpoints against local convo_test database
#
# Usage: ./Backend/scripts/test_phase6.sh

set -e

echo "🧪 Phase 6 Test Runner"
echo "====================="
echo ""

# Set test database URL
export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test"

# Verify database exists
if ! psql -lqt | cut -d \| -f 1 | grep -qw convo_test; then
    echo "❌ ERROR: convo_test database does not exist"
    echo "   Create it with: createdb convo_test"
    exit 1
fi

echo "✅ Database: convo_test"
echo "🔧 Initializing schema..."

# Initialize database schema
python3 Backend/scripts/init_test_db.py

echo ""
echo "🧪 Running Phase 6 tests..."
echo ""

# Run Phase 6 tests
cd Backend
pytest tests/test_phase6_onboarding.py -v

echo ""
echo "✅ Phase 6 tests complete!"
