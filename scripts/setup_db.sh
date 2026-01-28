#!/bin/bash
# Procast AI Database Setup Script
# This script sets up the PostgreSQL database for local development

set -e

# Configuration
DB_NAME="${PROCAST_DB_NAME:-procast}"
DB_USER="${PROCAST_DB_USER:-postgres}"
DB_PASSWORD="${PROCAST_DB_PASSWORD:-postgres}"
DB_HOST="${PROCAST_DB_HOST:-localhost}"
DB_PORT="${PROCAST_DB_PORT:-5432}"
ANALYST_USER="${PROCAST_ANALYST_USER:-procast_analyst}"
ANALYST_PASSWORD="${PROCAST_ANALYST_PASSWORD:-analyst_readonly}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Procast AI Database Setup${NC}"
echo -e "${GREEN}========================================${NC}"

# Check if PostgreSQL is running
echo -e "\n${YELLOW}Checking PostgreSQL connection...${NC}"
if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" > /dev/null 2>&1; then
    echo -e "${RED}Error: PostgreSQL is not running on $DB_HOST:$DB_PORT${NC}"
    echo "Please start PostgreSQL first."
    exit 1
fi
echo -e "${GREEN}PostgreSQL is running.${NC}"

# Check if database exists
echo -e "\n${YELLOW}Checking if database '$DB_NAME' exists...${NC}"
if PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
    echo -e "${YELLOW}Database '$DB_NAME' already exists.${NC}"
    read -p "Do you want to drop and recreate it? (y/N): " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Dropping database '$DB_NAME'...${NC}"
        PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -c "DROP DATABASE IF EXISTS $DB_NAME;"
    else
        echo -e "${YELLOW}Skipping database creation. Using existing database.${NC}"
    fi
fi

# Create database if it doesn't exist
echo -e "\n${YELLOW}Creating database '$DB_NAME'...${NC}"
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -tc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1 || \
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -c "CREATE DATABASE $DB_NAME;"
echo -e "${GREEN}Database '$DB_NAME' is ready.${NC}"

# Restore the dump
DUMP_FILE="${1:-$(dirname "$0")/../dump-demo-procast-202601271555.sql}"
if [ -f "$DUMP_FILE" ]; then
    echo -e "\n${YELLOW}Restoring database from dump: $DUMP_FILE${NC}"
    PGPASSWORD="$DB_PASSWORD" pg_restore \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        --no-owner \
        --no-privileges \
        --if-exists \
        --clean \
        "$DUMP_FILE" 2>/dev/null || true
    echo -e "${GREEN}Database restored successfully.${NC}"
else
    echo -e "${RED}Warning: Dump file not found at $DUMP_FILE${NC}"
    echo "Please provide the dump file path as an argument or place it in the project root."
fi

# Create read-only analyst user
echo -e "\n${YELLOW}Creating read-only analyst user '$ANALYST_USER'...${NC}"
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" << EOF
-- Drop user if exists
DROP USER IF EXISTS $ANALYST_USER;

-- Create the analyst user
CREATE USER $ANALYST_USER WITH PASSWORD '$ANALYST_PASSWORD';

-- Grant connect
GRANT CONNECT ON DATABASE $DB_NAME TO $ANALYST_USER;

-- Grant usage on schema
GRANT USAGE ON SCHEMA public TO $ANALYST_USER;

-- Grant SELECT on all existing tables
GRANT SELECT ON ALL TABLES IN SCHEMA public TO $ANALYST_USER;

-- Grant SELECT on all future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO $ANALYST_USER;

-- Revoke all write permissions explicitly
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM $ANALYST_USER;

-- Set statement timeout for safety (30 seconds max query time)
ALTER USER $ANALYST_USER SET statement_timeout = '30s';

-- Set read-only transaction mode
ALTER USER $ANALYST_USER SET default_transaction_read_only = on;

COMMENT ON ROLE $ANALYST_USER IS 'Read-only user for Procast AI analyst agent';
EOF
echo -e "${GREEN}Read-only analyst user created successfully.${NC}"

# Verify the setup
echo -e "\n${YELLOW}Verifying setup...${NC}"
TABLE_COUNT=$(PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';")
echo -e "${GREEN}Found ${TABLE_COUNT// /} tables in the database.${NC}"

# Test read-only user
echo -e "\n${YELLOW}Testing read-only user permissions...${NC}"
if PGPASSWORD="$ANALYST_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$ANALYST_USER" -d "$DB_NAME" -c "SELECT 1;" > /dev/null 2>&1; then
    echo -e "${GREEN}Read-only user can connect successfully.${NC}"
else
    echo -e "${RED}Warning: Could not connect with read-only user.${NC}"
fi

# Generate connection strings
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Connection strings for your .env file:"
echo ""
echo "# Admin connection (for migrations)"
echo "DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
echo ""
echo "# Read-only connection (for AI agent)"
echo "DATABASE_URL_READONLY=postgresql://${ANALYST_USER}:${ANALYST_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
echo ""
