# Procast AI Agent

AI-powered budget analysis agent for the Procast event planning and budgeting platform.

## Overview

This project provides an intelligent conversational agent that can analyze budget data using natural language queries. It uses a hybrid architecture combining:

- **LangGraph** for workflow orchestration and state management
- **DSPy** for optimized prompt engineering and LLM interactions
- **Claude 3.5 Sonnet** as the primary reasoning engine
- **MCP (Model Context Protocol)** for safe database access

## Features

- **Natural Language Queries**: Ask questions about budget data in plain English
- **Intelligent Analysis**: AI-generated insights with confidence scores
- **Read-Only Safety**: All database access is validated and read-only
- **Comprehensive Analysis**: Budget overviews, overspending alerts, trend analysis
- **Multi-turn Conversations**: Session support for follow-up questions
- **JWT-Ready Auth**: Prepared for .NET backend JWT integration

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FastAPI                                  │
│                    (REST API Layer)                              │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                     LangGraph Agent                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ Classify │──│ Generate │──│ Validate │──│ Execute  │        │
│  │  Intent  │  │   SQL    │  │   SQL    │  │  Query   │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
│                                                    │             │
│                              ┌──────────┐  ┌──────▼───────┐     │
│                              │ Response │──│   Analyze    │     │
│                              │  Format  │  │   Results    │     │
│                              └──────────┘  └──────────────┘     │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                      DSPy Modules                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │IntentClassify│  │ SQLGenerator │  │AnalysisSynth │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                     MCP Tools Layer                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ SQL Validator│  │ Query Tools  │  │ Schema Info  │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│              PostgreSQL (Read-Only Access)                       │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Anthropic API key

### Installation

1. **Clone and setup:**
```bash
cd procast-ai
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

2. **Configure environment:**
```bash
cp env.example .env
# Edit .env with your settings, especially ANTHROPIC_API_KEY
```

3. **Setup database:**
```bash
# Restore the database dump
./scripts/setup_db.sh dump-demo-procast-202601271555.sql
```

4. **Run the API:**
```bash
python -m uvicorn src.api.main:app --reload
```

5. **Access the API:**
- API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/health

### Using Docker

```bash
# Set your Anthropic API key
export ANTHROPIC_API_KEY=your-key-here

# Start all services
docker-compose up -d

# Run database setup (first time only)
docker-compose --profile setup run db-setup
```

## API Usage

### Analyze Budget Data

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -H "X-User-ID: test-user" \
  -d '{"query": "What is the total budget for all projects?"}'
```

### Quick Analysis Endpoints

```bash
# Budget overview
curl http://localhost:8000/api/v1/quick-analysis/budgets \
  -H "X-User-ID: test-user"

# Overspending alerts
curl http://localhost:8000/api/v1/quick-analysis/overspending \
  -H "X-User-ID: test-user"

# Category breakdown
curl http://localhost:8000/api/v1/quick-analysis/categories \
  -H "X-User-ID: test-user"
```

### Get Schema Information

```bash
curl http://localhost:8000/api/v1/schema \
  -H "X-User-ID: test-user"
```

## Project Structure

```
procast-ai/
├── docs/                      # Documentation
│   ├── DATABASE_SCHEMA.md     # Database schema documentation
│   └── ERD.md                 # Entity relationship diagrams
├── scripts/                   # Setup scripts
│   └── setup_db.sh           # Database setup script
├── data/training/            # DSPy training data
│   ├── sql_examples.json     # SQL generation examples
│   └── analysis_examples.json # Analysis examples
├── src/
│   ├── api/                  # FastAPI application
│   │   ├── main.py          # App entry point
│   │   ├── schemas.py       # Pydantic models
│   │   ├── routes/          # API routes
│   │   └── middleware/      # Auth middleware
│   ├── agent/               # LangGraph agent
│   │   ├── graph.py         # Workflow definition
│   │   ├── state.py         # Agent state
│   │   ├── nodes.py         # Node functions
│   │   └── routing.py       # Conditional routing
│   ├── dspy_modules/        # DSPy modules
│   │   ├── config.py        # LLM configuration
│   │   ├── sql_generator.py # SQL generation
│   │   ├── analyzer.py      # Analysis synthesis
│   │   ├── classifier.py    # Intent classification
│   │   └── metrics.py       # Evaluation metrics
│   ├── mcp/                 # MCP server
│   │   ├── server.py        # MCP server
│   │   └── tools.py         # Database tools
│   ├── db/                  # Database layer
│   │   ├── connection.py    # Connection management
│   │   └── schema_registry.py # Domain-split schema definitions
│   ├── eval/                # Evaluation
│   │   └── validator.py     # SQL/result validation
│   └── core/                # Core utilities
│       ├── config.py        # Settings
│       └── retry.py         # Retry logic
├── tests/                   # Test suite
├── docker-compose.yml       # Docker setup
├── Dockerfile              # Container definition
└── requirements.txt        # Dependencies
```

## Configuration

Key environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL_READONLY` | Read-only database URL | Required |
| `ANTHROPIC_API_KEY` | Claude API key | Required |
| `LLM_MODEL` | Claude model | `claude-3-5-sonnet-20241022` |
| `API_PORT` | API port | `8000` |
| `LOG_LEVEL` | Logging level | `INFO` |

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_mcp.py -v
```

## Security

- **Read-Only Access**: The agent uses a PostgreSQL user with SELECT-only permissions
- **SQL Validation**: All generated SQL is validated before execution
- **No DDL/DML**: INSERT, UPDATE, DELETE, DROP operations are blocked
- **Query Timeout**: 30-second timeout on all queries
- **JWT Ready**: Auth middleware prepared for JWT token validation

## Future Integration

When the .NET backend provides JWT specifications:

1. Update `src/api/middleware/auth.py` with JWT validation
2. Configure JWT settings in environment
3. The agent will automatically scope queries to the authenticated user

## License

MIT

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request
