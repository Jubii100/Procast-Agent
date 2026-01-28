"""
Schema Registry - Domain-split table descriptions for cost-efficient context loading.

This module provides compact, token-efficient table descriptions organized by domain.
The agent first receives a lightweight summary, then selects relevant domains,
and only loads detailed schemas for those specific tables.
"""

from dataclasses import dataclass
from typing import Optional

# =============================================================================
# COMPACT DATABASE SUMMARY (~300 tokens)
# Used as initial context for table selection - minimal token cost
# =============================================================================

DATABASE_SUMMARY = """
PROCAST DATABASE - Event Budget Management System

DOMAINS:
1. PROJECTS: Projects, SubProjects, ProjectAccounts, ProjectPeople, Portfolios
2. BUDGETS: EntryLines (budget items), SubAccounts, EntryLine_H (history)
3. ACCOUNTS: Accounts, AccountCategories, LegalEntityAccounts
4. ACTUALS: Invoices, PurchaseOrders, Reconciliations
5. USERS: People, AspNetUsers, Companies
6. CURRENCY: Currencies, CurrencyTuples, ConstantFxRates, FinancialYears
7. REFERENCE: Countries, Regions, Industries, Divisions, CostCodes

KEY FACTS:
- Budget total = EntryLines.Amount × EntryLines.Quantity
- Status >= 2 means committed spending
- IsDisabled = true means soft-deleted (always filter)
- Projects.OriginalProjectId links scenario copies
- All monetary amounts need currency conversion via ConstantFxRates
"""

# =============================================================================
# DOMAIN DEFINITIONS
# Maps domain names to their tables for targeted loading
# =============================================================================

DOMAIN_TABLES = {
    "projects": ["Projects", "SubProjects", "ProjectAccounts", "ProjectPeople", 
                 "ProjectPortfolios", "Portfolios", "ProjectDivisions", "ProjectIndustries"],
    "budgets": ["EntryLines", "EntryLine_H", "SubAccounts", "EntryLineSubProject", "EntryStatuses"],
    "accounts": ["Accounts", "AccountCategories", "LegalEntityAccounts", "LegalEntities"],
    "actuals": ["Invoices", "PurchaseOrders", "Reconciliations"],
    "users": ["People", "AspNetUsers", "AspNetRoles", "AspNetUserRoles", "Companies"],
    "currency": ["Currencies", "CurrencyTuples", "ConstantFxRates", "FinancialYears"],
    "reference": ["Countries", "Regions", "Industries", "Divisions", "CostCodes", "Folders"],
    "workspaces": ["PersonalWorkspaces", "SharedWorkspaces", "Folders"],
    "approvals": ["Approvals", "ReviewRequests", "ReviewRequestPeople"],
}

# =============================================================================
# DETAILED TABLE SCHEMAS BY DOMAIN
# Only loaded when specifically needed - keeps per-query token cost low
# =============================================================================

