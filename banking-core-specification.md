# Banking core — Specification

> Specification document for implementation with Claude Code. Sections marked as **Pending** are not yet decided and must not be implemented by assumption.

## 1. Context

A minimal banking core that records accounts and money movements under the **double-entry bookkeeping rule**. Every balance change happens through balanced movements; a balance is never modified directly.

## 2. Tech stack

- **Language:** Python
- **Web framework:** Flask
- **ORM:** SQLAlchemy
- **Database:** PostgreSQL, running in Docker (`docker-compose`)
- **Currency:** Mexican pesos (MXN) only

## 3. Architecture

Clean architecture, with dependencies always pointing toward the domain.

| Layer | Responsibility | May depend on |
|---|---|---|
| **Domain** | Entities, value objects, accounting rules and invariants | Nothing external (no Flask, no SQLAlchemy) |
| **Application** | Use cases (deposit, withdrawal, transfer, opening) and repository interfaces | Domain |
| **Infrastructure** | Repository implementations with SQLAlchemy, ORM models, DB session and transactions | Application, Domain |
| **Delivery (API)** | Flask routes, input and output serialization | Application |

Rules:

- The domain imports nothing from Flask or SQLAlchemy.
- Repositories are defined as interfaces (`Protocol` or abstract classes) in the application or domain layer, and implemented in infrastructure.
- Use cases receive their dependencies through injection.

### Folder structure

The code is organized by business module, and each module holds its layers inside:

```
docker-compose.yml        # PostgreSQL
.env.example              # reference environment variables (.env is not committed)
app.py                    # entry point: creates the Flask app from src/main
src/
├── main/                 # shared: configuration, DB session, JWT, error handling, route registration, dependency injection
├── user/                 # users, roles, RBAC, authentication
│   ├── domain_model/
│   ├── application_service/
│   ├── infrastructure/
│   └── api/
└── account/              # accounts, transactions, movements and operations
    ├── domain_model/
    ├── application_service/
    ├── infrastructure/
    └── api/
```

| Folder | Layer (§3) |
|---|---|
| `domain_model/` | Domain |
| `application_service/` | Application |
| `infrastructure/` | Infrastructure |
| `api/` | Delivery |

### Local database

- PostgreSQL 17 in Docker, defined in `docker-compose.yml`. 15+ is required for `UNIQUE NULLS NOT DISTINCT`.
- Credentials and configuration come from `.env`, based on `.env.example`.
- Start it with `docker compose up -d`.

## 4. Accounting model

### 4.1 Accounts

There is **a single account type**. All accounts have the same structure and the same rules. They differ only by an internal label:

```python
class AccountClass(Enum):
    NOSTRO = "NOSTRO"   # the bank's own account
    VOSTRO = "VOSTRO"   # client account
```

The label **does not change the accounting behavior**. It only indicates whether the holder is the bank or a client.

### 4.2 Fractal ledger: credit account and debit account

Each account is itself a small double-entry **ledger**, made of two ledger accounts, one of each nature:

- **Credit account:** what the bank owes the holder (liability). Its balance is the account's balance, the one the holder sees.
- **Debit account:** the money the bank holds for it (asset), the accounting mirror of everything that comes into and leaves the account.

```python
class Nature(Enum):
    CREDIT = "CREDIT"   # liability
    DEBIT = "DEBIT"     # asset
```

The ledger carries the class, the alias and the holder. Its two ledger accounts are opened with it, in the same transaction, and belong only to it. The API works only with ledgers: what it calls an account (`account_id`, `account_class`) is a ledger, and ledger accounts are not reached through it.

Every operation that affects an account records a movement on one of its ledger accounts and the opposite movement on the other. This way, **each ledger balances with itself** and can be audited in isolation, without looking at the rest of the books.

### 4.3 Balances

- Balances are **not stored**. They are always computed from the movements.
- The credit account has the credit nature: **balance = credits − debits**.
  - A credit increases the account's balance.
  - A debit decreases it.
- The debit account has the debit nature: **balance = debits − credits**.
- An account's balance is its credit account's balance. By construction, it always equals its debit account's balance: assets = liabilities.

### 4.4 Movements

- Movements are **immutable**: they are never edited or deleted.
- Every movement belongs to a transaction.
- A movement's amount is always positive; the direction is given by whether it is a debit or a credit.
- Amounts use `Decimal` in the domain and `NUMERIC(18,2)` in the database. Never `float`.

