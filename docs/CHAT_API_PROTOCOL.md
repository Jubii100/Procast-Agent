# Procast Chat API Protocol (FastAPI → Next.js UI)

This document describes the backend API contract for the Next.js chat UI using the **Vercel AI SDK 5+ UI Message Stream Protocol** with **NDJSON format**.

## Base URL + Versioning

- Base prefix: `/api/v1`
- Streaming chat endpoint: `/api/v1/chat/stream`

## Auth

All non-public endpoints require a JWT Bearer token:

```
Authorization: Bearer <jwt>
```

Behavior:
- `401` for missing/invalid token
- `403` for valid token without access to a resource (session ownership)

## Data Shapes

### Session
```json
{
  "id": "sess_123",
  "title": "My chat",
  "created_at": "2026-02-03T12:00:00Z",
  "updated_at": "2026-02-03T12:10:00Z"
}
```

### Message (Backend)
```json
{
  "id": "msg_1",
  "session_id": "sess_123",
  "role": "user" | "assistant" | "system",
  "content": "Hello",
  "created_at": "2026-02-03T12:00:01Z"
}
```

### AI SDK Message (Frontend - New Format)
```json
{
  "role": "user",
  "parts": [
    { "type": "text", "text": "Hello" }
  ]
}
```

### AI SDK Message (Frontend - Legacy Format)
```json
{
  "role": "user",
  "content": "Hello"
}
```

Notes:
- Both `content` (legacy) and `parts` (new) formats are supported for backwards compatibility.
- When using `parts`, text content is extracted from parts with `type: "text"`.
- Timestamps are ISO 8601 in UTC.

## Endpoints

### `GET /api/v1/sessions`
Returns sessions for the authenticated user.

Response:
```json
[
  {
    "id": "sess_123",
    "title": "My chat",
    "created_at": "2026-02-03T12:00:00Z",
    "updated_at": "2026-02-03T12:10:00Z"
  }
]
```

Optional query params:
- `limit` (int)
- `offset` (int)

### `GET /api/v1/sessions/{session_id}`
Returns a session plus full message history.

Response:
```json
{
  "id": "sess_123",
  "title": "My chat",
  "created_at": "2026-02-03T12:00:00Z",
  "updated_at": "2026-02-03T12:10:00Z",
  "messages": [
    {
      "id": "msg_1",
      "session_id": "sess_123",
      "role": "user",
      "content": "Hello",
      "created_at": "2026-02-03T12:00:01Z"
    }
  ]
}
```

Notes:
- Messages are ordered ascending by `created_at`.
- `404` if session does not exist or is inaccessible.

### `POST /api/v1/chat/stream`
Streaming chat endpoint compatible with Vercel AI SDK 5+ `useChat`.

Request body:
```json
{
  "session_id": "sess_123",
  "messages": [
    {
      "role": "user",
      "parts": [
        { "type": "text", "text": "Hello" }
      ]
    }
  ],
  "model": "optional-model-id",
  "temperature": 0.7
}
```

Legacy request format (still supported):
```json
{
  "session_id": "sess_123",
  "messages": [
    { "role": "user", "content": "Hello" }
  ]
}
```

Rules:
- `session_id` is required (used for persistence).
- `messages` supports both `parts` array (new) and `content` string (legacy).

#### Stream Protocol: UI Message Stream (NDJSON)

Response headers:
- `Content-Type: text/plain; charset=utf-8`
- `Cache-Control: no-cache`
- `Connection: keep-alive`
- `X-Accel-Buffering: no`

**Format:** Newline-Delimited JSON (NDJSON) - one JSON object per line, no prefix, single newline terminator.

#### Event Types

##### Lifecycle Events

**start** - Begin stream:
```
{"type":"start"}
```

**finish** - End stream:
```
{"type":"finish"}
```

##### Text Streaming Events

**text-start** - Begin text part:
```
{"type":"text-start","id":"text-abc123"}
```

**text-delta** - Incremental text chunk:
```
{"type":"text-delta","id":"text-abc123","delta":"Hello "}
```

**text-end** - End text part:
```
{"type":"text-end","id":"text-abc123"}
```

##### Tool Events

