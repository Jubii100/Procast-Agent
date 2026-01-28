# Procast Database Schema Documentation

## Overview

The Procast database is a sophisticated **event planning and budgeting system** built on PostgreSQL 15.x with ASP.NET Core Identity integration. It contains **60+ tables** organized into functional domains supporting multi-currency financial tracking, project management, and collaborative workspaces.

**Database Version:** PostgreSQL 15.14  
**ORM Framework:** Entity Framework Core (.NET)  
**Authentication:** ASP.NET Core Identity

---

## Table of Contents

1. [Domain Overview](#domain-overview)
2. [Core Entity Tables](#core-entity-tables)
3. [Financial & Budget Tables](#financial--budget-tables)
4. [Project Management Tables](#project-management-tables)
5. [User & Authentication Tables](#user--authentication-tables)
6. [Workspace & Collaboration Tables](#workspace--collaboration-tables)
7. [Reference & Lookup Tables](#reference--lookup-tables)
8. [Audit & History Tables](#audit--history-tables)
9. [Common Column Patterns](#common-column-patterns)
10. [Key Relationships Summary](#key-relationships-summary)

---

## Domain Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          PROCAST DATABASE DOMAINS                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │    USERS &   │    │   PROJECTS   │    │  FINANCIAL   │                   │
│  │    AUTH      │    │   & EVENTS   │    │   TRACKING   │                   │
│  │              │    │              │    │              │                   │
│  │ • People     │───▶│ • Projects   │───▶│ • EntryLines │                   │
│  │ • AspNetUsers│    │ • SubProjects│    │ • Invoices   │                   │
│  │ • Roles      │    │ • Portfolios │    │ • POs        │                   │
│  └──────────────┘    └──────────────┘    └──────────────┘                   │
│         │                   │                   │                            │
│         ▼                   ▼                   ▼                            │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │  WORKSPACES  │    │   ACCOUNTS   │    │  CURRENCIES  │                   │
│  │              │    │   & BUDGET   │    │   & FX       │                   │
│  │              │    │              │    │              │                   │
│  │ • Personal   │    │ • Accounts   │    │ • Currencies │                   │
│  │ • Shared     │    │ • Categories │    │ • FxRates    │                   │
│  │ • Folders    │    │ • SubAccounts│    │ • Tuples     │                   │
│  └──────────────┘    └──────────────┘    └──────────────┘                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Core Entity Tables

### People
**Purpose:** Central user/person entity that all other user-related data links to.

| Column | Type | Description |
|--------|------|-------------|
| `Id` | uuid (PK) | Unique identifier |
| `Email` | varchar(256) | User's email address (unique) |
| `FirstName` | varchar(512) | First name |
| `LastName` | text | Last name |
| `AvatarUrl` | varchar(4096) | Profile picture URL |
| `CompanyId` | uuid (FK) | Link to Companies table |
| `IsArchived` | boolean | Soft delete flag for archived users |
| `IsDisabled` | boolean | Account disabled flag |

**Key Relationships:**
- One-to-One with `AspNetUsers` (identity)
- One-to-Many with `ProjectPeople` (project membership)
- Referenced by audit columns (`CreatedBy`, `LastModifiedBy`) across all tables

---

### Companies
**Purpose:** Organization/tenant entity for multi-tenant support.

| Column | Type | Description |
|--------|------|-------------|
| `Id` | uuid (PK) | Unique identifier |
| `Name` | varchar(1024) | Company name |
| `Address` | varchar(1024) | Company address |
| `PhoneNumber` | varchar(128) | Contact phone |
| `Email` | varchar(256) | Company email |
| `LogoUrl` | varchar(4096) | Company logo |
| `ReportingCurrencyId` | uuid (FK) | Default reporting currency |
| `IsInverseRevenue` | boolean | Revenue calculation flag |

**Key Relationships:**
- One-to-Many with `People`
- Foreign key to `Currencies`

---

## Financial & Budget Tables

### EntryLines ⭐ (Critical for Analysis)
**Purpose:** Individual budget line items - the core transactional data for all budget tracking.

| Column | Type | Description |
|--------|------|-------------|
| `Id` | uuid (PK) | Unique identifier |
| `Description` | varchar(2048) | Line item description |
| `Quantity` | double | Number of units |
| `Amount` | double | Unit price/amount |
| `Status` | integer | Entry status code |
| `OwnerId` | uuid (FK) | Person who owns this entry |
| `ProjectAccountId` | uuid (FK) | Links to project-account combination |
| `LocalCurrencyId` | uuid (FK) | Currency of the amount |
| `PurchaseOrderCode` | varchar(1024) | Associated PO number |
| `InvoiceRefCode` | varchar(256) | Associated invoice reference |
| `EntryStatusId` | uuid (FK) | Detailed status reference |
| `ReconciliationId` | uuid (FK) | Reconciliation batch reference |
| `SupplierName` | varchar(256) | Vendor/supplier name |
| `SubAccountId` | uuid (FK) | Sub-budget allocation |
| `IsComputedInverse` | boolean | Revenue computation flag |

**Calculated Fields:**
- **Total Amount** = `Quantity * Amount`
- **Total in Operating Currency** requires FX conversion via `ConstantFxRates`

**Key Relationships:**
- Many-to-One with `ProjectAccounts`
- Many-to-One with `People` (owner)
- Many-to-Many with `SubProjects` (via `EntryLineSubProject`)

**Trigger:** `my_table_trigger` logs all changes to `EntryLine_H`

---

### Invoices ⭐ (Critical for Analysis)
**Purpose:** Actual posted invoices representing realized spending.

| Column | Type | Description |
|--------|------|-------------|
| `Id` | uuid (PK) | Unique identifier |
| `TransactionId` | text | External transaction reference |
| `TransactionType` | text | Invoice type classification |
| `DateApplied` | timestamptz | Invoice date |
| `HeaderDescription` | text | Invoice header/title |
| `LineDescription` | text | Line item description |
| `EntityCurrencyId` | uuid (FK) | Currency of entity |
| `EntityCurrencyTotal` | numeric | Total in entity currency |
| `LocalCurrencyId` | uuid (FK) | Local currency |
| `LocalCurrencyTotal` | numeric | Total in local currency |
| `PostedFlag` | boolean | Whether invoice is posted |
| `PostedDate` | timestamptz | Date of posting |
| `PostedBy` | text | User who posted |
| `CostCodeId` | uuid (FK) | Cost center code |
| `AccountId` | uuid (FK) | Account reference |
| `InvoiceRefCode` | text | Invoice reference number |
| `PurchaseOrderCode` | text | Associated PO |
| `ReconciliationId` | uuid (FK) | Reconciliation batch |
| `LegalEntityName` | text | Legal entity name |
| `IsNetOffed` | boolean | Net-off flag |

**Key Relationships:**
- Many-to-One with `Currencies` (two: entity and local)
- Many-to-One with `Accounts`
- Many-to-One with `CostCodes`

---

### PurchaseOrders ⭐ (Critical for Analysis)
**Purpose:** Committed purchase orders representing committed (but not yet invoiced) costs.

| Column | Type | Description |
|--------|------|-------------|
| `Id` | uuid (PK) | Unique identifier |
| `TransactionId` | text | External transaction reference |
| `PurchaseOrderCode` | text | PO number |
| `PurchaseOrderStatus` | integer | Status code (0=Draft, 1=Approved, etc.) |
| `EntityCurrencyTotal` | numeric | Total in entity currency |
| `LocalCurrencyTotal` | numeric | Total in local currency |
| `DateApplied` | timestamptz | PO date |
| `PostedFlag` | boolean | Whether PO is posted |
| `CostCodeId` | uuid (FK) | Cost center |
| `AccountId` | uuid (FK) | Account reference |
| `LegalEntityName` | text | Legal entity |

---

### SubAccounts ⭐ (Critical for Analysis)
**Purpose:** Sub-budget allocations within a project for granular budget tracking.

| Column | Type | Description |
|--------|------|-------------|
| `Id` | uuid (PK) | Unique identifier |
| `Name` | text | Sub-account name |
| `Amount` | double | Budgeted amount |
| `AccountId` | uuid (FK) | Parent account |
| `ProjectId` | uuid (FK) | Associated project |
| `CurrencyId` | uuid (FK) | Currency |
| `ProjectAccountId` | uuid (FK) | Project-account link |

---

### AccountCategories ⭐ (Critical for Analysis)
**Purpose:** Hierarchical expense categories (supports parent-child relationships).

| Column | Type | Description |
|--------|------|-------------|
| `Id` | uuid (PK) | Unique identifier |
| `Name` | varchar(2048) | Category name |
| `ParentCategoryId` | uuid (FK, self) | Parent category (for hierarchy) |
| `CategoryPosition` | integer | Display order |

**Self-Referencing:** Supports unlimited nesting of categories.

---

### Accounts
**Purpose:** Chart of accounts - expense/revenue account definitions.

| Column | Type | Description |
|--------|------|-------------|
| `Id` | uuid (PK) | Unique identifier |
| `Number` | bigint | Account number (e.g., 5000, 6000) |
| `Description` | varchar(2048) | Account description |
| `SubAccountCategoryId` | uuid (FK) | Category classification |

---

### ConstantFxRates ⭐ (Critical for Analysis)
**Purpose:** Currency conversion rates by month and financial year.

| Column | Type | Description |
|--------|------|-------------|
| `Id` | uuid (PK) | Unique identifier |
| `MonthOrder` | integer | Month (1-12) |
| `Value` | double | Exchange rate value |
| `FinancialYearId` | uuid (FK) | Financial year |
| `CurrencyTupleId` | uuid (FK) | From/To currency pair |

**Usage Pattern:**
```sql
-- Convert amount from LocalCurrency to OperatingCurrency
SELECT el."Amount" * el."Quantity" * cfr."Value" as converted_amount
FROM "EntryLines" el
JOIN "CurrencyTuples" ct ON ct."FromCurrencyId" = el."LocalCurrencyId"
JOIN "ConstantFxRates" cfr ON cfr."CurrencyTupleId" = ct."Id"
```

---

### CurrencyTuples
**Purpose:** Defines currency conversion pairs (from -> to).

| Column | Type | Description |
|--------|------|-------------|
| `Id` | uuid (PK) | Unique identifier |
| `FromCurrencyId` | uuid (FK) | Source currency |
| `ToCurrencyId` | uuid (FK) | Target currency |

---

### Currencies
**Purpose:** Currency definitions.

| Column | Type | Description |
|--------|------|-------------|
| `Id` | uuid (PK) | Unique identifier |
| `IsoCode` | varchar(3) | ISO 4217 code (USD, EUR, etc.) |

---

### FinancialYears
**Purpose:** Financial year definitions for reporting periods.

| Column | Type | Description |
|--------|------|-------------|
| `Id` | uuid (PK) | Unique identifier |
| `Year` | integer | Year number (2024, 2025, etc.) |
| `StartDate` | date | FY start date |
| `EndDate` | date | FY end date |

---

## Project Management Tables

### Projects ⭐ (Critical for Analysis)
**Purpose:** Events/projects - the main budget containers.

| Column | Type | Description |
|--------|------|-------------|
| `Id` | uuid (PK) | Unique identifier |
| `TakePlaceDate` | date | Event date |
| `Brand` | varchar(256) | Project/event brand name |
| `Edition` | bigint | Edition number |
| `Type` | integer | Project type code |
| `CostCodeId` | uuid (FK) | Default cost code |
| `OperatingCurrencyId` | uuid (FK) | Project's operating currency |
| `CountryId` | uuid (FK) | Event country |
| `OriginalProjectId` | uuid (FK, self) | For scenario cloning |
| `FolderId` | uuid (FK) | Workspace folder |
| `IsLocked` | boolean | Lock status |
| `ApprovalId` | uuid (FK) | Approval workflow |
| `SharedWorkspaceId` | uuid (FK) | Shared workspace |
| `ScenarioName` | varchar(1024) | Scenario name (if cloned) |
| `ScenarioPredefinedNameId` | uuid (FK) | Predefined scenario type |

**Scenario Support:** 
- `OriginalProjectId` links cloned scenarios to the original project
- Enables "what-if" budget analysis

---

### SubProjects
**Purpose:** Sub-events or workstreams within a project.

| Column | Type | Description |
|--------|------|-------------|
| `Id` | uuid (PK) | Unique identifier |
| `Name` | varchar(256) | Sub-project name |
| `CostCodeId` | uuid (FK) | Cost code override |
| `ProjectId` | uuid (FK) | Parent project |

---

### ProjectAccounts
**Purpose:** Junction table linking projects to accounts (which accounts are used in which projects).

| Column | Type | Description |
|--------|------|-------------|
| `Id` | uuid (PK) | Unique identifier |
| `ProjectId` | uuid (FK) | Project reference |
| `LegalEntityAccountId` | uuid (FK) | Legal entity account |

**Central to Budget Analysis:** All `EntryLines` reference a `ProjectAccount`.

---

### ProjectPeople
**Purpose:** Project team membership with roles.

| Column | Type | Description |
|--------|------|-------------|
| `Id` | uuid (PK) | Unique identifier |
| `PersonId` | uuid (FK) | Team member |
| `ProjectId` | uuid (FK) | Project |
| `IsApprover` | boolean | Has approval rights |
| `IsOwner` | boolean | Is project owner |
| `PersonalWorkspaceId` | uuid (FK) | User's workspace for this project |

---

### Portfolios
**Purpose:** Groups of related projects.

| Column | Type | Description |
|--------|------|-------------|
| `Id` | uuid (PK) | Unique identifier |
| `Name` | varchar(1024) | Portfolio name |

---

### ProjectPortfolios
**Purpose:** Many-to-many link between projects and portfolios.

---

## User & Authentication Tables

### AspNetUsers
**Purpose:** ASP.NET Core Identity user accounts.

| Column | Type | Description |
|--------|------|-------------|
| `Id` | text (PK) | Identity user ID |
| `PersonId` | uuid (FK) | Link to People table |
| `UserName` | varchar(256) | Login username |
| `Email` | varchar(256) | Email address |
| `PasswordHash` | text | Hashed password |
| `FirstLogin` | boolean | First login flag |
| `ResetPassword` | boolean | Password reset required |
| `TwoFactorEnabled` | boolean | 2FA status |
| `LockoutEnabled` | boolean | Lockout policy |
| `AccessFailedCount` | integer | Failed login attempts |

---

### AspNetRoles
**Purpose:** Role definitions for RBAC.

| Column | Type | Description |
|--------|------|-------------|
| `Id` | text (PK) | Role ID |
| `Name` | varchar(256) | Role name |
| `NormalizedName` | varchar(256) | Uppercase role name |

---

### AspNetUserRoles
**Purpose:** User-role assignments (many-to-many).

---

### RefreshTokens
**Purpose:** JWT refresh token storage.

| Column | Type | Description |
|--------|------|-------------|
| `Id` | uuid (PK) | Token ID |
| `Token` | varchar(512) | Refresh token value |
| `UserId` | varchar(256) | Associated user |
| `ExpiresAt` | timestamptz | Expiration time |
| `LastActivity` | timestamptz | Last token use |

---

## Workspace & Collaboration Tables

### PersonalWorkspaces
**Purpose:** User's personal workspace containing their project views.

---

### SharedWorkspaces
**Purpose:** Shared workspaces for team collaboration.

---

### Folders
**Purpose:** Folder organization within workspaces.

| Column | Type | Description |
|--------|------|-------------|
| `Id` | uuid (PK) | Unique identifier |
| `Name` | varchar(256) | Folder name |
| `PersonalWorkspaceId` | uuid (FK) | Parent personal workspace |
| `SharedWorkspaceId` | uuid (FK) | Parent shared workspace |

---

## Reference & Lookup Tables

### LegalEntities
**Purpose:** Legal entity/subsidiary definitions.

| Column | Type | Description |
|--------|------|-------------|
| `Id` | uuid (PK) | Unique identifier |
| `Name` | varchar(1024) | Entity name |
| `CountryId` | uuid (FK) | Country of incorporation |
| `EntityCurrencyId` | uuid (FK) | Default currency |
| `NickName` | text | Short name |

---

### LegalEntityAccounts
**Purpose:** Accounts available to each legal entity.

---

### LegalEntityProjects
**Purpose:** Which legal entities are involved in which projects.

| Column | Type | Description |
|--------|------|-------------|
| `IsPrimary` | boolean | Primary entity flag |

---

### Countries
**Purpose:** Country reference data.

| Column | Type | Description |
|--------|------|-------------|
| `IsoCode` | varchar(3) | ISO 3166 country code |
| `Name` | varchar(256) | Country name |

---

### Regions
**Purpose:** Geographic regions.

---

### Industries
**Purpose:** Industry classifications for projects.

---

### Divisions
**Purpose:** Organizational divisions.

---

### Partners
**Purpose:** External partner/vendor companies.

---

### CostCodes
**Purpose:** Cost center/code definitions.

| Column | Type | Description |
|--------|------|-------------|
| `Code` | varchar(128) | Cost code identifier |
| `Description` | varchar(1024) | Code description |

---

### EntryStatuses
**Purpose:** Detailed status definitions for entry lines.

---

## Audit & History Tables

### EntryLine_H ⭐ (Critical for Analysis)
**Purpose:** Audit history of all entry line changes - essential for trend analysis.

| Column | Type | Description |
|--------|------|-------------|
| `Id` | uuid (PK) | Unique identifier |
| `Action` | text | "Line Added", "Line Deleted", "Changes in Line" |
| `TableName` | text | Source table name |
| `OldData` | text | JSON of previous values |
| `NewData` | text | JSON of new values |
| `ProjectAccountId` | uuid (FK) | Associated project account |
| `LatestViewTotalCurrent` | double | Running total after change |
| `LatestViewTotalPrevious` | double | Running total before change |
| `Created` | timestamptz | Change timestamp |
| `LastModifiedBy` | uuid (FK) | User who made change |

**Populated by:** Database trigger `log_table_changes()` on `EntryLines`

---

### Notes
**Purpose:** User notes attached to any entity.

| Column | Type | Description |
|--------|------|-------------|
| `Description` | varchar(4096) | Note content |
| `TargetedPersonId` | uuid (FK) | Mentioned person |
| `TargetedDbEntityId` | uuid | Target entity ID |
| `TargetedDbEntityTypeId` | uuid (FK) | Target entity type |

---

### ReviewRequests
**Purpose:** Review/approval request workflow.

---

### Approvals
**Purpose:** Approval records.

| Column | Type | Description |
|--------|------|-------------|
| `Status` | integer | Approval status code |
| `Description` | varchar(4096) | Approval notes |
| `PersonId` | uuid (FK) | Approver |

---

## Common Column Patterns

All tables follow a consistent audit pattern:

| Column | Type | Description |
|--------|------|-------------|
| `Id` | uuid | Primary key (auto-generated) |
| `IsDisabled` | boolean | Soft delete flag |
| `DbEntityTypeId` | uuid (FK) | Entity type classification |
| `Created` | timestamptz | Creation timestamp |
| `CreatedBy` | uuid (FK) | Creator (People.Id) |
| `LastModified` | timestamptz | Last modification timestamp |
| `LastModifiedBy` | uuid (FK) | Modifier (People.Id) |

---

## Key Relationships Summary

### Budget Analysis Flow

```
People (user)
    │
    ▼
ProjectPeople (membership)
    │
    ▼
Projects (event/budget container)
    │
    ├──▶ ProjectAccounts (project-account junction)
    │        │
    │        ▼
    │    EntryLines (budget line items) ◀── SubAccounts
    │        │
    │        ├──▶ Currencies + ConstantFxRates (FX conversion)
    │        │
    │        └──▶ EntryLine_H (change history)
    │
    ├──▶ Invoices (realized spending)
    │
    └──▶ PurchaseOrders (committed costs)
```

### Account Hierarchy

```
AccountCategories (parent)
    │
    └──▶ AccountCategories (child - self-referencing)
            │
            └──▶ Accounts
                    │
                    └──▶ LegalEntityAccounts
                            │
                            └──▶ ProjectAccounts
                                    │
                                    └──▶ EntryLines
```

### Currency Conversion

```
Currencies (from)
    │
    └──▶ CurrencyTuples
            │
            └──▶ ConstantFxRates ◀── FinancialYears
```

---

## Analysis-Ready Queries

### Total Budget by Project

```sql
SELECT 
    p."Brand" as project_name,
    p."TakePlaceDate" as event_date,
    c."IsoCode" as currency,
    SUM(el."Amount" * el."Quantity") as total_budget
FROM "Projects" p
JOIN "ProjectAccounts" pa ON pa."ProjectId" = p."Id"
JOIN "EntryLines" el ON el."ProjectAccountId" = pa."Id"
JOIN "Currencies" c ON c."Id" = p."OperatingCurrencyId"
WHERE el."IsDisabled" = false
GROUP BY p."Id", p."Brand", p."TakePlaceDate", c."IsoCode";
```

### Budget vs Actuals (Invoices)

```sql
SELECT 
    p."Brand" as project_name,
    SUM(el."Amount" * el."Quantity") as budgeted,
    COALESCE(SUM(i."LocalCurrencyTotal"), 0) as invoiced
FROM "Projects" p
JOIN "ProjectAccounts" pa ON pa."ProjectId" = p."Id"
LEFT JOIN "EntryLines" el ON el."ProjectAccountId" = pa."Id" AND el."IsDisabled" = false
LEFT JOIN "Invoices" i ON i."AccountId" = (
    SELECT lea."AccountId" FROM "LegalEntityAccounts" lea WHERE lea."Id" = pa."LegalEntityAccountId"
)
GROUP BY p."Id", p."Brand";
```

### Overspending Detection

```sql
SELECT 
    p."Brand" as project_name,
    ac."Name" as category,
    SUM(el."Amount" * el."Quantity") as budgeted,
    SUM(CASE WHEN el."Status" >= 2 THEN el."Amount" * el."Quantity" ELSE 0 END) as committed,
    CASE 
        WHEN SUM(CASE WHEN el."Status" >= 2 THEN el."Amount" * el."Quantity" ELSE 0 END) > 
             SUM(el."Amount" * el."Quantity") 
        THEN 'OVERSPENT'
        ELSE 'OK'
    END as status
FROM "Projects" p
JOIN "ProjectAccounts" pa ON pa."ProjectId" = p."Id"
JOIN "EntryLines" el ON el."ProjectAccountId" = pa."Id"
JOIN "LegalEntityAccounts" lea ON lea."Id" = pa."LegalEntityAccountId"
JOIN "Accounts" a ON a."Id" = lea."AccountId"
JOIN "AccountCategories" ac ON ac."Id" = a."SubAccountCategoryId"
WHERE el."IsDisabled" = false
GROUP BY p."Id", p."Brand", ac."Id", ac."Name";
```

---

## Notes for AI Agent Integration

1. **Always filter by `IsDisabled = false`** - Soft deletes are used throughout
2. **Currency conversion is mandatory** for accurate cross-project analysis
3. **`EntryLine_H` provides change tracking** - Use for trend analysis
4. **Project scenarios** (`OriginalProjectId`) enable what-if analysis
5. **Status codes vary by table** - Check enum definitions in .NET codebase
