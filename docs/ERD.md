# Procast Database Entity Relationship Diagrams

## Overview

This document provides visual entity-relationship diagrams for the Procast database using Mermaid syntax.

---

## Complete High-Level ERD

```mermaid
erDiagram
    %% Core User & Identity
    People ||--o{ AspNetUsers : "has identity"
    People ||--o{ ProjectPeople : "participates in"
    Companies ||--o{ People : "employs"
    
    %% Project Management
    Projects ||--o{ ProjectPeople : "has members"
    Projects ||--o{ ProjectAccounts : "has accounts"
    Projects ||--o{ SubProjects : "has sub-events"
    Projects ||--o| Projects : "scenario of"
    Projects }o--|| Folders : "organized in"
    
    %% Financial Core
    ProjectAccounts ||--o{ EntryLines : "contains"
    LegalEntities ||--o{ LegalEntityAccounts : "owns"
    LegalEntityAccounts ||--o{ ProjectAccounts : "linked to"
    Accounts ||--o{ LegalEntityAccounts : "assigned to"
    AccountCategories ||--o{ Accounts : "categorizes"
    AccountCategories ||--o| AccountCategories : "parent of"
    
    %% Budget Line Items
    EntryLines }o--|| Currencies : "denominated in"
    EntryLines }o--o| SubAccounts : "allocated to"
    EntryLines }o--o| Reconciliations : "reconciled in"
    SubProjects ||--o{ EntryLineSubProject : "tagged in"
    EntryLines ||--o{ EntryLineSubProject : "tagged with"
    
    %% Actuals Tracking
    Projects ||--o{ Invoices : "incurs"
    Projects ||--o{ PurchaseOrders : "creates"
    Invoices }o--|| Currencies : "in currency"
    PurchaseOrders }o--|| Currencies : "in currency"
    
    %% Currency & FX
    Currencies ||--o{ CurrencyTuples : "from"
    CurrencyTuples ||--o{ ConstantFxRates : "has rates"
    FinancialYears ||--o{ ConstantFxRates : "for year"
    
    %% Workspaces
    PersonalWorkspaces ||--o{ Folders : "contains"
    SharedWorkspaces ||--o{ Folders : "contains"
    PersonalWorkspaces ||--o{ ProjectPeople : "assigned to"
    
    %% History
    EntryLines ||--o{ EntryLine_H : "history"
    ProjectAccounts ||--o{ EntryLine_H : "tracks"
```

---

## Domain-Specific ERDs

### 1. User & Authentication Domain

```mermaid
erDiagram
    People {
        uuid Id PK
        varchar Email UK
        varchar FirstName
        text LastName
        varchar AvatarUrl
        uuid CompanyId FK
        boolean IsArchived
        boolean IsDisabled
        timestamptz Created
        uuid CreatedBy FK
    }
    
    AspNetUsers {
        text Id PK
        uuid PersonId FK
        varchar UserName
        varchar Email
        text PasswordHash
        boolean FirstLogin
        boolean ResetPassword
        boolean TwoFactorEnabled
        boolean LockoutEnabled
        int AccessFailedCount
    }
    
    AspNetRoles {
        text Id PK
        varchar Name
        varchar NormalizedName
    }
    
    AspNetUserRoles {
        text UserId PK_FK
        text RoleId PK_FK
    }
    
    RefreshTokens {
        uuid Id PK
        varchar Token UK
        varchar UserId FK
        timestamptz ExpiresAt
        timestamptz LastActivity
    }
    
    Companies {
        uuid Id PK
        varchar Name
        varchar Address
        uuid ReportingCurrencyId FK
        boolean IsInverseRevenue
    }
    
    People ||--|| AspNetUsers : "identity"
    People }o--|| Companies : "works for"
    AspNetUsers ||--o{ AspNetUserRoles : "has"
    AspNetRoles ||--o{ AspNetUserRoles : "assigned to"
    AspNetUsers ||--o{ RefreshTokens : "has tokens"
```

---

### 2. Project Management Domain

```mermaid
erDiagram
    Projects {
        uuid Id PK
        date TakePlaceDate
        varchar Brand
        bigint Edition
        int Type
        uuid CostCodeId FK
        uuid OperatingCurrencyId FK
        uuid CountryId FK
        uuid OriginalProjectId FK
        uuid FolderId FK
        boolean IsLocked
        uuid ApprovalId FK
        uuid SharedWorkspaceId FK
        varchar ScenarioName
    }
    
    SubProjects {
        uuid Id PK
        varchar Name
        uuid CostCodeId FK
        uuid ProjectId FK
    }
    
    ProjectPeople {
        uuid Id PK
        uuid PersonId FK
        uuid ProjectId FK
        boolean IsApprover
        boolean IsOwner
        uuid PersonalWorkspaceId FK
    }
    
    Portfolios {
        uuid Id PK
        varchar Name
    }
    
    ProjectPortfolios {
        uuid Id PK
        uuid ProjectId FK
        uuid PortfolioId FK
    }
    
    Folders {
        uuid Id PK
        varchar Name
        uuid PersonalWorkspaceId FK
        uuid SharedWorkspaceId FK
    }
    
    Projects ||--o{ SubProjects : "contains"
    Projects ||--o{ ProjectPeople : "has team"
    Projects }o--o| Projects : "scenario of"
    Projects }o--|| Folders : "in folder"
    Projects ||--o{ ProjectPortfolios : "belongs to"
    Portfolios ||--o{ ProjectPortfolios : "contains"
    People ||--o{ ProjectPeople : "member of"
```

