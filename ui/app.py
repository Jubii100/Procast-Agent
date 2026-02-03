"""
Chainlit UI for Procast AI Budget Analysis Agent.

This is a minimal chat UI that connects to the FastAPI backend
and streams real-time responses to the user.

Features:
- Real-time streaming responses
- Session management with sidebar list
- Message history loading on session switch

Run with:
    cd ui && chainlit run app.py --port 8080
"""

import os
import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

import httpx
import chainlit as cl
from dotenv import load_dotenv

# #region agent log
def _debug_log(location: str, message: str, data: Dict[str, Any], hypothesis_id: str) -> None:
    payload = {
        "sessionId": "debug-session",
        "runId": "pre-fix",
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(__import__("time").time() * 1000),
    }
    try:
        log_path = Path("/home/mohammed/Desktop/tech_projects/procast-ai/.cursor/debug.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(payload) + "\n")
    except Exception:
        pass
# #endregion

# Load environment variables from project root and UI directory
ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")
load_dotenv()

# #region agent log
_debug_log(
    "ui/app.py:52",
    "module_import",
    {"root_dir": str(ROOT_DIR), "api_base_url": os.getenv("PROCAST_API_URL", "unset")},
    "H0",
)
# #endregion

# Configuration
API_BASE_URL = os.getenv("PROCAST_API_URL", "http://localhost:8000")
DEFAULT_USER_EMAIL = os.getenv("PROCAST_USER_EMAIL", "")
DEFAULT_USER_ID = os.getenv("PROCAST_USER_ID", "")


async def fetch_sessions(
    user_id: str,
    user_email: str,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Fetch user's sessions from the backend."""
    # #region agent log
    _debug_log(
        "ui/app.py:39",
        "fetch_sessions start",
        {"user_id_present": bool(user_id), "email_present": bool(user_email), "api_base_url": API_BASE_URL},
        "H1",
    )
    # #endregion
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{API_BASE_URL}/api/v1/sessions",
                headers={
                    "X-User-ID": user_id,
                    "X-User-Email": user_email,
                },
                params={"limit": 20},
            )
            if response.status_code == 200:
                data = response.json()
                # #region agent log
                _debug_log(
                    "ui/app.py:52",
                    "fetch_sessions success",
                    {"session_count": len(data.get("sessions", []))},
                    "H1",
                )
                # #endregion
                return data.get("sessions", []), None
            error_text = response.text.strip()
            # #region agent log
            _debug_log(
                "ui/app.py:58",
                "fetch_sessions non-200",
                {"status_code": response.status_code, "error_text": error_text[:200]},
                "H1",
            )
            # #endregion
            return [], f"Session list failed ({response.status_code}): {error_text}"
    except Exception as e:
        # #region agent log
        _debug_log(
            "ui/app.py:63",
            "fetch_sessions exception",
            {"error": str(e)},
            "H1",
        )
        # #endregion
        return [], f"Session list error: {str(e)}"


async def fetch_session_messages(
    session_id: str,
    user_id: str,
    user_email: str,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Fetch messages for a specific session."""
    # #region agent log
    _debug_log(
        "ui/app.py:84",
        "fetch_session_messages start",
        {"session_id_present": bool(session_id), "api_base_url": API_BASE_URL},
        "H6",
    )
    # #endregion
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{API_BASE_URL}/api/v1/sessions/{session_id}",
                headers={
                    "X-User-ID": user_id,
                    "X-User-Email": user_email,
                },
            )
            if response.status_code == 200:
                data = response.json()
                # #region agent log
                _debug_log(
                    "ui/app.py:97",
                    "fetch_session_messages success",
                    {"message_count": len(data.get("messages", []))},
                    "H6",
                )
                # #endregion
                return data.get("messages", []), None
            error_text = response.text.strip()
            # #region agent log
            _debug_log(
                "ui/app.py:103",
                "fetch_session_messages non-200",
                {"status_code": response.status_code, "error_text": error_text[:200]},
                "H6",
            )
            # #endregion
            return [], f"Session history failed ({response.status_code}): {error_text}"
    except Exception as e:
        # #region agent log
        _debug_log(
            "ui/app.py:108",
            "fetch_session_messages exception",
            {"error": str(e)},
            "H6",
        )
        # #endregion
        return [], f"Session history error: {str(e)}"


async def create_new_session(
    user_id: str,
    user_email: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Create a new session and return its ID."""
    # #region agent log
    _debug_log(
        "ui/app.py:89",
        "create_new_session start",
        {"user_id_present": bool(user_id), "email_present": bool(user_email), "api_base_url": API_BASE_URL},
        "H2",
    )
    # #endregion
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{API_BASE_URL}/api/v1/sessions",
                headers={
                    "X-User-ID": user_id,
                    "X-User-Email": user_email,
                },
            )
            if response.status_code == 200:
                data = response.json()
                # #region agent log
                _debug_log(
                    "ui/app.py:105",
                    "create_new_session success",
                    {"session_id_present": bool(data.get("id"))},
                    "H2",
                )
                # #endregion
                return data.get("id"), None
            error_text = response.text.strip()
            # #region agent log
            _debug_log(
                "ui/app.py:111",
                "create_new_session non-200",
                {"status_code": response.status_code, "error_text": error_text[:200]},
                "H2",
            )
            # #endregion
            return None, f"Session create failed ({response.status_code}): {error_text}"
    except Exception as e:
        # #region agent log
        _debug_log(
            "ui/app.py:116",
            "create_new_session exception",
            {"error": str(e)},
            "H2",
        )
        # #endregion
        return None, f"Session create error: {str(e)}"


NEW_SESSION_LABEL = "New session"


async def send_session_actions(sessions: List[Dict[str, Any]]) -> None:
    """Send session controls as action buttons in the chat."""
    actions = [
        cl.Action(
            name="new_session",
            payload={"action": "new_session"},
            label="New Session",
            tooltip="Start a new conversation session",
        )
    ]
    for session in sessions[:5]:
        session_id = session.get("id", "")
        title = session.get("title") or f"Session {session_id[:8]}..."
        msg_count = session.get("message_count", 0)
        label = f"{title[:30]} ({msg_count} msgs)"
        actions.append(
            cl.Action(
                name="switch_session",
                payload={"session_id": session_id},
                label=label,
                tooltip=f"Switch to session {session_id}",
            )
        )
    await cl.Message(
        content="**Session controls:**",
        actions=actions,
    ).send()


async def render_sidebar_sessions(selected_session_id: Optional[str] = None) -> Optional[str]:
    """Fetch sessions and keep cached; no sidebar rendering."""
    # #region agent log
    _debug_log(
        "ui/app.py:136",
        "render_sidebar_sessions start",
        {"selected_session_id_present": bool(selected_session_id)},
        "H3",
    )
    # #endregion
    user_id = cl.user_session.get("user_id") or DEFAULT_USER_ID
    user_email = cl.user_session.get("user_email") or DEFAULT_USER_EMAIL
    
    sessions, error = await fetch_sessions(user_id, user_email)
    cl.user_session.set("cached_sessions", sessions)
    cl.user_session.set("session_label_map", {})
    # #region agent log
    _debug_log(
        "ui/app.py:171",
        "render_sidebar_sessions sent",
        {"error_present": bool(error), "session_count": len(sessions)},
        "H3",
    )
    # #endregion
    return error


@cl.on_chat_start
async def on_chat_start():
    """Initialize a new chat session."""
    # #region agent log
    _debug_log(
        "ui/app.py:178",
        "on_chat_start enter",
        {"api_base_url": API_BASE_URL},
        "H4",
    )
    # #endregion
    try:
        user_email = DEFAULT_USER_EMAIL
        user_id = DEFAULT_USER_ID
        
        # Store user info first
        cl.user_session.set("user_id", user_id)
        cl.user_session.set("user_email", user_email)
        
        # Fetch existing sessions to show in sidebar
        sessions, sessions_error = await fetch_sessions(user_id, user_email)
        cl.user_session.set("cached_sessions", sessions)
        
        # Check if we have existing sessions
        if sessions:
            # Use the most recent session
            most_recent = sessions[0]
            session_id = most_recent.get("id")
            session_title = most_recent.get("title") or "Recent Session"
            
            cl.user_session.set("session_id", session_id)
            
            # Render sidebar sessions
            sidebar_error = await render_sidebar_sessions(selected_session_id=session_id)
            # #region agent log
            _debug_log(
                "ui/app.py:207",
                "on_chat_start existing sessions path",
                {"sessions_count": len(sessions), "sidebar_error_present": bool(sidebar_error)},
                "H4",
            )
            # #endregion
            if sessions_error or sidebar_error:
                await cl.Message(
                    content=f"**Session service warning:** {sessions_error or sidebar_error}\n\nBackend URL: `{API_BASE_URL}`",
                ).send()
            
            # Welcome message with session options
            await cl.Message(
                content=f"""**Welcome back to Procast AI Budget Analyst!**

I found {len(sessions)} previous session(s). You're now in: **{session_title}**

Use the buttons below to switch sessions or start a new one.

---
Ask me questions like:
- "What is the total budget across all projects?"
- "Show me the top spending categories"
- "Which projects are at risk of overspending?"

*Current Session: `{session_id[:8]}...`*
""",
            ).send()
            
            # Load and display message history for the current session
            await load_session_history(session_id, user_id, user_email)
            await send_session_actions(sessions)
        else:
            # No existing sessions, create a new one
            session_id, create_error = await create_new_session(user_id, user_email)
            # #region agent log
            _debug_log(
                "ui/app.py:228",
                "on_chat_start create session path",
                {"session_id_present": bool(session_id), "create_error_present": bool(create_error)},
                "H4",
            )
            # #endregion
            
            if not session_id:
                # Backend unreachable or session service unavailable; allow chat to continue
                cl.user_session.set("session_id", None)
                sidebar_error = await render_sidebar_sessions(selected_session_id=None)
                await cl.Message(
                    content=f"**Session service warning:** {create_error or sidebar_error or 'Unavailable'}\n\nBackend URL: `{API_BASE_URL}`",
                ).send()
            else:
                cl.user_session.set("session_id", session_id)
                await render_sidebar_sessions(selected_session_id=session_id)
            
            # Welcome message for new users
            session_label = f"*Session ID: `{session_id}`*" if session_id else "*Session ID: unavailable*"
            await cl.Message(
                content=f"""**Welcome to Procast AI Budget Analyst!**

I can help you analyze your budget data. Ask me questions like:
- "What is the total budget across all projects?"
- "Show me the top spending categories"
- "Which projects are at risk of overspending?"

{session_label}
*User: `{user_email}`*
""",
            ).send()
            await send_session_actions(sessions)

        # #region agent log
        _debug_log(
            "ui/app.py:243",
            "on_chat_start exit",
            {"sessions_count": len(sessions), "has_sessions": bool(sessions)},
            "H4",
        )
        # #endregion
    except Exception as e:
        # #region agent log
        _debug_log(
            "ui/app.py:249",
            "on_chat_start exception",
            {"error": str(e)},
            "H7",
        )
        # #endregion
        raise


async def load_session_history(session_id: str, user_id: str, user_email: str):
    """Load and display message history for a session."""
    # #region agent log
    _debug_log(
        "ui/app.py:257",
        "load_session_history start",
        {"session_id_present": bool(session_id)},
        "H5",
    )
    # #endregion
    try:
        messages, error = await fetch_session_messages(session_id, user_id, user_email)

        # #region agent log
        _debug_log(
            "ui/app.py:262",
            "load_session_history fetched",
            {"error_present": bool(error), "message_count": len(messages)},
            "H5",
        )
        # #endregion
        
        if error:
            # #region agent log
            _debug_log(
                "ui/app.py:264",
                "load_session_history error",
                {"error": error[:200]},
                "H5",
            )
            # #endregion
            await cl.Message(
                content=f"**Session history warning:** {error}",
            ).send()
            return
        
        if not messages:
            # #region agent log
            _debug_log(
                "ui/app.py:273",
                "load_session_history empty",
                {"message_count": 0},
                "H5",
            )
            # #endregion
            return
        
        # Display history separator
        await cl.Message(
            content="---\n**Previous messages in this session:**\n---",
        ).send()
        
        # Render each message from history
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "user":
                # Show user messages
                await cl.Message(
                    content=content,
                    author="You",
                ).send()
            elif role == "assistant":
                # Show assistant messages
                await cl.Message(
                    content=content,
                    author="Procast AI",
                ).send()

        # #region agent log
        _debug_log(
            "ui/app.py:304",
            "load_session_history rendered",
            {"message_count": len(messages)},
            "H5",
        )
        # #endregion
        
        # End of history separator
        await cl.Message(
            content="---\n**End of history. Continue the conversation below.**\n---",
        ).send()
    except Exception as e:
        # #region agent log
        _debug_log(
            "ui/app.py:314",
            "load_session_history exception",
            {"error": str(e)},
            "H7",
        )
        # #endregion
        raise


@cl.action_callback("new_session")
async def on_new_session(action: cl.Action):
    """Handle new session creation from action button."""
    user_id = cl.user_session.get("user_id") or DEFAULT_USER_ID
    user_email = cl.user_session.get("user_email") or DEFAULT_USER_EMAIL
    
    session_id, create_error = await create_new_session(user_id, user_email)
    if not session_id:
        await cl.Message(
            content=f"**Session create error:** {create_error or 'Unknown error'}",
        ).send()
        return
    
    cl.user_session.set("session_id", session_id)
    await render_sidebar_sessions(selected_session_id=session_id)
    await send_session_actions(cl.user_session.get("cached_sessions") or [])
    
    await cl.Message(
        content=f"**New session created!**\n\nSession ID: `{session_id[:8]}...`\n\nYou can now start a fresh conversation.",
    ).send()


@cl.action_callback("switch_session")
async def on_switch_session(action: cl.Action):
    """Handle session switching from action button."""
    payload = action.payload or {}
    session_id = payload.get("session_id")
    if not session_id:
        await cl.Message(content="**Session switch error:** Missing session id.").send()
        return
    
    user_id = cl.user_session.get("user_id") or DEFAULT_USER_ID
    user_email = cl.user_session.get("user_email") or DEFAULT_USER_EMAIL
    
    cl.user_session.set("session_id", session_id)
    await render_sidebar_sessions(selected_session_id=session_id)
    await send_session_actions(cl.user_session.get("cached_sessions") or [])
    
    await cl.Message(
        content=f"**Switched to session:** `{session_id[:8]}...`\n\nLoading conversation history...",
    ).send()
    
    await load_session_history(session_id, user_id, user_email)


@cl.on_message
async def on_message(message: cl.Message):
    """Handle incoming user messages with real-time streaming."""
    session_id = cl.user_session.get("session_id")
    user_id = cl.user_session.get("user_id") or DEFAULT_USER_ID
    user_email = cl.user_session.get("user_email") or DEFAULT_USER_EMAIL
    # Create a step to show processing status (shown above the response)
    async with cl.Step(name="Analysis", type="run") as step:
        step.output = "Preparing analysis..."
        await step.update()
        
        # Create a message placeholder for streaming
        msg = cl.Message(content="")
        await msg.send()
    
    try:
        event_type = None
        sql_query = None
        row_count = 0
        
        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream(
                "POST",
                f"{API_BASE_URL}/api/v1/analyze/stream",
                json={
                    "query": message.content,
                    "session_id": session_id,
                },
                headers={
                    "X-User-ID": user_id,
                    "X-User-Email": user_email,
                    "Accept": "text/event-stream",
                },
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    await msg.stream_token(f"**Error:** {error_text.decode()}")
                    await msg.update()
                    return
                
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    
                    # Parse SSE format
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        try:
                            data = json.loads(line[5:].strip())
                        except json.JSONDecodeError:
                            continue
                        
                        if event_type == "session":
                            # Update session ID if provided
                            if data.get("session_id"):
                                cl.user_session.set("session_id", data["session_id"])
                        
                        elif event_type == "status":
                            # Update step with status
                            status_msg = data.get("message", "Processing...")
                            step.output = status_msg
                            await step.update()
                        
                        elif event_type == "sql":
                            # Store SQL query for display
                            sql_query = data.get("sql")
                        
                        elif event_type == "token":
                            # Stream real-time tokens to the UI
                            token = data.get("token", "")
                            if token:
                                await msg.stream_token(token)
                        
                        elif event_type == "complete":
                            # Handle completion
                            row_count = data.get("row_count", 0)
                            step.output = f"Analysis complete: {row_count} rows analyzed"
                            await step.update()
                        
                        elif event_type == "error":
                            error_msg = data.get("error", "Unknown error")
                            await msg.stream_token(f"\n\n**Error:** {error_msg}")
        
        # Add SQL query as a collapsible element if available
        if sql_query:
            elements = [
                cl.Text(
                    name="SQL Query",
                    content=f"```sql\n{sql_query}\n```",
                    display="side",
                )
            ]
            msg.elements = elements
    
    except httpx.TimeoutException:
        await msg.stream_token("\n\n**Timeout:** Request took too long. Please try again.")
    except httpx.ConnectError:
        await msg.stream_token(f"\n\n**Connection Error:** Could not connect to backend at {API_BASE_URL}")
    except Exception as e:
        await msg.stream_token(f"\n\n**Error:** {str(e)}")
    
    # Finalize the message
    await msg.update()


@cl.on_chat_end
async def on_chat_end():
    """Handle chat session end."""
    session_id = cl.user_session.get("session_id")
    if session_id:
        # Could log session end here if needed
        pass


# Auth disabled for email-only testing.