DOMAIN_SCHEMAS = {
    "projects": """
## PROJECTS DOMAIN

### Projects (Main budget container - events)
- Id: uuid PK
- Brand: varchar(256) - Project/event name
- Edition: bigint - Edition number
- TakePlaceDate: date - Event date
- Type: integer - Project type
- OperatingCurrencyId: uuid FK → Currencies
- CountryId: uuid FK → Countries
- CostCodeId: uuid FK → CostCodes
- FolderId: uuid FK → Folders
- SharedWorkspaceId: uuid FK → SharedWorkspaces
- OriginalProjectId: uuid FK → Projects (for scenario clones)
- ScenarioName: varchar(1024)
- ScenarioPredefinedNameId: uuid FK
- IsLocked: boolean
- ApprovalId: uuid FK → Approvals
- IsDisabled: boolean (soft delete)
- Created, CreatedBy, LastModified, LastModifiedBy (audit)

### SubProjects (Sub-events within a project)
- Id: uuid PK
- Name: varchar(256)
- ProjectId: uuid FK → Projects
- CostCodeId: uuid FK → CostCodes

### ProjectAccounts (Links projects to accounts)
- Id: uuid PK
- ProjectId: uuid FK → Projects
- LegalEntityAccountId: uuid FK → LegalEntityAccounts
- IsDisabled: boolean

### ProjectPeople (Team membership)
- Id: uuid PK
- PersonId: uuid FK → People
- ProjectId: uuid FK → Projects
- IsApprover: boolean
- IsOwner: boolean
- PersonalWorkspaceId: uuid FK

### Portfolios (Groups of projects)
- Id: uuid PK
- Name: varchar(1024)

### ProjectPortfolios (Many-to-many)
- ProjectId: uuid FK → Projects
- PortfolioId: uuid FK → Portfolios
""",

    "budgets": """
## BUDGETS DOMAIN

### EntryLines (Core budget line items) ⭐ CRITICAL
- Id: uuid PK
- Description: varchar(2048)
- Quantity: double precision - Number of units
- Amount: double precision - Unit price
- Status: integer (0=Draft, 1=Pending, 2+=Committed)
- OwnerId: uuid FK → People
- ProjectAccountId: uuid FK → ProjectAccounts
- LocalCurrencyId: uuid FK → Currencies
- SubAccountId: uuid FK → SubAccounts (optional)
- EntryStatusId: uuid FK → EntryStatuses
- PurchaseOrderCode: varchar(1024)
- InvoiceRefCode: varchar(256)
- SupplierName: varchar(256)
- ReconciliationId: uuid FK → Reconciliations
- IsComputedInverse: boolean (revenue flag)
- IsDisabled: boolean

CALCULATION: Total = Amount × Quantity
FILTER: Always use IsDisabled = false

### EntryLine_H (Audit history of budget changes) ⭐ TREND ANALYSIS
- Id: uuid PK
- Action: text ("Line Added", "Line Deleted", "Changes in Line")
- TableName: text
- OldData: text (JSON)
- NewData: text (JSON)
- ProjectAccountId: uuid FK → ProjectAccounts
- LatestViewTotalCurrent: double - Running total after
- LatestViewTotalPrevious: double - Running total before
- Created: timestamptz
- CreatorId, LastModifierId: uuid FK → People

### SubAccounts (Sub-budget allocations)
- Id: uuid PK
- Name: text
- Amount: double - Budgeted amount
- AccountId: uuid FK → Accounts
- ProjectId: uuid FK → Projects
- ProjectAccountId: uuid FK → ProjectAccounts
- CurrencyId: uuid FK → Currencies

### EntryLineSubProject (Tags entries to sub-projects)
- EntryLinesId: uuid FK → EntryLines
- SubProjectsId: uuid FK → SubProjects

### EntryStatuses
- Id: uuid PK
- Name: varchar(256)
""",

    "accounts": """
## ACCOUNTS DOMAIN

### AccountCategories (Hierarchical expense categories) ⭐
- Id: uuid PK
- Name: varchar(2048)
- ParentCategoryId: uuid FK → AccountCategories (self-reference for hierarchy)
- CategoryPosition: integer (display order)
- IsDisabled: boolean

### Accounts (Chart of accounts)
- Id: uuid PK
- Number: bigint - Account number (e.g., 5000, 6000)
- Description: varchar(2048)
- SubAccountCategoryId: uuid FK → AccountCategories
- IsDisabled: boolean

### LegalEntityAccounts (Accounts available to each legal entity)
- Id: uuid PK
- LegalEntityId: uuid FK → LegalEntities
- AccountId: uuid FK → Accounts

### LegalEntities (Legal entity/subsidiary)
- Id: uuid PK
- Name: varchar(1024)
- NickName: text
- CountryId: uuid FK → Countries
- EntityCurrencyId: uuid FK → Currencies
""",

    "actuals": """
## ACTUALS DOMAIN (Realized spending)

### Invoices ⭐ ACTUAL SPENDING
- Id: uuid PK
- TransactionId: text - External reference
- TransactionType: text
- DateApplied: timestamptz - Invoice date
- HeaderDescription: text
- LineDescription: text
- EntityCurrencyId: uuid FK → Currencies
- EntityCurrencyTotal: numeric
- LocalCurrencyId: uuid FK → Currencies
- LocalCurrencyTotal: numeric
- PostedFlag: boolean - Is invoice posted
- PostedDate: timestamptz
- PostedBy: text
- CostCodeId: uuid FK → CostCodes
- AccountId: uuid FK → Accounts
- InvoiceRefCode: text
- PurchaseOrderCode: text
- ReconciliationId: uuid FK → Reconciliations
- LegalEntityName: text
- IsNetOffed: boolean
- IsDisabled: boolean

### PurchaseOrders ⭐ COMMITTED SPENDING
- Id: uuid PK
- TransactionId: text
- PurchaseOrderCode: text
- PurchaseOrderStatus: integer (0=Draft, 1=Approved, etc.)
- EntityCurrencyTotal: numeric
- LocalCurrencyTotal: numeric
- DateApplied: timestamptz
- PostedFlag: boolean
- CostCodeId: uuid FK → CostCodes
- AccountId: uuid FK → Accounts
- LegalEntityName: text
- EntityCurrencyId, LocalCurrencyId: uuid FK → Currencies

### Reconciliations
- Id: uuid PK
- Created: timestamptz
""",

    "users": """
## USERS DOMAIN

### People (Central user entity) ⭐
- Id: uuid PK
- Email: varchar(256) UNIQUE
- FirstName: varchar(512)
- LastName: text
- AvatarUrl: varchar(4096)
- CompanyId: uuid FK → Companies
- IsArchived: boolean
- IsDisabled: boolean

### AspNetUsers (Identity)
- Id: text PK
- PersonId: uuid FK → People
- UserName: varchar(256)
- Email: varchar(256)
- PasswordHash: text
- FirstLogin: boolean
- TwoFactorEnabled: boolean

### Companies (Organizations)
- Id: uuid PK
- Name: varchar(1024)
- Address: varchar(1024)
- PhoneNumber: varchar(128)
- Email: varchar(256)
- LogoUrl: varchar(4096)
- ReportingCurrencyId: uuid FK → Currencies
- IsInverseRevenue: boolean
""",

    "currency": """
## CURRENCY DOMAIN

### Currencies
- Id: uuid PK
- IsoCode: varchar(3) - ISO 4217 (USD, EUR, GBP)

### CurrencyTuples (Conversion pairs)
- Id: uuid PK
- FromCurrencyId: uuid FK → Currencies
- ToCurrencyId: uuid FK → Currencies

### ConstantFxRates ⭐ CURRENCY CONVERSION
- Id: uuid PK
- MonthOrder: integer (1-12)
- Value: double - Exchange rate
- FinancialYearId: uuid FK → FinancialYears
- CurrencyTupleId: uuid FK → CurrencyTuples

USAGE: Convert via CurrencyTuples → ConstantFxRates

### FinancialYears
- Id: uuid PK
- Year: integer (2024, 2025)
- StartDate: date
- EndDate: date
""",

    "reference": """
## REFERENCE DOMAIN

### Countries
- Id: uuid PK
- IsoCode: varchar(3) - ISO 3166
- Name: varchar(256)

### Regions
- Id: uuid PK
- Name: varchar(256)

### Industries
- Id: uuid PK
- Name: varchar(256)

### Divisions
- Id: uuid PK
- Name: varchar(256)

### CostCodes
- Id: uuid PK
- Code: varchar(128)
- Description: varchar(1024)

### Folders
- Id: uuid PK
- Name: varchar(256)
- PersonalWorkspaceId: uuid FK
- SharedWorkspaceId: uuid FK
""",

    "workspaces": """
## WORKSPACES DOMAIN

### PersonalWorkspaces
- Id: uuid PK
- Name: varchar(256)

### SharedWorkspaces
- Id: uuid PK
- Name: varchar(256)

### Folders
- Id: uuid PK
- Name: varchar(256)
- PersonalWorkspaceId: uuid FK → PersonalWorkspaces
- SharedWorkspaceId: uuid FK → SharedWorkspaces
""",

    "approvals": """
## APPROVALS DOMAIN

### Approvals
- Id: uuid PK
- Status: integer
- Description: varchar(4096)
- PersonId: uuid FK → People

### ReviewRequests
- Id: uuid PK
- PersonId: uuid FK → People (requester)
- TargetedDbEntityId: uuid
- TargetedDbEntityTypeId: uuid FK

### ReviewRequestPeople
- Id: uuid PK
- ReviewRequestId: uuid FK → ReviewRequests
- PersonId: uuid FK → People
""",
}

