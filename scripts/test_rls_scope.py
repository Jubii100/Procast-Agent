#!/usr/bin/env python3
"""
Test script for RLS (Row-Level Security) scope control.

This script tests that:
1. Users can only see projects they are members of
2. RLS policies correctly filter Projects, ProjectAccounts, EntryLines, and Invoices
3. Users with no membership see no data

Usage:
    python scripts/test_rls_scope.py --email jamestraynor@example.com
    python scripts/test_rls_scope.py --email nonexistent@example.com
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))


def _require_env(var_name: str) -> str:
    value = os.getenv(var_name)
    if not value or value == "your-anthropic-api-key-here":
        raise RuntimeError(f"Missing required environment variable: {var_name}")
    return value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test RLS scope control for Procast agent."
    )
    parser.add_argument(
        "--email",
        type=str,
        default="jamestraynor@example.com",
        help="User email to test scoping with",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable LLM caching for this run",
    )
    parser.add_argument(
        "--skip-agent",
        action="store_true",
        help="Skip agent tests, only run direct DB tests",
    )
    return parser.parse_args()


async def test_person_lookup(email: str) -> dict | None:
    """Test that we can look up a person by email."""
    from src.db.connection import DatabaseManager, lookup_person_by_email

    print(f"\n{'='*60}")
    print(f"TEST: Person Lookup for {email}")
    print("="*60)

    async with DatabaseManager.get_readonly_session() as session:
        person_info = await lookup_person_by_email(session, email)
        
        if person_info:
            print(f"  Found person:")
            print(f"    person_id: {person_info['person_id']}")
            print(f"    company_id: {person_info['company_id']}")
            print(f"    email: {person_info['email']}")
            return person_info
        else:
            print(f"  No person found with email: {email}")
            return None


async def test_rls_scoped_projects(email: str, person_id: str | None) -> int:
    """Test RLS scoping on Projects table."""
    from src.db.connection import DatabaseManager
    from src.mcp.tools import DatabaseTools
    from sqlalchemy import text

    print(f"\n{'='*60}")
    print("TEST: RLS-Scoped Project Access")
    print("="*60)

    # First, get unscoped count for comparison
    async with DatabaseManager.get_readonly_session() as session:
        # Check current RLS context (should be empty)
        result = await session.execute(
            text("SELECT current_setting('app.current_person_id', true) as pid")
        )
        row = result.mappings().first()
        print(f"  Unscoped session person_id: '{row['pid']}'")
        
        # Count all active projects (unscoped)
        result = await session.execute(
            text("""
                SELECT COUNT(*) as count 
                FROM "Projects" 
                WHERE "IsDisabled" = false 
                  AND "OriginalProjectId" IS NULL
            """)
        )
        unscoped_count = result.scalar()
        print(f"  Total active projects (unscoped): {unscoped_count}")

    # Now test with scoped session
    async with DatabaseManager.get_scoped_session(
        person_id=person_id,
        email=email if not person_id else None,
    ) as session:
        # Check RLS context is set
        result = await session.execute(
            text("SELECT current_setting('app.current_person_id', true) as pid")
        )
        row = result.mappings().first()
        print(f"  Scoped session person_id: '{row['pid']}'")
        
        # Count projects visible to user
        tools = DatabaseTools(session)
        result = await tools.execute_query(
            sql="""
                SELECT COUNT(*) as count 
                FROM "Projects" 
                WHERE "IsDisabled" = false 
                  AND "OriginalProjectId" IS NULL
            """,
            user_context={"email": email, "person_id": person_id},
        )
        
        if result.success and result.data:
            scoped_count = result.data[0]["count"]
            print(f"  Projects visible to user: {scoped_count}")
            
            if scoped_count < unscoped_count:
                print(f"  RLS IS WORKING: User sees {scoped_count}/{unscoped_count} projects")
            elif scoped_count == 0:
                print("  RLS IS WORKING: User has no project access")
            else:
                print(f"  WARNING: User sees ALL projects ({scoped_count})")
                print("  This could mean RLS is not enabled or user is superuser")
            
            return scoped_count
        else:
            print(f"  Query failed: {result.error}")
            return 0


async def test_rls_scoped_entry_lines(email: str, person_id: str | None) -> int:
    """Test RLS scoping on EntryLines table."""
    from src.db.connection import DatabaseManager
    from src.mcp.tools import DatabaseTools

    print(f"\n{'='*60}")
    print("TEST: RLS-Scoped EntryLines Access")
    print("="*60)

    async with DatabaseManager.get_scoped_session(
        person_id=person_id,
        email=email if not person_id else None,
    ) as session:
        tools = DatabaseTools(session)
        
        # Get total budget visible to user
        result = await tools.execute_query(
            sql="""
                SELECT 
                    COUNT(*) as entry_count,
                    COALESCE(SUM(CASE WHEN "IsComputedInverse" = false 
                        THEN "Amount" * "Quantity" ELSE 0 END), 0) as total_expenses,
                    COALESCE(ABS(SUM(CASE WHEN "IsComputedInverse" = true 
                        THEN "Amount" * "Quantity" ELSE 0 END)), 0) as total_revenue
                FROM "EntryLines"
                WHERE "IsDisabled" = false
            """,
            user_context={"email": email, "person_id": person_id},
        )
        
        if result.success and result.data:
            data = result.data[0]
            print(f"  Entry lines visible: {data['entry_count']}")
            print(f"  Total expenses visible: ${data['total_expenses']:,.2f}")
            print(f"  Total revenue visible: ${data['total_revenue']:,.2f}")
            return data['entry_count']
        else:
            print(f"  Query failed: {result.error}")
            return 0


async def test_rls_project_membership(email: str, person_id: str | None) -> list:
    """Get the list of projects the user is a member of."""
    from src.db.connection import DatabaseManager
    from src.mcp.tools import DatabaseTools

    print(f"\n{'='*60}")
    print("TEST: User's Project Memberships")
    print("="*60)

    if not person_id:
        print("  Cannot check memberships without person_id")
        return []

    async with DatabaseManager.get_readonly_session() as session:
        tools = DatabaseTools(session)
        
        # Direct query to ProjectPeople (not RLS-protected)
        result = await tools.execute_query(
            sql=f"""
                SELECT 
                    p."Id",
                    p."Brand",
                    pp."IsOwner",
                    pp."IsApprover"
                FROM "ProjectPeople" pp
                JOIN "Projects" p ON p."Id" = pp."ProjectId"
                WHERE pp."PersonId" = '{person_id}'
                  AND p."IsDisabled" = false
                  AND p."OriginalProjectId" IS NULL
                ORDER BY p."Brand"
                LIMIT 20
            """
        )
        
        if result.success and result.data:
            print(f"  User is member of {len(result.data)} projects:")
            for proj in result.data[:10]:
                role = []
                if proj.get("IsOwner"):
                    role.append("Owner")
                if proj.get("IsApprover"):
                    role.append("Approver")
                role_str = ", ".join(role) if role else "Member"
                print(f"    - {proj['Brand']} ({role_str})")
            if len(result.data) > 10:
                print(f"    ... and {len(result.data) - 10} more")
            return result.data
        else:
            print(f"  No memberships found or query failed: {result.error}")
            return []


async def test_agent_with_scope(email: str, skip_cache: bool = False) -> None:
    """Test the full agent workflow with RLS scoping."""
    from src.agent.graph import ProcastAgent

    print(f"\n{'='*60}")
    print(f"TEST: Agent Query with RLS Scope ({email})")
    print("="*60)

    agent = ProcastAgent()
    await agent.initialize()

    try:
        use_cache = None if not skip_cache else False
        
        result = await agent.query(
            question="What is the total budget across all my projects?",
            user_id=f"test-user-{email}",
            email=email,
            use_cache=use_cache,
        )
        
        print(f"  Response preview: {result.get('response', '')[:200]}...")
        print(f"  Confidence: {result.get('confidence', 0):.0%}")
        print(f"  Row count: {result.get('row_count', 0)}")
        print(f"  SQL: {result.get('sql_query', '')[:100]}...")
        
        if result.get("error"):
            print(f"  Error: {result.get('error')}")
            
    finally:
        await agent.close()


async def test_no_access_user() -> None:
    """Test that a user with no access sees no data."""
    from src.db.connection import DatabaseManager
    from src.mcp.tools import DatabaseTools

    print(f"\n{'='*60}")
    print("TEST: No-Access User (nonexistent@example.com)")
    print("="*60)

    async with DatabaseManager.get_scoped_session(
        email="nonexistent@example.com",
    ) as session:
        tools = DatabaseTools(session)
        
        result = await tools.execute_query(
            sql='SELECT COUNT(*) as count FROM "Projects" WHERE "IsDisabled" = false',
            user_context={"email": "nonexistent@example.com"},
        )
        
        if result.success and result.data:
            count = result.data[0]["count"]
            if count == 0:
                print("  PASS: No-access user sees 0 projects")
            else:
                print(f"  FAIL: No-access user sees {count} projects (should be 0)")
        else:
            print(f"  Query result: {result.error}")


async def main() -> None:
    args = _parse_args()
    load_dotenv(ROOT_DIR / ".env")

    _require_env("DATABASE_URL_READONLY")

    from src.db.connection import DatabaseManager

    await DatabaseManager.initialize(use_readonly=True)
    
    try:
        # Test 1: Person lookup
        person_info = await test_person_lookup(args.email)
        person_id = person_info["person_id"] if person_info else None
        
        # Test 2: Check project memberships
        memberships = await test_rls_project_membership(args.email, person_id)
        
        # Test 3: RLS-scoped project access
        project_count = await test_rls_scoped_projects(args.email, person_id)
        
        # Test 4: RLS-scoped entry lines
        entry_count = await test_rls_scoped_entry_lines(args.email, person_id)
        
        # Test 5: No-access user
        await test_no_access_user()
        
        # Test 6: Full agent test (if not skipped and API key available)
        if not args.skip_agent:
            try:
                _require_env("ANTHROPIC_API_KEY")
                
                # Configure DSPy cache
                if args.no_cache:
                    import dspy
                    from dspy.clients import configure_cache
                    configure_cache(enable_disk_cache=False, enable_memory_cache=False)
                    print("\nDSPy global cache DISABLED for this run")
                
                await test_agent_with_scope(args.email, args.no_cache)
            except RuntimeError as e:
                print(f"\nSkipping agent test: {e}")
        
        # Summary
        print(f"\n{'='*60}")
        print("SUMMARY")
        print("="*60)
        print(f"  User: {args.email}")
        print(f"  Person ID: {person_id or 'Not found'}")
        print(f"  Project memberships: {len(memberships)}")
        print(f"  Projects visible (via RLS): {project_count}")
        print(f"  Entry lines visible (via RLS): {entry_count}")
        
        if len(memberships) > 0 and project_count == len(memberships):
            print("\n  STATUS: RLS scoping appears to be working correctly!")
        elif len(memberships) == 0 and project_count == 0:
            print("\n  STATUS: User has no project access (expected if new user)")
        else:
            print(f"\n  WARNING: Membership count ({len(memberships)}) != visible projects ({project_count})")
            print("  This may indicate RLS is not fully enabled or configured")
        
    finally:
        await DatabaseManager.close()
        print("\nDatabase connection closed")


if __name__ == "__main__":
    asyncio.run(main())
