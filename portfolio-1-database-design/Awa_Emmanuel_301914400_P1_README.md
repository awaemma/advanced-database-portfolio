# Portfolio 1 Database Design and Modelling

## Requirements analysis

### Case study

Veracore MFB is a fictional Nigerian microfinance bank that offers Naira wallets and savings accounts through a mobile app, USSD and the web. The database stores customers, their accounts, and three kinds of transfer: intrabank transfers between Veracore accounts, inward transfers from accounts at other banks, and outward transfers to accounts at other banks. Every movement of money is recorded as ledger entries. It also stores the channel a customer used, the other banks, and security events such as failed logins and large transfers. Customer and transaction data is fictional, and other banks appear under their real names.

### Users

Customers open accounts and move money. Customer-support agents look up accounts and transfers. Operations staff handle reversals and frozen accounts. Auditors and compliance officers review the ledger and security events. A scheduled reconciliation job checks balances every day.

### Main operations

Open an account, make an intrabank transfer, receive an inward transfer from another bank, send an outward transfer to another bank, reverse a transfer, view a balance and statement, reconcile balances against the ledger, and record and review security events.

### Functional requirements

| ID | Requirement |
| --- | --- |
| FR1 | Register a customer and record their KYC tier. |
| FR2 | Open, freeze or close an account (wallet or savings) that belongs to a customer. |
| FR3 | Transfer funds between two Veracore accounts as one atomic operation (intrabank). |
| FR4 | Receive an inward transfer from an account at another bank into a Veracore account. |
| FR5 | Send an outward transfer from a Veracore account to an account at another bank. |
| FR6 | Reverse a successful transfer of any type once, without deleting its history. |
| FR7 | Show an account balance and a statement for a date range. |
| FR8 | Reconcile daily: each intrabank transfer nets to zero, each inward or outward transfer matches its single ledger entry, and the total of all balances equals money received from other banks minus money sent to them, after reversals. |
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

1. Each customer has a unique customer ID and a unique phone number.
2. Each account belongs to exactly one customer, a customer can hold several accounts, and each account number is unique.
3. All amounts are in Naira with two decimal places, and every transfer amount is greater than zero.
4. An intrabank transfer's source and destination accounts must differ, and both must be active. An inward or outward transfer must involve an active Veracore account.
5. A customer account's balance must never fall below zero.
6. A successful intrabank transfer creates two ledger entries, a debit and a credit of equal amount, in the same transaction. A successful inward transfer creates one credit entry, and a successful outward transfer creates one debit entry.
7. Ledger entries are never updated or deleted.
8. Each transfer has a 30-digit session ID. A session ID is never used twice across intrabank, inward and outward transfers, so a repeated message cannot post twice.
9. A transfer starts as pending and ends as success or failed. A successful transfer of any type can be reversed once, by posting offsetting ledger entries on the same transfer, and its status then becomes reversed.
10. An account is active, frozen or closed. Only active accounts can be debited or credited, and an account can be closed only when its balance is zero.
11. The response message of a successful transfer is "Transaction is successful". The response message of a failed transfer gives the reason it failed.

### Scope

One institution, one currency (NGN), transfers between Veracore accounts, transfers received from accounts at other Nigerian banks and sent to them, and generated data. Cash deposits and withdrawals, loans, cards, interest, foreign exchange, real identity checks and user login are left out intentionally.

## Conceptual design

The model has ten entities, drawn in two figures. In the diagrams an underlined attribute identifies a record, a dashed ellipse is a derived attribute (calculated, not stored), and an ellipse with further ellipses attached is a composite attribute. Double lines mean every record of that entity must take part in the relationship. Single lines mean taking part is optional.

### Figure 1 Customers, accounts and security events

[![ER diagram for customers, accounts and audit events](screenshots/Awa_Emmanuel_301914400_P1_ERDiagramCustomers.png)](screenshots/Awa_Emmanuel_301914400_P1_ERDiagramCustomers.png)


### Figure 2 Transfers, ledger, channels and other banks

[![ER diagram for transfers, ledger entries, channels and other banks](screenshots/Awa_Emmanuel_301914400_P1_ERDiagramTransfers.png)](screenshots/Awa_Emmanuel_301914400_P1_ERDiagramTransfers.png)


### Entities and attributes