# =============================================================================
# KEY RELATIONSHIPS (Compact reference for JOINs)
# =============================================================================

KEY_RELATIONSHIPS = """
## KEY JOIN PATHS

### Budget Flow (most common):
Projects → ProjectAccounts → EntryLines
Projects → ProjectAccounts → LegalEntityAccounts → Accounts → AccountCategories

### Actual Spending:
Invoices.AccountId → Accounts
PurchaseOrders.AccountId → Accounts

### Currency Conversion:
EntryLines.LocalCurrencyId → Currencies
Currencies → CurrencyTuples → ConstantFxRates ← FinancialYears

### User Context:
People → ProjectPeople → Projects
People → AspNetUsers
People → Companies

### History:
EntryLines triggers → EntryLine_H (automatic audit)
"""

# =============================================================================
# COMMON QUERY PATTERNS (Examples for the LLM)
# =============================================================================

QUERY_PATTERNS = """
## COMMON SQL PATTERNS

### Budget Total:
SELECT SUM(el."Amount" * el."Quantity") FROM "EntryLines" el WHERE el."IsDisabled" = false

### Committed vs Budgeted:
SUM(CASE WHEN el."Status" >= 2 THEN el."Amount" * el."Quantity" ELSE 0 END) as committed

### Join to Categories:
JOIN "LegalEntityAccounts" lea ON lea."Id" = pa."LegalEntityAccountId"
JOIN "Accounts" a ON a."Id" = lea."AccountId"
JOIN "AccountCategories" ac ON ac."Id" = a."SubAccountCategoryId"

### Exclude Scenarios:
WHERE p."OriginalProjectId" IS NULL

### Always Filter:
WHERE [table]."IsDisabled" = false
"""


