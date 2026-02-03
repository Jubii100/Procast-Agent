# Procast AI Agent

AI-powered budget analysis agent for the Procast event planning and budgeting platform.

## Overview

This project provides an intelligent conversational agent that can analyze budget data using natural language queries. It uses a hybrid architecture combining:

- **LangGraph** for workflow orchestration and state management
- **DSPy** for optimized prompt engineering and LLM interactions
- **Claude 3.5 Sonnet** as the primary reasoning engine
- **PostgreSQL** with Row-Level Security (RLS) for safe, scoped database access
- **SQLite** for session/chat history persistence

## Features

- **Natural Language Queries**: Ask questions about budget data in plain English
- **Intelligent Analysis**: AI-generated insights with confidence scores
- **Read-Only Safety**: All database access is validated and read-only
- **Row-Level Security (RLS)**: Queries are automatically scoped to user permissions
- **Session Management**: Full conversation history persistence and retrieval
- **Real-Time Streaming**: Server-Sent Events (SSE) for token-by-token response streaming
- **Multi-turn Conversations**: Context-aware follow-up questions within sessions
- **JWT-Ready Auth**: Prepared for .NET backend JWT integration

---

## Front-End Developer Guide

This section provides everything a front-end developer needs to build a Next.js interface around the Procast AI API.

### Base URL

```
Development: http://localhost:8000
Production: https://api.procast.ai (TBD)
```

### Authentication

The API uses header-based authentication with support for both development (mock) and production (JWT) modes.

#### Development Mode (Current)

```typescript
// Required headers for all authenticated requests
const headers = {
  'Content-Type': 'application/json',
  'X-User-ID': 'user-uuid',           // Required: User identifier
  'X-User-Email': 'user@example.com', // Optional: Enables RLS scoping
};
```

#### Production Mode (Future JWT)

```typescript
const headers = {
  'Content-Type': 'application/json',
  'Authorization': 'Bearer <jwt_token>',
};
```

**JWT Claims (Expected):**
| Claim | Description |
|-------|-------------|
| `sub` | User ID |
| `email` | User email (for RLS person lookup) |
| `person_id` | Procast People.Id (preferred for RLS) |
| `company_id` | Procast Companies.Id |
| `roles` | User roles array |
| `scope` | Permission scopes (e.g., `budget:read budget:analyze`) |

---

### API Endpoints

#### 1. Health Check

```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "database": {
    "status": "healthy",
    "readonly_connection": true,
    "table_count": 42
  },
  "agent": {
    "status": "ready",
    "llm_configured": true,
    "session_db": { "status": "healthy" }
  },
  "timestamp": "2026-02-03T10:00:00Z"
}
```

---

#### 2. Analyze (Non-Streaming)

Submit a natural language query and receive a complete response.

```http
POST /api/v1/analyze
Content-Type: application/json
X-User-ID: <user-id>
X-User-Email: <user-email>

{
  "query": "What is the total budget for all projects?",
  "session_id": "optional-session-uuid",
  "context": {}
}
```

**Response:**
```json
{
  "response": "Based on the query results, the total budget across all projects is $1,234,567...",
  "analysis": "Detailed analysis text...",
  "recommendations": "Consider reviewing Project X which is at 95% budget utilization...",
  "confidence": 0.92,
  "data": [
    {"project_name": "Project A", "budget": 500000, "spent": 450000},
    {"project_name": "Project B", "budget": 300000, "spent": 150000}
  ],
  "row_count": 2,
  "session_id": "uuid-of-session",
  "sql_query": "SELECT project_name, budget, spent FROM projects...",
  "metadata": {
    "intent": "db_query",
    "selected_domains": ["projects", "budgets"],
    "total_llm_calls": 4,
    "total_db_queries": 1
  },
  "error": null
}
```

---

#### 3. Streaming Analysis (SSE) ⭐ **Recommended for UI**

Real-time token streaming via Server-Sent Events for responsive UI.

```http
POST /api/v1/analyze/stream
Content-Type: application/json
X-User-ID: <user-id>
X-User-Email: <user-email>

{
  "query": "Show me overspending projects",
  "session_id": "optional-session-uuid"
}
```

**SSE Event Types:**

| Event | Description | Payload |
|-------|-------------|---------|
| `session` | Session ID for the conversation | `{ "session_id": "uuid" }` |
| `status` | Processing status updates | `{ "status": "classifying", "message": "..." }` |
| `sql` | Generated SQL query | `{ "sql": "SELECT ..." }` |
| `token` | Individual response token | `{ "token": "The" }` |
| `complete` | Stream finished | `{ "session_id", "sql_query", "row_count", "domains" }` |
| `error` | Error occurred | `{ "error": "message", "session_id" }` |

