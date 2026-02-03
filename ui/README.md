# Procast AI Chat UI

A minimal Chainlit-based chat interface for the Procast AI Budget Analysis Agent.

## Setup

1. Install dependencies:
```bash
cd ui
pip install -r requirements.txt
```

2. Make sure the FastAPI backend is running:
```bash
# From the project root
uvicorn src.api.main:app --reload
```

3. Run the Chainlit UI:
```bash
cd ui
chainlit run app.py
```

4. Open your browser to http://localhost:8000 (Chainlit default port)

## Configuration

Set these environment variables to customize the UI:

- `PROCAST_API_URL`: Backend API URL (default: `http://localhost:8000`)
- `PROCAST_USER_EMAIL`: Default user email for testing (default: `jamestraynor@example.com`)
- `PROCAST_USER_ID`: Default user ID (default: `chainlit-user`)

## Features

- **Streaming responses**: See the AI's response as it's generated
- **Session persistence**: Conversation history is saved to the session database
- **RLS scoping**: Users only see data they have access to
- **SQL visibility**: View the generated SQL queries

## Architecture

```
┌─────────────┐    SSE Stream    ┌─────────────┐    RLS-Scoped    ┌──────────┐
│  Chainlit   │ ◄──────────────► │   FastAPI   │ ◄──────────────► │ Postgres │
│     UI      │    /analyze/     │   Backend   │     Queries      │    DB    │
└─────────────┘     stream       └─────────────┘                  └──────────┘
                                        │
                                        ▼
                                 ┌─────────────┐
                                 │   SQLite    │
                                 │  Sessions   │
                                 └─────────────┘
```
