"""MCP Server implementation for Procast database access."""

import asyncio
import json
from typing import Any, Optional

import structlog
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    Tool,
)

from src.core.config import settings
from src.db.connection import DatabaseManager
from src.mcp.tools import DatabaseTools, ToolResponse

logger = structlog.get_logger(__name__)


class ProcastMCPServer:
    """
    MCP Server for Procast database access.
    
    This server exposes database tools via the Model Context Protocol,
    allowing AI agents to query the Procast budget database safely.
    
    Tools provided:
    - get_db_summary: Compact database overview
    - get_schema_for_domains: Detailed schema for specific domains
    - get_table_columns: Live column info from database
    - execute_query: Run validated SQL SELECT queries
    - get_sample_data: Sample rows from a table
    """

    def __init__(self):
        """Initialize the MCP server."""
        self.server = Server("procast-db")
        self._setup_handlers()
        self._db_tools: Optional[DatabaseTools] = None

    def _setup_handlers(self) -> None:
        """Set up MCP request handlers."""
        
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            """List available database tools."""
            return [
                Tool(
                    name="get_db_summary",
                    description="Get a compact summary of the database structure. "
                                "Use this first to understand available data domains.",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    },
                ),
                Tool(
                    name="get_schema_for_domains",
                    description="Get detailed schema for specific domains. "
                                "Only request domains you need to minimize context. "
                                "Common domains: projects, budgets, accounts, actuals, users, currency.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "domains": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of domain names (e.g., ['projects', 'budgets'])",
                            },
                        },
                        "required": ["domains"],
                    },
                ),
                Tool(
                    name="get_table_columns",
                    description="Get column information for specific tables from the database.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "table_names": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of table names to get columns for",
                            },
                        },
                        "required": ["table_names"],
                    },
                ),
                Tool(
                    name="execute_query",
                    description="Execute a validated SQL SELECT query. Only SELECT statements are allowed.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "sql": {
                                "type": "string",
                                "description": "The SQL SELECT query to execute",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum results (default 1000)",
                                "default": 1000,
                            },
                        },
                        "required": ["sql"],
                    },
                ),
                Tool(
                    name="get_sample_data",
                    description="Get sample rows from a table to understand its structure.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "table_name": {
                                "type": "string",
                                "description": "Name of the table",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Number of sample rows (max 10)",
                                "default": 5,
                            },
                        },
                        "required": ["table_name"],
                    },
                ),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
            """Handle tool calls."""
            logger.info("Tool called", tool_name=name, arguments=arguments)
            
            try:
                result = await self._execute_tool(name, arguments)
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "success": result.success,
                                "data": result.data,
                                "row_count": result.row_count,
                                "error": result.error,
                                "metadata": result.metadata,
                            },
                            default=str,
                            indent=2,
                        ),
                    )
                ]
            except Exception as e:
                logger.error("Tool execution failed", tool_name=name, error=str(e))
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "success": False,
                                "error": str(e),
                            }
                        ),
                    )
                ]

    async def _execute_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResponse:
        """
        Execute a tool by name with the given arguments.
        
        Args:
            name: Tool name
            arguments: Tool arguments
            
        Returns:
            ToolResponse with results
        """
        async with DatabaseManager.get_readonly_session() as session:
            tools = DatabaseTools(session)
            
            if name == "get_db_summary":
                return await tools.get_db_summary()
            elif name == "get_schema_for_domains":
                return await tools.get_schema_for_domains(
                    domains=arguments["domains"],
                )
            elif name == "get_table_columns":
                return await tools.get_table_columns(
                    table_names=arguments["table_names"],
                )
            elif name == "execute_query":
                return await tools.execute_query(
                    sql=arguments["sql"],
                    limit=arguments.get("limit", 1000),
                )
            elif name == "get_sample_data":
                return await tools.get_sample_data(
                    table_name=arguments["table_name"],
                    limit=arguments.get("limit", 5),
                )
            else:
                return ToolResponse(
                    success=False,
                    error=f"Unknown tool: {name}",
                )

    async def run(self) -> None:
        """Run the MCP server."""
        logger.info("Starting Procast MCP Server")
        
        # Initialize database connection
        await DatabaseManager.initialize(use_readonly=True)
        
        try:
            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(
                    read_stream,
                    write_stream,
                    self.server.create_initialization_options(),
                )
        finally:
            await DatabaseManager.close()
            logger.info("Procast MCP Server stopped")


async def main() -> None:
    """Main entry point for the MCP server."""
    server = ProcastMCPServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