## 5. Operations

Each operation is an **atomic transaction**: either all of its movements are recorded or none are.

| Operation | Debit | Credit |
|---|---|---|
| **Deposit** to A | Debit account A | Credit account A |
| **Withdrawal** from A | Credit account A | Debit account A |
| **Transfer** A → B | Credit account A | Debit account A |
| | Debit account B | Credit account B |

- **Deposit:** external money comes into the account. 2 movements.
- **Withdrawal:** money leaves the account to outside the bank. 2 movements.
- **Transfer:** only between accounts of the same bank. Each account goes through its own two ledger accounts. 4 movements in a single transaction.

The operations apply equally to NOSTRO and VOSTRO accounts.

### Transaction type

Within an account's ledger, a withdrawal and an outgoing transfer produce identical movements. What tells them apart is the transaction they belong to, so every transaction carries a type:

```python
class TransactionType(Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    TRANSFER = "TRANSFER"
    REVERSAL = "REVERSAL"
```

A **reversal** (§8.15) undoes a previous transaction with a new transaction of type `REVERSAL`, which repeats its movements with the opposite entry type. The original is neither edited nor deleted (§4.4).

## 6. Invariants

The domain must validate these rules **before persisting** any transaction:

1. **Transaction balance:** the sum of debits equals the sum of credits.
2. **Per-account balance:** in each account, the credit account's balance equals the debit account's balance (assets = liabilities). Every movement belongs to a ledger account of one of the transaction's accounts.
3. **No negative balances:** no account, NOSTRO or VOSTRO, may end up with a negative balance. Withdrawals and transfers without sufficient funds are rejected.
   - The debit account is not checked separately: its balance always equals the credit account's.
4. **Positive amounts:** every movement has an amount > 0.
5. **Transfers:** the source account and the destination account must be different.

## 7. Users and roles

Every user has exactly one of these roles. Roles and their permissions are a **fixed seed** in the database (see §9, RBAC schema):

| Role | Scope |
|---|---|
| **Client** | May hold several accounts. Makes deposits, withdrawals and transfers, only on their own accounts. |
| **Operator** | Operates and opens NOSTRO accounts. Opens VOSTRO accounts and can view their balances and movements, but cannot perform operations on them. |
| **Admin** | Full access to the whole ledger: NOSTRO and VOSTRO accounts, and user management. |

### RBAC

Authorization is based on **permissions**, not roles. Use cases ask "does the user have this permission?" and never "is the user an operator?". A role is just a grouping of permissions.

A permission is the combination of an **action** and a **scope**:

```python
class Action(Enum):
    VIEW = "VIEW"
    DEPOSIT = "DEPOSIT"
    WITHDRAW = "WITHDRAW"
    TRANSFER = "TRANSFER"
    OPEN_ACCOUNT = "OPEN_ACCOUNT"
    REVERSE = "REVERSE"
    MANAGE_USERS = "MANAGE_USERS"

class Scope(Enum):
    OWN = "OWN"           # accounts held by the authenticated user
    VOSTRO = "VOSTRO"     # any client account
    NOSTRO = "NOSTRO"     # the bank's accounts
```

Permission assignment:

| Permission | Client | Operator | Admin |
|---|---|---|---|
| `VIEW`, `DEPOSIT`, `WITHDRAW`, `TRANSFER` on `OWN` | ✓ | | |
| `VIEW:VOSTRO` | | ✓ | ✓ |
| `DEPOSIT`, `WITHDRAW`, `TRANSFER` on `VOSTRO` | | | ✓ |
| `VIEW`, `DEPOSIT`, `WITHDRAW`, `TRANSFER` on `NOSTRO` | | ✓ | ✓ |
| `OPEN_ACCOUNT:NOSTRO` | | ✓ | ✓ |
| `OPEN_ACCOUNT:VOSTRO` | | ✓ | ✓ |
| `REVERSE` on `VOSTRO` and `NOSTRO` | | | ✓ |
| `MANAGE_USERS` | | | ✓ |

Evaluation:

1. The use case determines the scope of each involved account:
   - VOSTRO with `holder_id` equal to the authenticated user → `OWN`.
   - VOSTRO of another holder → `VOSTRO`.
   - NOSTRO → `NOSTRO`.