**tool-input-start** - Tool call initiated:
```
{"type":"tool-input-start","toolCallId":"call_xyz","toolName":"query_database"}
```

**tool-input-available** - Tool arguments ready:
```
{"type":"tool-input-available","toolCallId":"call_xyz","toolName":"query_database","input":{"query":"SELECT..."}}
```

**tool-output-available** - Tool result ready:
```
{"type":"tool-output-available","toolCallId":"call_xyz","output":{"rows":[...],"row_count":5}}
```

**tool-output-error** - Tool execution failed:
```
{"type":"tool-output-error","toolCallId":"call_xyz","errorText":"Connection timeout"}
```

##### Error Events

**error** - Stream-level error:
```
{"type":"error","errorText":"Rate limit exceeded"}
```

#### Example: Simple Text Response

```
{"type":"start"}
{"type":"text-start","id":"text-1"}
{"type":"text-delta","id":"text-1","delta":"Hello, "}
{"type":"text-delta","id":"text-1","delta":"how can I help you?"}
{"type":"text-end","id":"text-1"}
{"type":"finish"}
```

#### Example: Agent with Tool Usage

```
{"type":"start"}
{"type":"tool-input-start","toolCallId":"call_1","toolName":"select_tables"}
{"type":"tool-input-available","toolCallId":"call_1","toolName":"select_tables","input":{"domains":["expenses","budgets"]}}
{"type":"tool-output-available","toolCallId":"call_1","output":{"selected_tables":["expenses","budgets"]}}
{"type":"tool-input-start","toolCallId":"call_2","toolName":"query_database"}
{"type":"tool-input-available","toolCallId":"call_2","toolName":"query_database","input":{"query":"SELECT category, SUM(amount) FROM expenses GROUP BY category"}}
{"type":"tool-output-available","toolCallId":"call_2","output":{"rows":[{"category":"Engineering","total":45000}],"row_count":1,"truncated":false}}
{"type":"text-start","id":"text-1"}
{"type":"text-delta","id":"text-1","delta":"Based on the data, "}
{"type":"text-delta","id":"text-1","delta":"Engineering has the highest spending."}
{"type":"text-end","id":"text-1"}
{"type":"finish"}
```

### Streaming Behavior

The backend streams events **in real-time as the agent executes**:

1. **Immediate start**: `start` event is sent immediately when the request is received
2. **Node-by-node progress**: As each agent node executes (classify_intent, select_tables, generate_sql, etc.), tool events are streamed:
   - `tool-input-start` when a node begins
   - `tool-input-available` with node input
   - `tool-output-available` with node result
3. **Final response**: After all nodes complete, the text response is streamed in chunks
4. **Finish**: `finish` event marks the end of the stream

This provides real-time feedback to users showing what the agent is doing (classifying intent, selecting tables, generating SQL, executing query, etc.) rather than waiting for the entire response.

### Persistence behavior
On each chat request:
- Store the latest user message in the session.
- Stream tool events as agent nodes execute.
- Stream the final response text in chunks.
- Persist the final assistant message to the session.

## Frontend integration notes

- Use `streamProtocol: "data"` in `useChat` (default for AI SDK 5+).
- Map backend `Message` objects directly to AI SDK messages.
- The chat endpoint is **not** a Next.js API route; it is served by FastAPI.
- Set `NEXT_PUBLIC_API_BASE_URL` if the API is not on `http://localhost:8000`.
- Store the JWT in `localStorage` under `procast_jwt`.

## Event Type Summary

| Event Type | Required Fields | Purpose |
|------------|-----------------|---------|
| `start` | - | Begin stream |
| `finish` | - | End stream |
| `text-start` | `id` | Begin text part |
| `text-delta` | `id`, `delta` | Incremental text |
| `text-end` | `id` | End text part |
| `tool-input-start` | `toolCallId`, `toolName` | Tool call initiated |
| `tool-input-available` | `toolCallId`, `toolName`, `input` | Tool args ready |
| `tool-output-available` | `toolCallId`, `output` | Tool result ready |
| `tool-output-error` | `toolCallId`, `errorText` | Tool execution failed |
| `error` | `errorText` | Stream-level error |