**Status Flow:**
```
classifying → selecting_domains → loading_schema → generating_sql → executing_query → analyzing → complete
```

**TypeScript Example:**

```typescript
interface StreamEvent {
  event: 'session' | 'status' | 'sql' | 'token' | 'complete' | 'error';
  data: any;
}

async function streamAnalysis(query: string, sessionId?: string) {
  const response = await fetch('/api/v1/analyze/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-User-ID': userId,
      'X-User-Email': userEmail,
    },
    body: JSON.stringify({ query, session_id: sessionId }),
  });

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('event:')) {
        const eventType = line.split('event: ')[1].split('\n')[0];
        const dataLine = line.split('data: ')[1];
        const data = JSON.parse(dataLine);

        switch (eventType) {
          case 'session':
            setSessionId(data.session_id);
            break;
          case 'status':
            setStatus(data.message);
            break;
          case 'token':
            appendToResponse(data.token);
            break;
          case 'complete':
            setComplete(data);
            break;
          case 'error':
            setError(data.error);
            break;
        }
      }
    }
  }
}
```

---

#### 4. Session Management

##### Create Session

```http
POST /api/v1/sessions
Content-Type: application/json

{
  "title": "Budget Review Q1 2026"  // Optional
}
```

**Response:**
```json
{
  "id": "session-uuid",
  "user_id": "user-uuid",
  "email": "user@example.com",
  "person_id": "procast-person-uuid",
  "company_id": "procast-company-uuid",
  "title": "Budget Review Q1 2026",
  "created_at": "2026-02-03T10:00:00Z",
  "last_activity": "2026-02-03T10:00:00Z",
  "message_count": 0
}
```

##### List Sessions (for Sidebar)

```http
GET /api/v1/sessions?limit=50&offset=0
```

**Response:**
```json
{
  "sessions": [
    {
      "id": "session-uuid-1",
      "user_id": "user-uuid",
      "title": "Budget Review Q1 2026",
      "created_at": "2026-02-03T10:00:00Z",
      "last_activity": "2026-02-03T11:30:00Z",
      "message_count": 8
    },
    {
      "id": "session-uuid-2",
      "user_id": "user-uuid",
      "title": "Overspending Analysis",
      "created_at": "2026-02-02T14:00:00Z",
      "last_activity": "2026-02-02T14:45:00Z",
      "message_count": 12
    }
  ],
  "total": 2
}
```

##### Get Session with Messages (Load Chat History)

```http
GET /api/v1/sessions/{session_id}
```

**Response:**
```json
{
  "session": {
    "id": "session-uuid",
    "user_id": "user-uuid",
    "title": "Budget Review Q1 2026",
    "created_at": "2026-02-03T10:00:00Z",
    "last_activity": "2026-02-03T11:30:00Z",
    "message_count": 4
  },
  "messages": [
    {
      "id": 1,
      "session_id": "session-uuid",
      "role": "user",
      "content": "What is the total budget?",
      "timestamp": "2026-02-03T10:00:00Z",
      "metadata": null
    },
    {
      "id": 2,
      "session_id": "session-uuid",
      "role": "assistant",
      "content": "Based on my analysis...",
      "timestamp": "2026-02-03T10:00:05Z",
      "metadata": {
        "confidence": 0.92,
        "row_count": 15
      }
    }
  ]
}
```

##### Update Session Title

```http
PATCH /api/v1/sessions/{session_id}
Content-Type: application/json

{
  "title": "New Session Title"
}
```

##### Get Session Messages Only

```http
GET /api/v1/sessions/{session_id}/messages?limit=100
```

##### Get Session Events (Agent Behavior Logs)

```http
GET /api/v1/sessions/{session_id}/events?event_type=sql_generated&limit=50
```

**Event Types:**
- `sql_generated` - SQL query was generated
- `query_completed` - Database query completed
- `stream_completed` - Streaming response finished

---

#### 5. Quick Analysis Endpoints

Pre-built queries for common analysis tasks.

```http
GET /api/v1/quick-analysis/budgets?limit=10
GET /api/v1/quick-analysis/overspending?threshold=90
GET /api/v1/quick-analysis/categories?top_n=10
```

---

#### 6. Schema Information

```http
GET /api/v1/schema/summary
GET /api/v1/schema/domains
GET /api/v1/schema/domains/{domain_name}
GET /api/v1/schema/tables
GET /api/v1/schema/tables/{table_name}
GET /api/v1/schema/tables/{table_name}/sample?limit=5
```