2. A domain authorization service checks whether the user's role includes the `(action, scope)` permission. If not, the operation is rejected before touching the ledger.
3. In a transfer, the permission is evaluated on the **source** account. The destination account only has to exist.
4. In a reversal, the `REVERSE` permission is evaluated on **every** account of the original transaction.

General rules:

- Authorization is validated in the application layer (use cases), not only in the Flask routes.
- NOSTRO accounts belong to the bank as an entity and have no holder user. Their holder is the **bank's name**, taken from configuration (environment variable `BANK_NAME`) and shown as the holder in responses.
- VOSTRO accounts always have a single client holder. A client may have several.

### Client signup

- Clients do not sign themselves up. The operator signs up the client as part of opening their VOSTRO account.
- The opening use case receives the new client's data, creates the user with role `CLIENT` and opens the account in **a single DB transaction**: both are created or neither is.
- This signup is covered by `OPEN_ACCOUNT:VOSTRO`. It does not require `MANAGE_USERS` and only allows creating users with role `CLIENT`.
- The operator assigns an **initial password**. The user is created with `must_change_password = true`.
- While `must_change_password` is `true`, the client can authenticate but the only operation allowed is changing their password. Once changed, the flag becomes `false`.
- The operator never sees or stores the plain-text password after signup; only the hash is persisted.

### Operator and admin signup

- Operators and admins are created by an admin, with the `MANAGE_USERS` permission.
- As with clients, the admin assigns an initial password and the user is created with `must_change_password = true`.

### At least one admin

- The system must always have **at least one active admin**.
- Any operation that would leave zero active admins is rejected: today, deactivating the last admin (§8.14). A user's role does not change after signup.
- The validation is done in the use case, inside the DB transaction, locking the rows of the active admins (`SELECT ... FOR UPDATE`). This way, two admins cannot deactivate each other at the same time and leave the system without an administrator.

### First admin

- Since no user can create the first admin from the API, it is created with a console command (for example `flask create-admin`) that runs only once when installing the system. From then on, admins are created from the API.

### Additional accounts

- Opening an additional account follows the same flow: the operator opens it for the client.
- If the client already exists, no new user is created. The operator identifies the client by their `email` (unique) and the new account is associated with that user.
- The VOSTRO account opening use case therefore accepts two forms of input:
  - **New client:** client data + initial password → creates user and account.
  - **Existing client:** client email → only creates the account.
- If an email that already exists is given when trying to create a new client, the operation is rejected.

### Authentication

- Traditional JWT: a single **access token**, no refresh tokens.
- The access token lasts **20 minutes** (claim `exp`). The value is taken from configuration, with 20 minutes as the default.
- The user logs in with email and password and receives the token. When it expires, they log in again.
- The token is sent on every request in the `Authorization: Bearer <token>` header.
- Signed with HS256 and a secret key taken from environment variables, never written in the code.
- There is no revocation list: logging out happens on the client side (discarding the token).
- The token carries the user's `id` and the name of their role.
- On every request the user is looked up in the database to verify they are still active and to get their current role. This way, a deactivation or a role change takes effect without waiting for the token to expire.
- Since the role → permissions matrix is fixed, it can be loaded once at application startup and kept in memory.
- The delivery layer translates the token into an authenticated user object (id, role, permissions), which is passed to the use cases for authorization.

## 8. Application services

Each service is a use case in the application layer. It receives the authenticated user, validates permissions and business rules, and runs everything inside a single DB transaction.

All signup services share these rules:

- The `email` must be unique; if it already exists, the operation is rejected.
- An initial password is assigned, only its hash is stored, and the user is created with `must_change_password = true`.
- The user is created with `active = true`.

### 8.1 Admin signup

| | |
|---|---|
| **Run by** | Admin |
| **Required permission** | `MANAGE_USERS` |
| **Input** | `email`, initial password |
| **Effect** | Creates a user with role `ADMIN` |
| **Rejections** | No permission; duplicate email |

### 8.2 Operator signup

| | |
|---|---|
| **Run by** | Admin |
| **Required permission** | `MANAGE_USERS` |
| **Input** | `email`, initial password |
| **Effect** | Creates a user with role `OPERATOR` |
| **Rejections** | No permission; duplicate email |

### 8.3 Client signup

| | |
|---|---|
| **Run by** | Operator (or admin) |
| **Required permission** | `OPEN_ACCOUNT:VOSTRO` |
| **Input** | `email`, initial password, client data |
| **Effect** | Creates a user with role `CLIENT` and their first VOSTRO account with its two ledger accounts (§4.2), in the same transaction |
| **Rejections** | No permission; duplicate email |