---

### 3. Financial & Budget Domain (Core)

```mermaid
erDiagram
    ProjectAccounts {
        uuid Id PK
        uuid ProjectId FK
        uuid LegalEntityAccountId FK
    }
    
    EntryLines {
        uuid Id PK
        varchar Description
        double Quantity
        double Amount
        int Status
        uuid OwnerId FK
        uuid ProjectAccountId FK
        uuid LocalCurrencyId FK
        varchar PurchaseOrderCode
        varchar InvoiceRefCode
        uuid EntryStatusId FK
        uuid ReconciliationId FK
        varchar SupplierName
        uuid SubAccountId FK
        boolean IsComputedInverse
    }
    
    SubAccounts {
        uuid Id PK
        text Name
        double Amount
        uuid AccountId FK
        uuid ProjectId FK
        uuid CurrencyId FK
        uuid ProjectAccountId FK
    }
    
    EntryLine_H {
        uuid Id PK
        text Action
        text TableName
        text OldData
        text NewData
        uuid ProjectAccountId FK
        double LatestViewTotalCurrent
        double LatestViewTotalPrevious
        timestamptz Created
        uuid LastModifiedBy FK
    }
    
    EntryLineSubProject {
        uuid EntryLinesId PK_FK
        uuid SubProjectsId PK_FK
    }
    
    Projects ||--o{ ProjectAccounts : "has"
    ProjectAccounts ||--o{ EntryLines : "contains"
    ProjectAccounts ||--o{ SubAccounts : "has"
    EntryLines }o--o| SubAccounts : "allocated to"
    EntryLines ||--o{ EntryLine_H : "audit trail"
    EntryLines ||--o{ EntryLineSubProject : "tagged"
    SubProjects ||--o{ EntryLineSubProject : "tags"
```

---

### 4. Account Hierarchy Domain

```mermaid
erDiagram
    AccountCategories {
        uuid Id PK
        varchar Name
        uuid ParentCategoryId FK
        int CategoryPosition
    }
    
    Accounts {
        uuid Id PK
        bigint Number
        varchar Description
        uuid SubAccountCategoryId FK
    }
    
    LegalEntityAccounts {
        uuid Id PK
        uuid LegalEntityId FK
        uuid AccountId FK
    }
    
    LegalEntities {
        uuid Id PK
        varchar Name
        uuid CountryId FK
        uuid EntityCurrencyId FK
        text NickName
    }
    
    AccountCategories ||--o| AccountCategories : "parent of"
    AccountCategories ||--o{ Accounts : "contains"
    Accounts ||--o{ LegalEntityAccounts : "available to"
    LegalEntities ||--o{ LegalEntityAccounts : "has access to"
    LegalEntityAccounts ||--o{ ProjectAccounts : "used in"
```

---

### 5. Currency & FX Domain

```mermaid
erDiagram
    Currencies {
        uuid Id PK
        varchar IsoCode
    }
    
    CurrencyTuples {
        uuid Id PK
        uuid FromCurrencyId FK
        uuid ToCurrencyId FK
    }
    
    ConstantFxRates {
        uuid Id PK
        int MonthOrder
        double Value
        uuid FinancialYearId FK
        uuid CurrencyTupleId FK
    }
    
    FinancialYears {
        uuid Id PK
        int Year
        date StartDate
        date EndDate
    }
    
    Currencies ||--o{ CurrencyTuples : "from"
    Currencies ||--o{ CurrencyTuples : "to"
    CurrencyTuples ||--o{ ConstantFxRates : "has rates"
    FinancialYears ||--o{ ConstantFxRates : "for period"
    
    Currencies ||--o{ EntryLines : "denominated in"
    Currencies ||--o{ Projects : "operating currency"
    Currencies ||--o{ Companies : "reporting currency"
```

---

### 6. Actuals & Reconciliation Domain

