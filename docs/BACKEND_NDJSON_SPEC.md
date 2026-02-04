# Backend NDJSON Stream Specification

This document specifies the exact stream format required by the Vercel AI SDK v5+ `DefaultChatTransport`.

## Current Issue

The backend currently sends **SSE format**:
```
data: {"type": "text-delta", "id": "text-1", "delta": "Hello"}

data: {"type": "text-delta", "id": "text-1", "delta": " world"}

```

The AI SDK expects **NDJSON format** (Newline-Delimited JSON):
```
{"type": "text-delta", "id": "text-1", "delta": "Hello"}
{"type": "text-delta", "id": "text-1", "delta": " world"}
```

## Required Changes

### 1. Response Headers

Change from:
```
Content-Type: text/event-stream; charset=utf-8
```

To:
```
Content-Type: text/plain; charset=utf-8
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
```

### 2. Stream Format

Change from SSE format:
```
data: {"type": "start"}\n\n
data: {"type": "text-delta", "id": "text-1", "delta": "Hello"}\n\n
data: {"type": "finish"}\n\n
```

To NDJSON format (one JSON object per line, no `data:` prefix):
```
{"type": "start"}\n
{"type": "text-delta", "id": "text-1", "delta": "Hello"}\n
{"type": "finish"}\n
```

**Key differences:**
- NO `data:` prefix
- Single newline `\n` after each JSON object (not double `\n\n`)
- Each line is a complete, valid JSON object

## Event Types (Unchanged)

The event types and their fields remain the same as in `CHAT_API_PROTOCOL.md`:

### Lifecycle Events

```json
{"type": "start"}
{"type": "finish"}
```

### Text Streaming Events

```json
{"type": "text-start", "id": "text-abc123"}
{"type": "text-delta", "id": "text-abc123", "delta": "Hello "}
{"type": "text-end", "id": "text-abc123"}
```

### Tool Events

```json
{"type": "tool-input-start", "toolCallId": "call_xyz", "toolName": "query_database"}
{"type": "tool-input-available", "toolCallId": "call_xyz", "toolName": "query_database", "input": {"query": "SELECT..."}}
{"type": "tool-output-available", "toolCallId": "call_xyz", "output": {"rows": [], "row_count": 5}}
{"type": "tool-output-error", "toolCallId": "call_xyz", "errorText": "Connection timeout"}
```

### Error Events

```json
{"type": "error", "errorText": "Rate limit exceeded"}
```

## Complete Example: Simple Text Response

**Old SSE format (current):**
```
data: {"type": "start"}

data: {"type": "text-start", "id": "text-1"}

data: {"type": "text-delta", "id": "text-1", "delta": "Hello, "}

data: {"type": "text-delta", "id": "text-1", "delta": "how can I help?"}

data: {"type": "text-end", "id": "text-1"}

data: {"type": "finish"}

```

**New NDJSON format (required):**
```
{"type": "start"}
{"type": "text-start", "id": "text-1"}
{"type": "text-delta", "id": "text-1", "delta": "Hello, "}
{"type": "text-delta", "id": "text-1", "delta": "how can I help?"}
{"type": "text-end", "id": "text-1"}
{"type": "finish"}
```

## Complete Example: Agent with Tool Usage

**NDJSON format:**
```
{"type": "start"}
{"type": "tool-input-start", "toolCallId": "call_1", "toolName": "select_tables"}
{"type": "tool-input-available", "toolCallId": "call_1", "toolName": "select_tables", "input": {"domains": ["expenses"]}}
{"type": "tool-output-available", "toolCallId": "call_1", "output": {"selected_tables": ["expenses"]}}
{"type": "text-start", "id": "text-1"}
{"type": "text-delta", "id": "text-1", "delta": "Based on the data, "}
{"type": "text-delta", "id": "text-1", "delta": "Engineering has the highest spending."}
{"type": "text-end", "id": "text-1"}
{"type": "finish"}
```

## Python Implementation Example

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import json

async def generate_ndjson_stream():
    """Generator that yields NDJSON lines."""
    
    # Start event
    yield json.dumps({"type": "start"}) + "\n"
    
    # Text streaming
    yield json.dumps({"type": "text-start", "id": "text-1"}) + "\n"
    
    for chunk in ["Hello, ", "how can ", "I help?"]:
        yield json.dumps({
            "type": "text-delta",
            "id": "text-1",
            "delta": chunk
        }) + "\n"
    
    yield json.dumps({"type": "text-end", "id": "text-1"}) + "\n"
    
    # Finish event
    yield json.dumps({"type": "finish"}) + "\n"

@app.post("/api/v1/chat/stream")
async def chat_stream(request: ChatRequest):
    return StreamingResponse(
        generate_ndjson_stream(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
```

## Summary of Changes

| Aspect | Old (SSE) | New (NDJSON) |
|--------|-----------|--------------|
| Content-Type | `text/event-stream` | `text/plain; charset=utf-8` |
| Line prefix | `data: ` | None |
| Line terminator | `\n\n` (double) | `\n` (single) |
| Format | SSE | NDJSON |

## Validation

Each line in the stream must:
1. Be valid JSON
2. Have a `type` field
3. End with a single newline character `\n`
4. NOT have any prefix like `data:` or `event:`