### 8.4 Account opening

Additional VOSTRO account for an existing client.

| | |
|---|---|
| **Run by** | Operator (or admin) |
| **Required permission** | `OPEN_ACCOUNT:VOSTRO` |
| **Input** | Client's `email` |
| **Effect** | Creates a VOSTRO account with that client as holder, with its two ledger accounts (§4.2). Does not create a user |
| **Rejections** | No permission; nonexistent email; the user does not have role `CLIENT`; the user is inactive |

### Rules shared by the operations

They apply to deposits, withdrawals and transfers (§8.5–8.7 and §8.10–8.12):

- The `amount` is a `Decimal` greater than zero with at most 2 decimals.
- The account (or accounts) must exist.
- Before computing balances, the rows of the involved accounts are locked (see §10).
- Movements are recorded according to the table in §5 and the invariants of §6 are validated before persisting.
- The response includes the `id` of the created transaction.

### 8.5 Deposit (client)

| | |
|---|---|
| **Run by** | Client |
| **Required permission** | `DEPOSIT:OWN` |
| **Input** | `account_id`, `amount` |
| **Effect** | `DEPOSIT` transaction: debit to the debit account, credit to the credit account |
| **Rejections** | No permission; the account is not the client's; invalid amount |

### 8.6 Withdrawal (client)

| | |
|---|---|
| **Run by** | Client |
| **Required permission** | `WITHDRAW:OWN` |
| **Input** | `account_id`, `amount` |
| **Effect** | `WITHDRAWAL` transaction: debit to the credit account, credit to the debit account |
| **Rejections** | No permission; the account is not the client's; invalid amount; insufficient funds |

### 8.7 Transfer (client)

| | |
|---|---|
| **Run by** | Client |
| **Required permission** | `TRANSFER:OWN`, evaluated on the source account |
| **Input** | `source_account_id`, `destination_account_id`, `amount` |
| **Effect** | `TRANSFER` transaction with 4 movements (§5) |
| **Rejections** | No permission; the source account is not the client's; nonexistent destination; source = destination; invalid amount; insufficient funds |

The destination can be any account of the bank, VOSTRO or NOSTRO.

### 8.8 Balance inquiry (client)

| | |
|---|---|
| **Run by** | Client |
| **Required permission** | `VIEW:OWN` |
| **Input** | `account_id` |
| **Effect** | Returns the account's balance, computed from the movements. Modifies nothing |
| **Rejections** | No permission; the account is not the client's |

### 8.9 Balance inquiry (operator)

| | |
|---|---|
| **Run by** | Operator (or admin) |
| **Required permission** | `VIEW:VOSTRO` or `VIEW:NOSTRO`, depending on the account's class |
| **Input** | `account_id` |
| **Effect** | Returns the balance of any account, VOSTRO or NOSTRO. Modifies nothing |
| **Rejections** | No permission; nonexistent account |

### 8.10 Deposit (NOSTRO)

| | |
|---|---|
| **Run by** | Operator (or admin) |
| **Required permission** | `DEPOSIT:NOSTRO` |
| **Input** | `account_id`, `amount` |
| **Effect** | `DEPOSIT` transaction on the NOSTRO account |
| **Rejections** | No permission; the account is not NOSTRO; invalid amount |

### 8.11 Withdrawal (NOSTRO)

| | |
|---|---|
| **Run by** | Operator (or admin) |
| **Required permission** | `WITHDRAW:NOSTRO` |
| **Input** | `account_id`, `amount` |
| **Effect** | `WITHDRAWAL` transaction on the NOSTRO account |
| **Rejections** | No permission; the account is not NOSTRO; invalid amount; insufficient funds |

### 8.12 Transfer (NOSTRO)

| | |
|---|---|
| **Run by** | Operator (or admin) |
| **Required permission** | `TRANSFER:NOSTRO`, evaluated on the source account |
| **Input** | `source_account_id`, `destination_account_id`, `amount` |
| **Effect** | `TRANSFER` transaction with 4 movements (§5) from a NOSTRO account |
| **Rejections** | No permission; source is not NOSTRO; nonexistent destination; source = destination; invalid amount; insufficient funds |