@dataclass
class SchemaContext:
    """Container for schema context to pass to SQL generation."""
    db_summary: str
    selected_domains: list[str]
    table_schemas: str
    relationships: str
    query_patterns: str
    
    @property
    def full_context(self) -> str:
        """Get full context string for SQL generation."""
        return f"""{self.db_summary}

{self.table_schemas}

{self.relationships}

{self.query_patterns}"""
    
    @property
    def token_estimate(self) -> int:
        """Rough estimate of tokens in the context."""
        # Approximate: 1 token ≈ 4 characters
        return len(self.full_context) // 4


def get_db_summary() -> str:
    """Get the compact database summary for initial context."""
    return DATABASE_SUMMARY


def get_domain_tables(domain: str) -> list[str]:
    """Get list of tables in a domain."""
    return DOMAIN_TABLES.get(domain.lower(), [])


def get_all_domains() -> list[str]:
    """Get list of all domain names."""
    return list(DOMAIN_TABLES.keys())


def get_domain_schema(domain: str) -> str:
    """Get detailed schema for a specific domain."""
    return DOMAIN_SCHEMAS.get(domain.lower(), "")


def get_schemas_for_domains(domains: list[str]) -> str:
    """Get combined schemas for multiple domains."""
    schemas = []
    for domain in domains:
        schema = get_domain_schema(domain.lower())
        if schema:
            schemas.append(schema)
    return "\n".join(schemas)


def build_schema_context(domains: list[str]) -> SchemaContext:
    """
    Build a complete schema context for the given domains.
    
    Args:
        domains: List of domain names to include
        
    Returns:
        SchemaContext with all necessary information
    """
    return SchemaContext(
        db_summary=DATABASE_SUMMARY,
        selected_domains=domains,
        table_schemas=get_schemas_for_domains(domains),
        relationships=KEY_RELATIONSHIPS,
        query_patterns=QUERY_PATTERNS,
    )


def estimate_context_tokens(domains: list[str]) -> int:
    """
    Estimate tokens for a given set of domains.
    
    Args:
        domains: List of domains to include
        
    Returns:
        Estimated token count
    """
    context = build_schema_context(domains)
    return context.token_estimate
