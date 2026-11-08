# Portfolio 1 Database Design and Modelling

## Requirements analysis

### Case study

Veracore MFB is a fictional Nigerian microfinance bank that offers Naira wallets and savings accounts through a mobile app, USSD and the web. The database stores customers, their accounts, transfers between accounts, and the ledger entries that record every movement of money. It also stores the channel each request came through and security events such as failed logins and large transfers. All data in this portfolio is fictional.

### Users

Customers open accounts and move money. Customer-support agents look up accounts and transfers. Operations staff handle reversals and frozen accounts. Auditors and compliance officers review the ledger and security events. A scheduled reconciliation job checks balances every day.

### Main operations

Open an account, deposit, withdraw, transfer between accounts, reverse a transfer, view a balance and statement, reconcile balances against the ledger, and record and review security events.

### Functional requirements

| ID | Requirement |
| --- | --- |
| FR1 | Register a customer and record their KYC tier. |
| FR2 | Open, freeze or close an account (wallet or savings) that belongs to a customer. |
| FR3 | Deposit funds into an account through a channel. |
| FR4 | Withdraw funds, and reject a withdrawal that would overdraw the account. |
| FR5 | Transfer funds between two accounts as one atomic operation. |
| FR6 | Reverse a posted transfer once, without deleting its history. |
| FR7 | Show an account balance and a statement for a date range. |
| FR8 | Reconcile daily: each balance equals the sum of its ledger entries, and each transfer nets to zero. |
| FR9 | Record security events such as failed logins, large transfers and flags. |
| FR10 | Report on activity, for example failed transfers by channel and day, and the accounts with the highest volume. |

### Non-functional requirements

| ID | Requirement |
| --- | --- |
| NFR1 | Integrity: a transfer is applied completely or not at all. |
| NFR2 | Concurrency: simultaneous debits must not overdraw an account or spend the same money twice. |
| NFR3 | Auditability: the ledger is append-only and every change can be traced. |
| NFR4 | Performance: statement and recent-transfer lookups should use indexes on a large ledger. |
| NFR5 | Security: access is split by role (application, operations, read-only auditor). |
| NFR6 | Availability and recovery: the database tolerates the loss of one node and backups can be restored. |
| NFR7 | Scalability: the ledger grows fastest, so it should be possible to partition or shard it by account or date. |

### Business rules

1. Each customer has a unique customer reference and a unique phone number.
2. Each account belongs to exactly one customer, a customer can hold several accounts, and each account number is unique.
3. All amounts are in Naira with two decimal places, and every transfer amount is greater than zero.
4. A transfer's source and destination accounts must differ, and both must be active.
5. A customer account's balance must never fall below zero.
6. Each posted transfer creates exactly two ledger entries, one debit and one credit of equal amount, in the same transaction.
7. Ledger entries are never updated or deleted.
8. Each transfer has a unique idempotency key, and repeating a request with the same key must not post a second transfer.
9. A transfer moves from pending to posted or failed, and from posted to reversed. It can be reversed at most once, through a new transfer that refers to the original.
10. An account is active, frozen or closed. Only active accounts can be debited or credited, and an account can be closed only when its balance is zero.

### Scope

One institution, one currency (NGN), transfers between accounts held at the bank, and generated data. Loans, cards, interest, foreign exchange, interbank transfers, real identity checks and user login are left out.