The destination can be any account of the bank, NOSTRO or VOSTRO. Since the permission is evaluated only on the source account, the operator can credit a VOSTRO account through a transfer from NOSTRO, even though they cannot deposit to, withdraw from or transfer from it.

### 8.13 Account opening (NOSTRO)

| | |
|---|---|
| **Run by** | Operator (or admin) |
| **Required permission** | `OPEN_ACCOUNT:NOSTRO` |
| **Input** | *Pending* (see §11) |
| **Effect** | Creates a NOSTRO account, with a null `holder_id` and a zero balance, with its two ledger accounts (§4.2). Its holder is the bank's name |
| **Rejections** | No permission |

### 8.14 User deactivation

| | |
|---|---|
| **Run by** | Admin |
| **Required permission** | `MANAGE_USERS` |
| **Input** | The user's `email` |
| **Effect** | Sets `active = false` on the user, whether admin, operator or client. They can no longer authenticate and their valid tokens stop working (§7) |
| **Rejections** | No permission; nonexistent email; the user is already inactive; it is the only active admin (§7) |

An admin can deactivate themselves if another active admin remains. A deactivated client's accounts are kept with their balance and keep receiving transfers. There is no reactivation or role change: those use cases do not apply.

### 8.15 Reversal

| | |
|---|---|
| **Run by** | Admin |
| **Required permission** | `REVERSE` on the scope of each account of the original transaction |
| **Input** | `transaction_id` of the transaction to reverse |
| **Effect** | `REVERSAL` transaction that references the original (`original_transaction_id`) and repeats its movements with the opposite entry type: 2 if it was a deposit or withdrawal, 4 if it was a transfer |
| **Rejections** | No permission; nonexistent transaction; the transaction is a reversal; it was already reversed; insufficient funds |

- A reversal is always for the full amount; there are no partial reversals.
- A transaction is reversed only once, and a reversal cannot be reversed.
- The invariants of §6 apply as well. If reversing would leave an account with a negative balance (the money from a deposit or from a received transfer has already left the account), the reversal is rejected.
- The accounts of the original transaction are locked, as in §10.

### API routes

Every route receives and returns JSON. Except where marked, they require `Authorization: Bearer <token>`.

| Method | Route | Service | Permission |
|---|---|---|---|
| POST | `/user/login` | Login (§7) | No token |
| GET | `/user/` | List of every user | `MANAGE_USERS` |
| GET | `/user/<user_id>` | A user's profile | Own profile: any user¹; any other: `MANAGE_USERS` |
| POST | `/user/password` | Password change (§7) | Any user¹ |
| POST | `/user/admin` | Admin signup (§8.1) | `MANAGE_USERS` |
| POST | `/user/operator` | Operator signup (§8.2) | `MANAGE_USERS` |
| POST | `/user/deactivate` | User deactivation (§8.14) | `MANAGE_USERS` |
| GET | `/account/` | List of every account with its holder and current balance | `VIEW:VOSTRO` and `VIEW:NOSTRO` |
| POST | `/account/client` | Client signup (§8.3) | `OPEN_ACCOUNT:VOSTRO` |
| POST | `/account/vostro` | Account opening (§8.4) | `OPEN_ACCOUNT:VOSTRO` |
| POST | `/account/nostro` | Account opening (NOSTRO) (§8.13) | `OPEN_ACCOUNT:NOSTRO` |
| POST | `/account/<account_id>/deposit` | Deposit (§8.5, §8.10) | `DEPOSIT` on the account's scope |
| POST | `/account/<account_id>/withdrawal` | Withdrawal (§8.6, §8.11) | `WITHDRAW` on the account's scope |
| POST | `/account/<account_id>/transfer` | Transfer (§8.7, §8.12); the account in the path is the source | `TRANSFER` on the source's scope |
| GET | `/account/<account_id>/balance` | Balance inquiry (§8.8, §8.9) | `VIEW` on the account's scope |
| POST | `/account/transaction/<transaction_id>/reversal` | Reversal (§8.15) | `REVERSE` on the scope of each account of the transaction |

¹ Allowed while `must_change_password` is `true`.

Bodies and responses:

| Route | Body | Response |
|---|---|---|
| `POST /user/login` | `email`, `password` | 200: `token`, `must_change_password` |
| `GET /user/` | — | 200: `users`, oldest to newest, each one with the profile fields |
| `GET /user/<user_id>` | — | 200: profile fields |
| `POST /user/password` | `current_password`, `new_password` | 200: `must_change_password: false` |
| `POST /user/admin`, `/user/operator` | `email`, `password` | 201: `id`, `email`, `role`, `active`, `must_change_password` |
| `POST /user/deactivate` | `email` | 200: `id`, `email`, `role`, `active: false`, `must_change_password` |
| `GET /account/` | — | 200: `accounts`, each one with the opening fields plus `balance` |
| `POST /account/client` | `email`, `password`, `name`, `alias` | 201: opening fields |
| `POST /account/vostro` | `email` (of the client), `alias` | 201: opening fields |
| `POST /account/nostro` | `alias` | 201: opening fields |
| `POST /account/<account_id>/deposit`, `/withdrawal` | `amount` | 201: operation fields |
| `POST /account/<account_id>/transfer` | `destination_account_id`, `amount` | 201: operation fields |
| `GET /account/<account_id>/balance` | — | 200: `account_id`, `account_class`, `alias`, `movements` |
| `POST /account/transaction/<transaction_id>/reversal` | — | 201: `transaction_id`, `type` (`REVERSAL`), `original_transaction_id`, `original_type`, `amount`, `accounts`, `created_at` |

