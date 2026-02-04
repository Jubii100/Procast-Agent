# Backend API Upgrade Specification: UI Message Stream Protocol

This document specifies the required changes to upgrade the FastAPI backend chat API to be fully compatible with the Vercel AI SDK 5+ UI Message Stream Protocol. These changes will enable:

- Real-time text streaming (character-by-character or chunk-by-chunk)
- Live tool/agent status updates in the UI
- Proper message format compatibility with the frontend SDK

---

## Table of Contents

1. [Overview](#1-overview)
2. [Request Format Changes](#2-request-format-changes)
3. [Response Stream Protocol](#3-response-stream-protocol)
4. [Event Types Reference](#4-event-types-reference)
5. [Streaming Behavior Requirements](#5-streaming-behavior-requirements)
6. [Complete Examples](#6-complete-examples)
7. [Migration Checklist](#7-migration-checklist)

---

## 1. Overview

### Current Protocol (Legacy)

**Request:**
```json
{
  "session_id": "sess_123",
  "messages": [
    { "role": "user", "content": "Hello" }
  ]
}
```

**Response (SSE):**
```
data: {"type":"text","value":"Hello world"}

data: {"type":"finish"}
```

### New Protocol (UI Message Stream)

**Request:**
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
  ]
}
```

**Response (SSE):**
```
data: {"type":"start"}

data: {"type":"text-start","id":"text-1"}

data: {"type":"text-delta","id":"text-1","delta":"Hello"}

data: {"type":"text-delta","id":"text-1","delta":" world"}

data: {"type":"text-end","id":"text-1"}

data: {"type":"finish"}
```

---

## 2. Request Format Changes

### Message Structure

Each message in the `messages` array should support both formats for backwards compatibility:

```typescript
interface Message {
  role: "user" | "assistant" | "system";
  
  // Legacy format (still accept for backwards compatibility)
  content?: string;
  
  // New format (preferred)
  parts?: MessagePart[];
}

type MessagePart = 
  | TextPart 
  | ToolCallPart 
  | ToolResultPart;

interface TextPart {
  type: "text";
  text: string;
}

interface ToolCallPart {
  type: "tool-call";
  toolCallId: string;
  toolName: string;
  args: Record<string, unknown>;
}

interface ToolResultPart {
  type: "tool-result";
  toolCallId: string;
  result: unknown;
}
```

### Parsing Logic (Python Example)

```python
def extract_message_content(message: dict) -> str:
    """Extract text content from a message, supporting both formats."""
    
    # New format: parts array
    if "parts" in message and isinstance(message["parts"], list):
        text_parts = [
            part["text"] 
            for part in message["parts"] 
            if part.get("type") == "text" and "text" in part
        ]
        return "".join(text_parts)
    
    # Legacy format: content string
    if "content" in message:
        return message["content"]
    
    return ""


def extract_tool_calls(message: dict) -> list:
    """Extract tool calls from a message."""
    if "parts" not in message:
        return []
    
    return [
        {
            "tool_call_id": part["toolCallId"],
            "tool_name": part["toolName"],
            "args": part["args"]
        }
        for part in message["parts"]
        if part.get("type") == "tool-call"
    ]
```

### Request Body Schema

```python
from pydantic import BaseModel
from typing import Optional, List, Union, Any

class TextPart(BaseModel):
    type: str = "text"
    text: str

class ToolCallPart(BaseModel):
    type: str = "tool-call"
    toolCallId: str
    toolName: str
    args: dict

class ToolResultPart(BaseModel):
    type: str = "tool-result"
    toolCallId: str
    result: Any

class Message(BaseModel):
    role: str
    content: Optional[str] = None  # Legacy support
    parts: Optional[List[Union[TextPart, ToolCallPart, ToolResultPart]]] = None

class ChatStreamRequest(BaseModel):
    session_id: str
    messages: List[Message]
    model: Optional[str] = None
    temperature: Optional[float] = 0.7
```

---

## 3. Response Stream Protocol

### Headers

```
Content-Type: text/event-stream; charset=utf-8
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no  # Important for nginx proxy
```

### SSE Format

Each event is a single line starting with `data: ` followed by a JSON object:

```
data: {"type":"event-type",...}\n\n
```

**Important:** Each event MUST be followed by two newlines (`\n\n`).

---

## 4. Event Types Reference

### 4.1 Stream Lifecycle Events

#### `start`
Sent at the beginning of the stream.

```json
{"type": "start"}
```

#### `finish`
Sent when the stream is complete.

```json
{"type": "finish"}
```

---

### 4.2 Text Streaming Events

Text is streamed using a three-phase pattern: start → deltas → end.

#### `text-start`
Begins a new text part. The `id` must be unique within the response.

```json
{
  "type": "text-start",
  "id": "text-1"
}
```

#### `text-delta`
Sends an incremental chunk of text. Send one event per chunk.

```json
{
  "type": "text-delta",
  "id": "text-1",
  "delta": "Hello "
}
```

**Important for real streaming:** Send `text-delta` events as soon as tokens are available from the LLM. Do NOT buffer the entire response.

#### `text-end`
Completes the text part.

```json
{
  "type": "text-end",
  "id": "text-1"
}
```

---

### 4.3 Tool/Agent Events

These events enable real-time visibility into agent tool usage.

#### `tool-input-start`
Sent when the agent begins a tool call.

```json
{
  "type": "tool-input-start",
  "toolCallId": "call_abc123",
  "toolName": "query_database"
}
```

#### `tool-input-delta`
Sent as tool arguments are being generated (optional, for streaming args).

```json
{
  "type": "tool-input-delta",
  "toolCallId": "call_abc123",
  "inputTextDelta": "{\"query\": \"SELECT..."
}
```

#### `tool-input-available`
Sent when tool arguments are fully available.

```json
{
  "type": "tool-input-available",
  "toolCallId": "call_abc123",
  "toolName": "query_database",
  "input": {
    "query": "SELECT category, SUM(amount) FROM expenses GROUP BY category"
  }
}
```

#### `tool-output-available`
Sent when tool execution completes with a result.

```json
{
  "type": "tool-output-available",
  "toolCallId": "call_abc123",
  "output": {
    "rows": [
      {"category": "Marketing", "total": 15000},
      {"category": "Engineering", "total": 45000}
    ]
  }
}
```

#### `tool-output-error`
Sent when tool execution fails.

```json
{
  "type": "tool-output-error",
  "toolCallId": "call_abc123",
  "errorText": "Database connection timeout"
}
```

---

### 4.4 Error Events

#### `error`
Sent when a stream-level error occurs.

```json
{
  "type": "error",
  "errorText": "Rate limit exceeded"
}
```

---

## 5. Streaming Behavior Requirements

### 5.1 Real-Time Streaming (Critical)

The backend MUST flush/yield events immediately as they become available. Do NOT buffer the entire response.

**Bad (Buffered):**
```python
# DON'T DO THIS - buffers entire response
async def stream_response():
    full_response = await generate_complete_response()
    for chunk in split_into_chunks(full_response):
        yield f"data: {json.dumps({'type': 'text-delta', ...})}\n\n"
```

**Good (Real-Time):**
```python
# DO THIS - streams as tokens arrive
async def stream_response():
    yield f"data: {json.dumps({'type': 'start'})}\n\n"
    yield f"data: {json.dumps({'type': 'text-start', 'id': 'text-1'})}\n\n"
    
    async for token in llm.stream_tokens():
        yield f"data: {json.dumps({'type': 'text-delta', 'id': 'text-1', 'delta': token})}\n\n"
        # Flush immediately - no buffering!
    
    yield f"data: {json.dumps({'type': 'text-end', 'id': 'text-1'})}\n\n"
    yield f"data: {json.dumps({'type': 'finish'})}\n\n"
```

### 5.2 FastAPI Streaming Response

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

@app.post("/api/v1/chat/stream")
async def chat_stream(request: ChatStreamRequest):
    async def event_generator():
        # Start event
        yield f"data: {json.dumps({'type': 'start'})}\n\n"
        
        text_id = f"text-{uuid.uuid4().hex[:8]}"
        yield f"data: {json.dumps({'type': 'text-start', 'id': text_id})}\n\n"
        
        # Stream from your LLM/agent
        async for chunk in your_agent.stream(request.messages):
            if chunk.type == "text":
                yield f"data: {json.dumps({'type': 'text-delta', 'id': text_id, 'delta': chunk.text})}\n\n"
            
            elif chunk.type == "tool_start":
                yield f"data: {json.dumps({'type': 'tool-input-start', 'toolCallId': chunk.id, 'toolName': chunk.name})}\n\n"
            
            elif chunk.type == "tool_args":
                yield f"data: {json.dumps({'type': 'tool-input-available', 'toolCallId': chunk.id, 'toolName': chunk.name, 'input': chunk.args})}\n\n"
            
            elif chunk.type == "tool_result":
                yield f"data: {json.dumps({'type': 'tool-output-available', 'toolCallId': chunk.id, 'output': chunk.result})}\n\n"
        
        yield f"data: {json.dumps({'type': 'text-end', 'id': text_id})}\n\n"
        yield f"data: {json.dumps({'type': 'finish'})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
```

### 5.3 Disable Proxy Buffering

If using nginx or another reverse proxy, ensure SSE buffering is disabled:

**nginx:**
```nginx
location /api/v1/chat/stream {
    proxy_buffering off;
    proxy_cache off;
    proxy_set_header Connection '';
    proxy_http_version 1.1;
    chunked_transfer_encoding off;
}
```

---

## 6. Complete Examples

### Example 1: Simple Text Response

**Request:**
```json
{
  "session_id": "sess_123",
  "messages": [
    {
      "role": "user",
      "parts": [{"type": "text", "text": "What is 2+2?"}]
    }
  ]
}
```

**Response Stream:**
```
data: {"type":"start"}

data: {"type":"text-start","id":"text-1"}

data: {"type":"text-delta","id":"text-1","delta":"2"}

data: {"type":"text-delta","id":"text-1","delta":" + "}

data: {"type":"text-delta","id":"text-1","delta":"2"}

data: {"type":"text-delta","id":"text-1","delta":" = "}

data: {"type":"text-delta","id":"text-1","delta":"4"}

data: {"type":"text-end","id":"text-1"}

data: {"type":"finish"}
```

### Example 2: Agent with Tool Usage

**Request:**
```json
{
  "session_id": "sess_456",
  "messages": [
    {
      "role": "user",
      "parts": [{"type": "text", "text": "Which categories have the highest spending?"}]
    }
  ]
}
```

**Response Stream:**
```
data: {"type":"start"}

data: {"type":"text-start","id":"text-1"}

data: {"type":"text-delta","id":"text-1","delta":"Let me query the database for spending by category."}

data: {"type":"text-end","id":"text-1"}

data: {"type":"tool-input-start","toolCallId":"call_db1","toolName":"query_database"}

data: {"type":"tool-input-available","toolCallId":"call_db1","toolName":"query_database","input":{"query":"SELECT category, SUM(amount) as total FROM expenses GROUP BY category ORDER BY total DESC"}}

data: {"type":"tool-output-available","toolCallId":"call_db1","output":{"rows":[{"category":"Engineering","total":45000},{"category":"Marketing","total":15000}]}}

data: {"type":"text-start","id":"text-2"}

data: {"type":"text-delta","id":"text-2","delta":"Based on the data, "}

data: {"type":"text-delta","id":"text-2","delta":"Engineering has the highest spending at $45,000, "}

data: {"type":"text-delta","id":"text-2","delta":"followed by Marketing at $15,000."}

data: {"type":"text-end","id":"text-2"}

data: {"type":"finish"}
```

---

## 7. Migration Checklist

### Request Handling

- [ ] Update Pydantic models to accept `parts` array in messages
- [ ] Implement `extract_message_content()` helper to support both formats
- [ ] Implement `extract_tool_calls()` helper for tool-call parts
- [ ] Keep `content` field support for backwards compatibility

### Response Streaming

- [ ] Replace `{"type":"text","value":"..."}` with `text-start`/`text-delta`/`text-end` pattern
- [ ] Add unique `id` field to all text events
- [ ] Add `start` event at beginning of stream
- [ ] Add `finish` event at end of stream
- [ ] Replace `{"type":"finish"}` with `{"type":"finish"}`

### Tool Events

- [ ] Emit `tool-input-start` when agent decides to call a tool
- [ ] Emit `tool-input-available` when tool arguments are ready
- [ ] Emit `tool-output-available` when tool execution completes
- [ ] Emit `tool-output-error` when tool execution fails

### Streaming Performance

- [ ] Ensure LLM responses are streamed token-by-token (not buffered)
- [ ] Flush each SSE event immediately after yielding
- [ ] Disable any proxy buffering (nginx, cloudflare, etc.)
- [ ] Set appropriate SSE headers (`X-Accel-Buffering: no`)

### Testing

- [ ] Test simple text streaming (should see character-by-character updates)
- [ ] Test tool usage (should see tool status updates in UI)
- [ ] Test error handling (should see error messages in UI)
- [ ] Test with frontend to verify real-time updates

---

## Appendix: Event Type Summary

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

---

## References

- [Vercel AI SDK Stream Protocol](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol)
- [UI Message Stream Protocol](https://ai-sdk.dev/docs/ai-sdk-ui/streaming-data)
- [FastAPI Streaming Responses](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)