```mermaid
erDiagram
    Invoices {
        uuid Id PK
        text TransactionId
        text TransactionType
        timestamptz DateApplied
        text HeaderDescription
        text LineDescription
        uuid EntityCurrencyId FK
        numeric EntityCurrencyTotal
        uuid LocalCurrencyId FK
        numeric LocalCurrencyTotal
        boolean PostedFlag
        timestamptz PostedDate
        text PostedBy
        uuid CostCodeId FK
        uuid AccountId FK
        text InvoiceRefCode
        text PurchaseOrderCode
        uuid ReconciliationId FK
        boolean IsNetOffed
    }
    
    PurchaseOrders {
        uuid Id PK
        text TransactionId
        text PurchaseOrderCode
        int PurchaseOrderStatus
        numeric EntityCurrencyTotal
        numeric LocalCurrencyTotal
        timestamptz DateApplied
        boolean PostedFlag
        uuid CostCodeId FK
        uuid AccountId FK
    }
    
    Reconciliations {
        uuid Id PK
        timestamptz Created
    }
    
    CostCodes {
        uuid Id PK
        varchar Code
        varchar Description
    }
    
    Invoices }o--|| Reconciliations : "in batch"
    EntryLines }o--o| Reconciliations : "reconciled"
    Invoices }o--|| CostCodes : "charged to"
    PurchaseOrders }o--|| CostCodes : "charged to"
    Invoices }o--|| Accounts : "posted to"
    PurchaseOrders }o--|| Accounts : "posted to"
```

---

## Data Flow Diagrams

### Budget Entry Flow

```mermaid
flowchart TD
    subgraph Input
        User[User/Person]
        Currency[Select Currency]
    end
    
    subgraph ProjectContext
        Project[Project]
        Account[Account Category]
        PA[ProjectAccount]
    end
    
    subgraph EntryCreation
        Entry[EntryLine]
        SubAcc[SubAccount Optional]
        SubProj[SubProject Tags]
    end
    
    subgraph Audit
        History[EntryLine_H]
        Trigger[DB Trigger]
    end
    
    User --> Project
    Project --> PA
    Account --> PA
    PA --> Entry
    Currency --> Entry
    SubAcc -.-> Entry
    SubProj -.-> Entry
    Entry --> Trigger
    Trigger --> History
```

### Currency Conversion Flow

```mermaid
flowchart LR
    subgraph EntryData
        Amount[Amount in Local Currency]
        LocalCurr[LocalCurrencyId]
    end
    
    subgraph LookupChain
        CT[CurrencyTuples]
        FY[FinancialYears]
        FXR[ConstantFxRates]
    end
    
    subgraph ProjectContext
        OpCurr[Project Operating Currency]
        EventDate[TakePlaceDate]
    end
    
    subgraph Result
        Converted[Amount in Operating Currency]
    end
    
    LocalCurr --> CT
    OpCurr --> CT
    CT --> FXR
    EventDate --> FY
    FY --> FXR
    Amount --> FXR
    FXR --> Converted
```

### Budget vs Actuals Reconciliation

```mermaid
flowchart TB
    subgraph Budget
        EL[EntryLines]
        PA[ProjectAccount]
    end
    
    subgraph Actuals
        INV[Invoices]
        PO[PurchaseOrders]
    end
    
    subgraph Matching
        POCode[PurchaseOrderCode]
        InvCode[InvoiceRefCode]
        AccMatch[Account Match]
    end
    
    subgraph Reconciliation
        Recon[Reconciliation Record]
        Status[Reconciliation Status]
    end
    
    EL --> POCode
    EL --> InvCode
    PO --> POCode
    INV --> InvCode
    PA --> AccMatch
    INV --> AccMatch
    POCode --> Recon
    InvCode --> Recon
    AccMatch --> Recon
    Recon --> Status
```

---

## Key Cardinality Rules

| Relationship | Cardinality | Description |
|-------------|-------------|-------------|
| People → AspNetUsers | 1:1 | Every person has exactly one identity |
| People → ProjectPeople | 1:N | A person can be in many projects |
| Projects → ProjectAccounts | 1:N | A project has many account assignments |
| ProjectAccounts → EntryLines | 1:N | Each account-project pair has many entries |
| AccountCategories → AccountCategories | 1:N | Self-referencing for hierarchy |
| Currencies → CurrencyTuples | 1:N | Each currency can be in many pairs |
| CurrencyTuples → ConstantFxRates | 1:N | Each pair has rates for many months |
| EntryLines → EntryLine_H | 1:N | Each entry has audit history |
| Projects → Projects | 1:N | Scenarios reference original project |

---

## Notes for Implementation

1. **UUID Primary Keys**: All tables use UUID for primary keys, enabling distributed ID generation
2. **Soft Deletes**: `IsDisabled` column is used instead of hard deletes
3. **Audit Trail**: All tables have `Created`, `CreatedBy`, `LastModified`, `LastModifiedBy`
4. **Self-References**: `AccountCategories` and `Projects` have self-referencing FKs
5. **Composite Keys**: Junction tables like `EntryLineSubProject` use composite PKs