- **Profile fields:** `id`, `email`, `name`, `role`, `active`, `must_change_password`, `created_at`. Never the password hash.
- **Opening fields:** `id`, `account_class`, `alias`, `holder`, `holder_id`, `created_at`. In NOSTRO accounts, `holder` is the bank's name and `holder_id` is null.
- **Operation fields:** `transaction_id`, `type`, `amount`, `account_id`, `destination_account_id` (null except in transfers), `balance` (that of `account_id` after the operation), `created_at`.
- **Movements:** oldest to newest. Each one carries `movement_id`, `transaction_id`, `type`, `entry_type`, `amount`, `balance` (the account's balance after that movement) and `created_at`. There is no overall balance: the current one is the last movement's.
- **Reversal accounts:** one `account_id`, `balance` entry per account of the original transaction, with its balance after the reversal.
- `amount` is accepted as text or as a JSON number. Amounts and balances are returned as text with 2 decimals (`"100.50"`), never as float. Dates are ISO 8601.

Errors are returned as `{"error": "..."}`:

| Code | When |
|---|---|
| 400 | Missing field, invalid amount, nonexistent account or transaction, insufficient funds, duplicate email or alias, any other business rule rejection |
| 401 | Missing, invalid or expired token; invalid credentials |
| 403 | Missing permission, or the user still has to change their password |

## 9. Persistence (proposal)

> Initial proposal; review before implementing.

### RBAC schema

Roles and permissions live in the database. Each user has a single role.

There are **exactly three roles**: `CLIENT`, `OPERATOR` and `ADMIN`.

The RBAC is a **fixed seed**:

- Roles, permissions and `role_permissions` are loaded when the schema is created.
- There is no endpoint to create, edit or delete roles, permissions or assignments.
- Changing the permission matrix requires changing the seed.
- The only thing managed at runtime is which role each user has and whether they are active.

**`roles`**

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `name` | text | unique: `CLIENT`, `OPERATOR`, `ADMIN` |
| `description` | text | optional |

**`permissions`**

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `action` | enum `VIEW` / `DEPOSIT` / `WITHDRAW` / `TRANSFER` / `OPEN_ACCOUNT` / `REVERSE` / `MANAGE_USERS` | |
| `scope` | enum `OWN` / `VOSTRO` / `NOSTRO` | null only for `MANAGE_USERS` |

Constraints:

- `UNIQUE NULLS NOT DISTINCT (action, scope)` (PostgreSQL 15+), so permissions without a scope are not duplicated.
- `CHECK ((action = 'MANAGE_USERS' AND scope IS NULL) OR (action <> 'MANAGE_USERS' AND scope IS NOT NULL))`.
- `CHECK (action <> 'OPEN_ACCOUNT' OR scope <> 'OWN')`: opening accounts does not apply to the `OWN` scope.

**`role_permissions`**

| Column | Type | Notes |
|---|---|---|
| `role_id` | UUID | FK → `roles`, `ON DELETE CASCADE` |
| `permission_id` | UUID | FK → `permissions`, `ON DELETE CASCADE` |

Composite PK: `(role_id, permission_id)`.

**`users`**

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `email` | text | unique |
| `password_hash` | text | never the plain-text password |
| `role_id` | UUID | FK → `roles`, required |
| `active` | boolean | default `true`; an inactive user cannot authenticate |
| `must_change_password` | boolean | default `false`; `true` for newly signed-up clients |
| `created_at` | timestamptz | |

**`ledgers`**

What the API calls an account (§4.2).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK. It is the `account_id` of the API |
| `account_class` | enum `NOSTRO` / `VOSTRO` | |
| `alias` | text | required |
| `holder_id` | UUID | FK → `users`. Required if VOSTRO, null if NOSTRO |
| `created_at` | timestamptz | |

Constraints:

- `CHECK ((account_class = 'VOSTRO' AND holder_id IS NOT NULL) OR (account_class = 'NOSTRO' AND holder_id IS NULL))`.
- `UNIQUE NULLS NOT DISTINCT (holder_id, alias)`: the alias is unique per holder, and among the NOSTRO accounts.

The bank's name is not stored on each NOSTRO account: it is the same for all of them and comes from configuration.

The rule "the holder of a VOSTRO account must have role `CLIENT`" cannot be expressed with a `CHECK`; it is validated in the account opening use case.

### Seed data

The seed loads the roles and permissions:

| Role | Permissions |
|---|---|
| `CLIENT` | `VIEW:OWN`, `DEPOSIT:OWN`, `WITHDRAW:OWN`, `TRANSFER:OWN` |
| `OPERATOR` | `VIEW:NOSTRO`, `DEPOSIT:NOSTRO`, `WITHDRAW:NOSTRO`, `TRANSFER:NOSTRO`, `OPEN_ACCOUNT:NOSTRO`, `VIEW:VOSTRO`, `OPEN_ACCOUNT:VOSTRO` |
| `ADMIN` | `VIEW`, `DEPOSIT`, `WITHDRAW`, `TRANSFER`, `REVERSE` on `VOSTRO` and `NOSTRO`; `OPEN_ACCOUNT:VOSTRO`, `OPEN_ACCOUNT:NOSTRO`; `MANAGE_USERS` |

The admin does not need the `OWN` permissions: they hold no accounts, and `VOSTRO` already covers any client account.

### Accounting schema

**`accounts`**

The two ledger accounts of each ledger (§4.2).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `ledger_id` | UUID | FK → `ledgers` |
| `nature` | enum `CREDIT` / `DEBIT` | |

Constraint: `UNIQUE (ledger_id, nature)`, one ledger account of each nature per ledger.

**`transactions`**

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `type` | enum `DEPOSIT` / `WITHDRAWAL` / `TRANSFER` / `REVERSAL` | |
| `original_transaction_id` | UUID | FK → `transactions`, unique. Required if `REVERSAL`, null for the other types |
| `description` | text | optional |
| `created_at` | timestamptz | |

**`movements`**

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `transaction_id` | UUID | FK → `transactions` |
| `account_id` | UUID | FK → `accounts`: a ledger account |
| `entry_type` | enum `DEBIT` / `CREDIT` | |
| `amount` | `NUMERIC(18,2)` | `CHECK (amount > 0)` |
| `created_at` | timestamptz | |

## 10. Concurrency

Since the balance is computed from movements, two concurrent operations on the same account could pass the funds validation at the same time. To prevent it:

- Inside the DB transaction, lock the `ledgers` rows of the involved accounts with `SELECT ... FOR UPDATE` before computing balances. A ledger's lock covers its two ledger accounts, which never move without it.
- In transfers, lock both accounts **always in the same order** (by `id`) to avoid deadlocks.

## 11. Pending

- [x] Services: all NOSTRO accounts have the same holder (the bank). Do they carry an alias to tell them apart (for example "Capital", "Fees")? That would be the input of §8.13 and an `alias` column in `accounts`.
- [x] Services: the admin has permissions to operate VOSTRO accounts, but there is no service for that. Is one added, or does the admin not operate client accounts in practice?
- [x] Services: does the balance inquiry include the list of movements, or is the movement inquiry a separate service?
- [x] Services: login and password change are missing (needed because of `must_change_password`). Are they added?
- [x] Services: are there services to deactivate users or change their role?
- [x] API endpoints (routes, payloads, responses, error codes).
- [x] Account opening: required holder data.
- [x] Reversals: whether they are implemented as a transaction with its own type that references the original.