| Entity | Attributes |
| --- | --- |
| Customer | customer_id (key), title, first_name, last_name, date_of_birth, gender, phone, email, bvn, kyc_tier, registered_on, address (street, city, lga, state) |
| Account | account_id (key), account_number (unique), account_type, status, opened_on, closed_on, balance (derived) |
| AuditEvent | event_id (key), event_type, severity, occurred_at, ip_address, details |
| Channel | channel_id (key), channel_code (unique), channel_name |
| ExternalInstitution | institution_id (key), institution_code (unique), institution_name |
| IntrabankTransfer | intrabank_transfer_id (key), session_id, amount, narration, status, created_at, posted_at, response_message, reversal (reversed_at, reversal_reason) |
| InwardTransfer | inward_transfer_id (key), session_id, amount, narration, status, created_at, posted_at, response_message, sender (name, account_number, institution_code), reversal (reversed_at, reversal_reason) |
| OutwardTransfer | outward_transfer_id (key), session_id, amount, narration, status, created_at, posted_at, response_message, beneficiary (name, account_number, institution_code), reversal (reversed_at, reversal_reason) |
| SessionRegistry | session_id (key), transfer_type |
| LedgerEntry | entry_id (key), direction, amount, posted_at, entry_kind |

Gender is male or female, account_type is wallet or savings, account status is active, frozen or closed, transfer status is pending, success, failed or reversed, direction is debit or credit, and entry_kind is original or reversal. A session_id is a 30-digit number, and transfer_type in SessionRegistry is intrabank, inward or outward. Every entity has an id as its key. Account, Channel and ExternalInstitution also keep their business identifiers (account_number, channel_code and institution_code) as unique attributes. Balance is the sum of an account's ledger entries.

### Relationships

| Relationship | Entities | Cardinality | Participation |
| --- | --- | --- | --- |
| owns | Customer, Account | 1 : N | Every account has a customer. A customer may not have an account yet. |
| concerns | AuditEvent, Customer | N : 1 | Optional on both sides: an event may not be linked to a customer. |
| debits, credits | IntrabankTransfer, Account | N : 1 each | Every intrabank transfer has a source account and a destination account. |
| credits | InwardTransfer, Account | N : 1 | Every inward transfer is credited to one Veracore account. |
| debits | OutwardTransfer, Account | N : 1 | Every outward transfer is debited from one Veracore account. |
| received from | InwardTransfer, ExternalInstitution | N : 1 | Every inward transfer comes from one other bank. |
| sent to | OutwardTransfer, ExternalInstitution | N : 1 | Every outward transfer goes to one other bank. |
| made through | IntrabankTransfer or OutwardTransfer, Channel | N : 1 | Every intrabank and outward transfer is made through one channel. Inward transfers arrive from another bank, so they have no channel. |
| registered in | IntrabankTransfer, InwardTransfer or OutwardTransfer, SessionRegistry | 1 : 1 | Every transfer has exactly one registry row holding its session_id, and every registry row belongs to one transfer. SessionRegistry is what makes session_id unique across the three transfer tables, since a UNIQUE rule only works inside one table. |
| records | IntrabankTransfer, InwardTransfer or OutwardTransfer, LedgerEntry | 1 : N | A successful transfer has its ledger entries, plus reversal entries if it is reversed. A pending or failed transfer has none. |
| posts to | LedgerEntry, Account | N : 1 | Every entry affects one account. |

Every ledger entry belongs to exactly one transfer, which is an intrabank, inward or outward transfer. The diagram shows this as three separate links, and it cannot show that only one of them applies. The diagrams show structure only. Rules about values and behaviour, such as rules 4 to 9 and 11, are not drawn on them.


## Logical design

### Relational schema

Each entity became a table with its id as the primary key. Composite attributes became separate columns: address into street, city, lga and state, reversal into reversed_at and reversal_reason, and sender and beneficiary into a name and an account number. Balance is derived, so it is not a column. Each one-to-many relationship became a foreign key on the many side. The sender and beneficiary institution_code from the ER diagram is not repeated in the transfer tables, because institution_id already identifies the bank. A ledger entry holds three optional foreign keys, one per transfer table, and exactly one of them is filled.

[![Relational schema of the Veracore MFB database](screenshots/Awa_Emmanuel_301914400_P1_RelationalSchemaDiagram.png)](screenshots/Awa_Emmanuel_301914400_P1_RelationalSchemaDiagram.png)