---

### Data Models (TypeScript Types)

```typescript
// Session Types
interface Session {
  id: string;
  user_id: string;
  email?: string;
  person_id?: string;
  company_id?: string;
  title?: string;
  created_at: string;
  last_activity: string;
  message_count: number;
}

interface Message {
  id: number;
  session_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  metadata?: {
    confidence?: number;
    row_count?: number;
    [key: string]: any;
  };
}

// Analysis Types
interface AnalyzeRequest {
  query: string;
  session_id?: string;
  context?: Record<string, any>;
}

interface AnalyzeResponse {
  response: string;
  analysis?: string;
  recommendations?: string;
  confidence: number;
  data?: Record<string, any>[];
  row_count: number;
  session_id: string;
  sql_query?: string;
  metadata?: {
    intent: string;
    selected_domains: string[];
    total_llm_calls: number;
    total_db_queries: number;
  };
  error?: string;
}

// Streaming Types
interface StreamSessionEvent {
  session_id: string;
}

interface StreamStatusEvent {
  status: string;
  message: string;
  row_count?: number;
}

interface StreamTokenEvent {
  token: string;
}

interface StreamCompleteEvent {
  session_id: string;
  sql_query: string;
  row_count: number;
  domains: string[];
  response_length: number;
}

interface StreamErrorEvent {
  error: string;
  session_id?: string;
}
```

---

### CORS Configuration

The API accepts requests from:
- `http://localhost:3000` (Next.js dev)
- `http://localhost:8080`
- Additional origins configurable via `CORS_ORIGINS` env var

---

## Architecture

### System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Next.js Frontend                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │  Chat UI     │  │  Sessions    │  │  Analysis    │  │  Streaming   │    │
│  │  Component   │  │  Sidebar     │  │  Display     │  │  Handler     │    │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │ HTTP/SSE
┌───────────────────────────────▼─────────────────────────────────────────────┐
│                           FastAPI (REST + SSE)                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐    │
│  │   Auth      │  │  Analyze    │  │  Sessions   │  │   Streaming     │    │
│  │ Middleware  │  │   Routes    │  │   Routes    │  │   Routes        │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────┘    │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────────────┐
│                          LangGraph Agent                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ Classify │──│ Select   │──│ Generate │──│ Validate │──│ Execute  │      │
│  │  Intent  │  │ Domains  │  │   SQL    │  │   SQL    │  │  Query   │      │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘      │
│                                                               │              │
│                               ┌──────────┐  ┌──────────────▼─────┐         │
│                               │ Response │──│   Analyze Results  │         │
│                               │  Format  │  └────────────────────┘         │
│                               └──────────┘                                  │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────────────┐
│                          DSPy Modules                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │IntentClassify│  │TableSelector │  │ SQLGenerator │  │AnalysisSynth │    │
│  │   (Haiku)    │  │   (Haiku)    │  │  (Sonnet)    │  │   (Sonnet)   │    │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
┌───────▼───────┐     ┌─────────▼─────────┐    ┌───────▼───────┐
│   PostgreSQL   │     │      SQLite       │    │    Claude     │
│ (Procast Data) │     │ (Session History) │    │   (Anthropic) │
│    + RLS       │     │                   │    │               │
└────────────────┘     └───────────────────┘    └───────────────┘
```

### Agent Workflow

```
User Query
    │
    ▼
┌─────────────────┐
│ Classify Intent │──────────────────────────┐
│    (Haiku)      │                          │
└────────┬────────┘                          │
         │                                   │
    ┌────┴────┬─────────────┬──────────┐    │
    │         │             │          │    │
    ▼         ▼             ▼          ▼    │
db_query  clarify    general_info  friendly │
    │         │             │        chat   │
    │         ▼             ▼          │    │
    │    Return          Return        │    │
    │   Questions        Info          │    │
    │                                  │    │
    ▼                                  ▼    │
┌─────────────────┐              Return     │
│ Select Domains  │              Greeting   │
│    (Haiku)      │                         │
└────────┬────────┘                         │
         │                                  │
         ▼                                  │
┌─────────────────┐                         │
│  Generate SQL   │◄────────────────────────┤
│    (Sonnet)     │    Retry on Error       │
└────────┬────────┘    (max 3 attempts)     │
         │                                  │
         ▼                                  │
┌─────────────────┐                         │
│  Validate SQL   │                         │
│ (SELECT only)   │                         │
└────────┬────────┘                         │
         │                                  │
         ▼                                  │
