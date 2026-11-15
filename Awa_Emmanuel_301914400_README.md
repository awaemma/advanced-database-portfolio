# MIT 8103 Advanced Database Systems Portfolio

Name: Emmanuel Awa

Student ID: 301914400

## Case study

I am using Veracore MFB, a fictional Nigerian digital microfinance bank, as the case study for all five portfolios. The database records customers, accounts, transfers between accounts, and a ledger of every movement of money.

## Portfolio summaries

Each folder has its own README with the full details and a `screenshots/` folder with the evidence. The overall summary is in [Awa_Emmanuel_301914400_FinalSummary.pdf](Awa_Emmanuel_301914400_FinalSummary.pdf).

### Portfolio 1: Database Design and Modelling

[portfolio-1-database-design](portfolio-1-database-design/)

Requirements, an ER diagram, a normalised relational schema and a PostgreSQL implementation. The ledger is partitioned by month, balances come from the `account_balance` view, and three roles limit who can change data. A seed script loads 500 customers, 874 accounts, 100,000 transfers and 155,090 ledger entries, and the load checks found no negative balances or broken ledger pairs. All 19 constraint tests and all 7 access tests gave the expected result.

### Portfolio 2: Query Processing and Optimisation

[portfolio-2-query-optimisation](portfolio-2-query-optimisation/)

Four queries were measured with `EXPLAIN (ANALYZE, BUFFERS)` before and after adding five indexes. The account statement query fell from 160.1 ms to 0.2 ms and the latest-transfers query from 7.5 ms to 0.1 ms. The failed-transfers query improved less, and the highest-volume query did not improve because it reads nearly the whole partition.

### Portfolio 3: Transactions and Concurrency

[portfolio-3-transactions-concurrency](portfolio-3-transactions-concurrency/)

Five demos in two pgAdmin sessions: a transfer that commits, a transfer that fails and rolls back completely, and two concurrent withdrawals. Under `READ COMMITTED` the withdrawals could overdraw an account. A `SELECT ... FOR UPDATE` row lock prevented that. A `REPEATABLE READ` demo showed a transaction keeping its snapshot until it ended.

### Portfolio 4: NoSQL and Advanced Models

[portfolio-4-nosql](portfolio-4-nosql/)

Customers, transfers and audit events were modelled as MongoDB documents and copied from PostgreSQL, while the ledger stays in PostgreSQL as the source of truth. Schema validation rejected all 7 invalid test inserts. Five queries were run with execution plans: indexed lookups were fast, but the debit-volume aggregation scanned the whole collection.

### Portfolio 5: Distributed and Cloud Databases

[portfolio-5-distributed-cloud](portfolio-5-distributed-cloud/)

A three-node MongoDB replica set in Docker replicated a write to a secondary, elected a new primary when the primary was stopped, and caught the old primary up when it rejoined. A backup was restored into a separate database with matching counts. Sharding the transfers on `sender_account, created_at` and a cloud deployment are discussed as designs only.

## Tools

PostgreSQL 18, pgAdmin 4, Python 3.11 (psycopg2, pymongo), and MongoDB in Docker.