| Table | Primary key | Foreign keys | Also unique |
| --- | --- | --- | --- |
| customer | customer_id | none | phone |
| account | account_id | customer_id references customer | account_number |
| audit_event | event_id | customer_id references customer (optional) | none |
| channel | channel_id | none | channel_code |
| external_institution | institution_id | none | institution_code |
| session_registry | session_id | none | none |
| intrabank_transfer | intrabank_transfer_id | session_id references session_registry; source_account_id and destination_account_id reference account; channel_id references channel | session_id |
| outward_transfer | outward_transfer_id | session_id references session_registry; debited_account_id references account; channel_id references channel; institution_id references external_institution | session_id |
| inward_transfer | inward_transfer_id | session_id references session_registry; credited_account_id references account; institution_id references external_institution | session_id |
| ledger_entry | entry_id | account_id references account; intrabank_transfer_id, outward_transfer_id and inward_transfer_id reference their transfer tables (each optional) | none |

### Constraints

Every foreign key is required except the ones marked optional. No foreign key cascades a delete, because transfers and ledger entries are never deleted.

| Table | Constraint | Rule |
| --- | --- | --- |
| customer | phone is required and unique; gender is male or female | 1 |
| account | account_type is wallet or savings; status is active, frozen or closed; closed_on is filled only when status is closed, and always when it is | 2, 10 |
| session_registry | session_id is exactly 30 digits; transfer_type is intrabank, inward or outward | 8 |
| the three transfer tables | amount is greater than zero; status is pending, success, failed or reversed; response_message is "Transaction is successful" when status is success; reversed_at and reversal_reason are filled when status is reversed and empty otherwise | 3, 9, 11 |
| intrabank_transfer | source_account_id and destination_account_id differ | 4 |
| ledger_entry | direction is debit or credit; entry_kind is original or reversal; amount is greater than zero; exactly one of the three transfer ids is filled | 3, 6 |

Some rules involve other rows or other tables, so a column or row check cannot hold them: the active-account condition in rule 4, rule 5, the pairing of debit and credit entries in rule 6, rule 7, the match between transfer_type in the registry and the table that holds the transfer, and the zero-balance condition for closing an account in rule 10.

### Normalisation

I started from a flat report of outward transfers. The values are made up for the example, and the session IDs are shortened.

| session_id | customer_id | customer_name | account_number | account_type | channel_code | channel_name | bank_name | ledger_entries |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T1 | C1 | Ada Okoro | 1000000001 | savings | MOB | Mobile app | Access Bank | debit 25,000.00 |
| T2 | C1 | Ada Okoro | 1000000001 | savings | USSD | USSD | GTBank | debit 10,000.00 |
| T3 | C2 | Tunde Bello | 1000000002 | wallet | MOB | Mobile app | Access Bank | debit 7,500.00; credit 7,500.00 (reversal) |

The dependencies in this data are:

- session_id determines account_number, channel_code and bank_name, since a transfer has one source account, one channel and one bank.
- account_number determines customer_id and account_type.
- customer_id determines customer_name.
- channel_code determines channel_name.

**First normal form.** The ledger_entries cell of T3 holds two values. Each entry gets its own row, numbered within its transfer, so the key becomes session_id with entry_no.

**Second normal form.** direction, amount and entry_kind depend on the whole key. The customer, account, channel and bank columns depend on session_id alone, which is a partial dependency. They move to a transfer table, and the entries stay in their own table.

| session_id | entry_no | direction | amount | entry_kind |
| --- | --- | --- | --- | --- |
| T1 | 1 | debit | 25,000.00 | original |
| T2 | 1 | debit | 10,000.00 | original |
| T3 | 1 | debit | 7,500.00 | original |
| T3 | 2 | credit | 7,500.00 | reversal |

**Third normal form.** In the transfer table, customer_id and account_type depend on account_number, customer_name depends on customer_id, and channel_name depends on channel_code. Each of these depends on a column that is not the key, which is a transitive dependency. The table splits into transfer (session_id, account_number, channel_code, bank_name), account (account_number, customer_id, account_type), customer (customer_id, customer_name) and channel (channel_code, channel_name). Bank details get their own table in the same way.

**Boyce-Codd normal form.** In each of these tables the only determinants are candidate keys. In the final schema, account_id and account_number both identify an account, and session_id and the transfer id both identify a transfer. Either one is a candidate key, so no determinant falls outside a key and the tables are in BCNF.

I checked whether lga determines state in the customer address, which would be a transitive dependency. It does not, because some LGA names exist in more than one state, for example Surulere in Lagos and in Oyo. The address columns stay in customer.

The final schema above is the result. The generated ids replace the business columns as primary keys, and account_number, channel_code and institution_code stay as unique columns. Balance is not stored, so it cannot disagree with the ledger.