┌─────────────────┐                         │
│ Execute Query   │                         │
│  (with RLS)     │                         │
└────────┬────────┘                         │
         │                                  │
         ▼                                  │
┌─────────────────┐                         │
│ Analyze Results │                         │
│    (Sonnet)     │                         │
└────────┬────────┘                         │
         │                                  │
         ▼                                  │
┌─────────────────┐                         │
│ Format Response │─────────────────────────┘
└─────────────────┘
```

### Intent Types

| Intent | Description | Database Access |
|--------|-------------|-----------------|
| `db_query` | Question requiring data analysis | Yes |
| `clarify` | Ambiguous question needing clarification | No |
| `general_info` | Question about system capabilities | No |
| `friendly_chat` | Greetings and social interaction | No |

---

## Session Management & Chat History

### Storage Architecture

- **Session Database**: SQLite (`.data/procast_ai.db`)
- **Tables**: `sessions`, `messages`, `events`
- **Persistence**: All conversations are automatically persisted

### Session Lifecycle

1. **Auto-Creation**: Sessions are created automatically on first message if no `session_id` provided
2. **Title Generation**: Auto-generated from first query (first 50 chars)
3. **Activity Tracking**: `last_activity` updated on every message
4. **History Loading**: Agent loads last 20 messages for context on each request

### Data Model

```sql
-- Sessions table
sessions (
  id          VARCHAR(36) PRIMARY KEY,  -- UUID
  user_id     VARCHAR(256) NOT NULL,
  email       VARCHAR(256),
  person_id   VARCHAR(36),              -- For RLS
  company_id  VARCHAR(36),
  title       VARCHAR(512),
  created_at  DATETIME,
  last_activity DATETIME
)

-- Messages table  
messages (
  id          INTEGER PRIMARY KEY,
  session_id  VARCHAR(36) REFERENCES sessions(id),
  role        VARCHAR(20),              -- 'user', 'assistant', 'system'
  content     TEXT,
  timestamp   DATETIME,
  metadata    TEXT                      -- JSON
)

-- Events table (agent behavior tracking)
events (
  id          INTEGER PRIMARY KEY,
  session_id  VARCHAR(36) REFERENCES sessions(id),
  event_type  VARCHAR(50),              -- 'sql_generated', 'query_completed', etc.
  payload     TEXT,                     -- JSON
  timestamp   DATETIME
)
```

---

## Row-Level Security (RLS)

### How RLS Works

1. **Email Lookup**: User's email is used to find their `People.Id` in Procast
2. **Session Variable**: `app.current_person_id` is set on each database session
3. **Policy Enforcement**: PostgreSQL RLS policies filter data based on this variable
4. **Scope**: Users only see data for projects they're associated with

### Implementation

```python
# Automatic RLS scoping in the agent
async with DatabaseManager.get_scoped_session(
    person_id=user.person_id,  # From JWT
    email=user.email,          # Fallback lookup
) as session:
    # All queries in this session are RLS-filtered
    result = await tools.execute_query(sql)
```

---

## Roadmap: Session Management & Sidebar Feature

### Current State (Implemented ✅)

- [x] Session creation and persistence
- [x] Message storage with role tracking
- [x] Event logging for agent behavior
- [x] List sessions endpoint with pagination
- [x] Get session with messages
- [x] Update session title
- [x] Auto-title generation from first query
- [x] Conversation history context (last 20 messages)

### Phase 1: Enhanced Session Management 🔄

- [ ] **Session Search**: Full-text search across session messages
  ```http
  GET /api/v1/sessions/search?q=budget+overspending
  ```

- [ ] **Session Delete**: Soft-delete with archive
  ```http
  DELETE /api/v1/sessions/{session_id}
  ```

- [ ] **Session Export**: Export session as JSON/PDF
  ```http
  GET /api/v1/sessions/{session_id}/export?format=json
  ```

- [ ] **Session Metadata**: Tags, favorites, pinning
  ```http
  PATCH /api/v1/sessions/{session_id}
  { "tags": ["q1", "review"], "pinned": true }
  ```

### Phase 2: Advanced Chat Features 📋

- [ ] **Message Reactions**: Feedback on responses
  ```http
  POST /api/v1/sessions/{session_id}/messages/{message_id}/react
  { "reaction": "helpful" | "unhelpful" | "incorrect" }
  ```

- [ ] **Message Editing**: Edit user messages (creates new branch)
  ```http
  PATCH /api/v1/sessions/{session_id}/messages/{message_id}
  { "content": "Updated question..." }
  ```

- [ ] **Suggested Follow-ups**: AI-generated follow-up questions
  ```json
  {
    "response": "...",
    "suggested_followups": [
      "Which project has the highest overspending?",
      "Show me the trend over the last 6 months"
    ]
  }
  ```

- [ ] **Context Memory**: Session-level memory for entities
  ```json
  {
    "context": {
      "current_project": "Project Alpha",
      "time_range": "Q1 2026",
      "focus_metrics": ["budget", "spent"]
    }
  }
  ```

### Phase 3: Collaboration Features 🤝

- [ ] **Shared Sessions**: Share read-only link
- [ ] **Session Templates**: Save and reuse query templates
- [ ] **Scheduled Reports**: Recurring analysis delivery

### Phase 4: Analytics & Insights 📊

- [ ] **Usage Analytics**: Query patterns, common questions
- [ ] **Performance Metrics**: Response times, token usage
- [ ] **User Feedback Analysis**: Improve model based on reactions

---

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+ (with Procast database)
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
# Edit .env with your settings:
# - ANTHROPIC_API_KEY
# - DATABASE_URL_READONLY
# - MOCK_USER_ID and MOCK_USER_EMAIL for testing
```

