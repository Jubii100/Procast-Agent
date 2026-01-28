"""Schema introspection endpoints."""

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.middleware.auth import get_current_user, UserContext
from src.api.schemas import SchemaResponse, SchemaInfo, ErrorResponse
from src.db.connection import DatabaseManager
from src.db.schema_registry import (
    get_db_summary,
    get_all_domains,
    get_domain_schema,
    build_schema_context,
)
from src.mcp.tools import DatabaseTools

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Schema"])


@router.get(
    "/schema/summary",
    response_model=dict,
    summary="Get database summary",
    description="Get a compact summary of the database structure for understanding available data domains.",
)
async def get_schema_summary(
    user: UserContext = Depends(get_current_user),
) -> dict:
    """
    Get a compact database summary.
    
    Returns a token-efficient overview of the database structure
    suitable for understanding what data is available.
    """
    logger.info("Schema summary request", user_id=user.user_id)
    
    return {
        "summary": get_db_summary(),
        "available_domains": get_all_domains(),
    }


@router.get(
    "/schema/domains",
    response_model=list[str],
    summary="List all domains",
    description="Get a list of all data domain names.",
)
async def list_domains(
    user: UserContext = Depends(get_current_user),
) -> list[str]:
    """Get a list of all domain names."""
    return get_all_domains()


@router.get(
    "/schema/domains/{domain_name}",
    response_model=dict,
    responses={
        404: {"model": ErrorResponse, "description": "Domain not found"},
    },
    summary="Get domain schema",
    description="Get detailed schema information for a specific domain.",
)
async def get_domain_schema_endpoint(
    domain_name: str,
    user: UserContext = Depends(get_current_user),
) -> dict:
    """Get schema for a specific domain."""
    schema = get_domain_schema(domain_name.lower())
    
    if not schema:
        raise HTTPException(
            status_code=404,
            detail=f"Domain '{domain_name}' not found. Available domains: {get_all_domains()}",
        )
    
    return {
        "domain": domain_name,
        "schema": schema,
    }


@router.post(
    "/schema/context",
    response_model=dict,
    summary="Build schema context",
    description="Build a schema context for specific domains. Useful for understanding token costs.",
)
async def build_context(
    domains: list[str],
    user: UserContext = Depends(get_current_user),
) -> dict:
    """Build schema context for specified domains."""
    # Validate domains
    valid_domains = get_all_domains()
    invalid = [d for d in domains if d.lower() not in valid_domains]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid domains: {invalid}. Available: {valid_domains}",
        )
    
    context = build_schema_context([d.lower() for d in domains])
    
    return {
        "selected_domains": context.selected_domains,
        "token_estimate": context.token_estimate,
        "context": context.full_context,
    }


@router.get(
    "/schema",
    response_model=SchemaResponse,
    responses={
        500: {"model": ErrorResponse, "description": "Database error"},
    },
    summary="Get database schema",
    description="Retrieve the database schema from the live database including tables and columns.",
)
async def get_schema(
    user: UserContext = Depends(get_current_user),
    tables: Optional[str] = Query(
        default=None,
        description="Comma-separated list of table names to filter (optional)",
    ),
) -> SchemaResponse:
    """
    Get database schema information from the live database.
    
    Returns a list of tables and their columns with data types.
    """
    logger.info("Schema request received", user_id=user.user_id)
    
    try:
        await DatabaseManager.initialize(use_readonly=True)
        
        async with DatabaseManager.get_readonly_session() as session:
            tools = DatabaseTools(session)
            
            # Get table stats first
            stats_result = await tools.get_live_table_stats()
            
            if not stats_result.success:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to get schema: {stats_result.error}",
                )
            
            all_tables = [row.get("table_name", "") for row in stats_result.data or []]
            
            # Filter tables if specified
            if tables:
                requested_tables = [t.strip() for t in tables.split(",")]
                all_tables = [t for t in all_tables if t in requested_tables]
            
            # Get column info for tables
            schema_info = []
            if all_tables:
                columns_result = await tools.get_table_columns(all_tables[:50])  # Limit to 50 tables
                
                if columns_result.success:
                    for row in columns_result.data or []:
                        schema_info.append(
                            SchemaInfo(
                                table_name=row.get("table_name", ""),
                                column_name=row.get("column_name", ""),
                                data_type=row.get("data_type", ""),
                                is_nullable=row.get("is_nullable", "YES"),
                                constraint_type=row.get("constraint_type"),
                            )
                        )
            
            logger.info(
                "Schema request completed",
                user_id=user.user_id,
                table_count=len(all_tables),
            )
            
            return SchemaResponse(
                tables=sorted(all_tables),
                schema_info=schema_info,
                total_tables=len(all_tables),
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Schema request failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve schema: {str(e)}",
        )


@router.get(
    "/schema/tables",
    response_model=list[str],
    summary="List all tables",
    description="Get a simple list of all table names from the live database.",
)
async def list_tables(
    user: UserContext = Depends(get_current_user),
) -> list[str]:
    """Get a list of all table names."""
    schema_response = await get_schema(user=user)
    return schema_response.tables


@router.get(
    "/schema/tables/{table_name}",
    response_model=list[SchemaInfo],
    responses={
        404: {"model": ErrorResponse, "description": "Table not found"},
    },
    summary="Get table schema",
    description="Get column information for a specific table.",
)
async def get_table_schema(
    table_name: str,
    user: UserContext = Depends(get_current_user),
) -> list[SchemaInfo]:
    """Get schema for a specific table."""
    try:
        await DatabaseManager.initialize(use_readonly=True)
        
        async with DatabaseManager.get_readonly_session() as session:
            tools = DatabaseTools(session)
            result = await tools.get_table_columns([table_name])
            
            if not result.success or not result.data:
                raise HTTPException(
                    status_code=404,
                    detail=f"Table '{table_name}' not found",
                )
            
            return [
                SchemaInfo(
                    table_name=row.get("table_name", ""),
                    column_name=row.get("column_name", ""),
                    data_type=row.get("data_type", ""),
                    is_nullable=row.get("is_nullable", "YES"),
                    constraint_type=row.get("constraint_type"),
                )
                for row in result.data
            ]
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Table schema request failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve table schema: {str(e)}",
        )


@router.get(
    "/schema/tables/{table_name}/sample",
    response_model=dict,
    responses={
        404: {"model": ErrorResponse, "description": "Table not found"},
    },
    summary="Get sample data",
    description="Get sample rows from a specific table to understand data structure.",
)
async def get_table_sample(
    table_name: str,
    user: UserContext = Depends(get_current_user),
    limit: int = Query(default=5, ge=1, le=10, description="Number of sample rows"),
) -> dict:
    """Get sample data from a table."""
    try:
        await DatabaseManager.initialize(use_readonly=True)
        
        async with DatabaseManager.get_readonly_session() as session:
            tools = DatabaseTools(session)
            result = await tools.get_sample_data(table_name, limit=limit)
            
            if not result.success:
                raise HTTPException(
                    status_code=404,
                    detail=f"Table '{table_name}' not found or error: {result.error}",
                )
            
            return {
                "table": table_name,
                "sample_count": result.row_count,
                "data": result.data,
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Sample data request failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve sample data: {str(e)}",
        )