3. **Run the API:**
```bash
python -m uvicorn src.api.main:app --reload
```

4. **Access:**
- API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/health

### Using Docker

```bash
export ANTHROPIC_API_KEY=your-key-here
docker-compose up -d
```

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL_READONLY` | Read-only PostgreSQL URL | Required |
| `ANTHROPIC_API_KEY` | Claude API key | Required |
| `LLM_MODEL` | Primary Claude model | `claude-3-5-sonnet-20241022` |
| `LLM_AUXILIARY_MODEL` | Cheap model for classification | `claude-3-5-haiku-20241022` |
| `API_PORT` | API server port | `8000` |
| `CORS_ORIGINS` | Comma-separated CORS origins | `localhost:3000,localhost:8080` |
| `SESSION_DB_PATH` | SQLite path for sessions | `./.data/procast_ai.db` |
| `MOCK_USER_ID` | Default user ID for testing | `test-user-123` |
| `MOCK_USER_EMAIL` | Default email for testing | `test@procast.local` |

---

## Security

### Safety Measures

- **Read-Only Access**: PostgreSQL user has SELECT-only permissions
- **SQL Validation**: Only SELECT statements allowed, DDL/DML blocked
- **RLS Enforcement**: Row-level security filters all queries
- **Query Timeout**: 30-second maximum query execution
- **UUID Validation**: person_id validated before RLS session var set
- **No Secrets in Responses**: SQL queries sanitized before returning

### Protected Paths

Public (no auth required):
- `/health`
- `/docs`
- `/openapi.json`
- `/redoc`

---

## Project Structure

```
procast-ai/
├── src/
│   ├── api/                  # FastAPI application
│   │   ├── main.py          # App entry point & lifespan
│   │   ├── schemas.py       # Pydantic request/response models
│   │   ├── streaming.py     # SSE token streaming utilities
│   │   ├── middleware/
│   │   │   └── auth.py      # Auth middleware & user context
│   │   └── routes/
│   │       ├── analyze.py   # Analysis endpoints
│   │       ├── stream.py    # Streaming SSE endpoint
│   │       ├── sessions.py  # Session CRUD endpoints
│   │       └── schema.py    # Schema introspection
│   ├── agent/               # LangGraph agent
│   │   ├── graph.py         # Workflow definition
│   │   ├── state.py         # Agent state TypedDict
│   │   ├── nodes.py         # Node functions
│   │   └── routing.py       # Conditional routing
│   ├── sessions/            # Session persistence
│   │   ├── db.py            # SQLite connection
│   │   ├── models.py        # SQLAlchemy models
│   │   └── repo.py          # Repository pattern CRUD
│   ├── dspy_modules/        # DSPy LLM modules
│   │   ├── classifier.py    # Intent classification
│   │   ├── table_selector.py # Domain selection
│   │   ├── sql_generator.py # SQL generation
│   │   └── analyzer.py      # Results analysis
│   ├── db/                  # Database layer
│   │   ├── connection.py    # Async PostgreSQL + RLS
│   │   └── schema_registry.py # Domain schema definitions
│   ├── mcp/                 # MCP tools layer
│   │   └── tools.py         # Database tools & validation
│   └── core/
│       └── config.py        # Pydantic settings
├── docs/                    # Documentation
├── tests/                   # Test suite
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_sessions.py -v
```

---

## License

MIT

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request
