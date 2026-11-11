# Portfolio 3: Transactions and Concurrency

This portfolio uses the Veracore MFB database from Portfolio 1 in PostgreSQL. The demos are in `Awa_Emmanuel_301914400_P3_Transactions.sql`. I ran them in pgAdmin, using one Query Tool tab per session where two sessions were needed. The screenshots are in `screenshots/`.

Every transfer is written as one transaction: a row in `session_registry`, a row in the transfer table, and the ledger entries. Balances are not stored. They are derived from `ledger_entry` through the `account_balance` view, so a transfer is only complete when all its rows are committed together.

## Demo 1: a transfer that commits

I moved 5,000.00 from 7328253919 to 5399728535 as an intrabank transfer. The transaction inserts the registry row, the transfer row, one debit entry and one credit entry, then commits. I read both balances before and after.

| Step | Screenshot |
|---|---|
| Balances before | [CommitBefore](screenshots/Awa_Emmanuel_301914400_P3_CommitBefore.png) |
| Transaction run | [CommitRun](screenshots/Awa_Emmanuel_301914400_P3_CommitRun.png) |
| Balances after | [CommitAfter](screenshots/Awa_Emmanuel_301914400_P3_CommitAfter.png) |

## Demo 2: a transfer that fails and is rolled back

I moved 3,000.00 from 5503326610 to 9874690636. The debit entry inserted normally. The credit entry used the direction `refund`, which the CHECK constraint on `ledger_entry.direction` rejects. After the error I issued `ROLLBACK` and checked the sender and destination balances, the registry row and the transfer row for that session ID.

| Step | Screenshot |
|---|---|
| Constraint error on the credit entry | [RollbackError](screenshots/Awa_Emmanuel_301914400_P3_RollbackError.png) |
| State after rollback | [RollbackAfter](screenshots/Awa_Emmanuel_301914400_P3_RollbackAfter.png) |

The registry row, the transfer row and the debit entry were all undone, even though they had been inserted before the error.

## Isolation level in use

I did not set an isolation level for Demos 1 to 4. `SHOW transaction_isolation` returns the PostgreSQL default, `read committed`: [IsolationLevel](screenshots/Awa_Emmanuel_301914400_P3_IsolationLevel.png).

## Demo 3: concurrent withdrawals under READ COMMITTED

The test uses account 4132204106 and two withdrawals of 15,000.00 as outward transfers. Session A and session B are separate tabs.

1. A begins a transaction and reads the balance. It is enough for a 15,000.00 withdrawal ([OverdraftASees](screenshots/Awa_Emmanuel_301914400_P3_OverdraftASees.png)).
2. B reads the balance, withdraws 15,000.00 and commits ([OverdraftBCommit](screenshots/Awa_Emmanuel_301914400_P3_OverdraftBCommit.png), [OverdraftBAfter](screenshots/Awa_Emmanuel_301914400_P3_OverdraftBAfter.png)).
3. A, still working from the balance it read in step 1, withdraws 15,000.00 as well. A's balance query now shows -8,232.60 ([OverdraftNegative](screenshots/Awa_Emmanuel_301914400_P3_OverdraftNegative.png)).
4. I rolled A back so the data stays valid. The balance returned to 6,767.40 ([OverdraftAfterRollback](screenshots/Awa_Emmanuel_301914400_P3_OverdraftAfterRollback.png)).

Nothing in the schema stops this. A's check and A's insert are separate statements, and under `READ COMMITTED` the row B committed in between does not block A. The balance A checked was out of date by the time A acted on it. This is a lost-check problem on a derived balance, and it would leave a customer overdrawn if A had committed.

## Demo 4: the same race with a row lock

The test uses account 1606196817 and two withdrawals of 15,000.00. Before checking the balance, each session locks the account row with `SELECT ... FOR UPDATE`.

1. A locks the row and reads the balance.
2. B asks for the same lock and waits ([LockBWaiting](screenshots/Awa_Emmanuel_301914400_P3_LockBWaiting.png)).
3. A withdraws 15,000.00 and commits, which releases the lock ([LockACommit](screenshots/Awa_Emmanuel_301914400_P3_LockACommit.png)).
4. B's lock request now returns. B reads the balance again, sees A's withdrawal and does not withdraw ([LockBRecheck](screenshots/Awa_Emmanuel_301914400_P3_LockBRecheck.png)). I rolled B back.
5. The final balance is 6,908.72, so only one withdrawal took effect ([LockFinal](screenshots/Awa_Emmanuel_301914400_P3_LockFinal.png)).

The lock makes the two sessions take turns. The second session checks the balance after the first has finished, so its decision uses current data. The cost is that B waits while A holds the lock. The lock is on one account row, so transfers on other accounts are not affected.

The first screenshot of A taking the lock (LockA1) is not included. It was not valid and I could not recreate it, so Demo 4 is evidenced by the five screenshots above.

## Demo 5: REPEATABLE READ

This demo uses the `audit_event` table. Session A starts a `REPEATABLE READ` transaction and counts the rows. Session B inserts one row and commits. A counts again inside its transaction, then commits and counts a third time.

| Step | Session | Count | Screenshot |
|---|---|---|---|
| A starts `REPEATABLE READ` and counts | A | 2000 | [IsolationA1](screenshots/Awa_Emmanuel_301914400_P3_IsolationA1.png) |
| B inserts one row and commits | B | | [IsolationBInsert](screenshots/Awa_Emmanuel_301914400_P3_IsolationBInsert.png) |
| A counts again, same transaction | A | 2000 | [IsolationA2](screenshots/Awa_Emmanuel_301914400_P3_IsolationA2.png) |
| A commits and counts | A | 2001 | [IsolationA3](screenshots/Awa_Emmanuel_301914400_P3_IsolationA3.png) |

A keeps the snapshot taken at its first query, so it does not see B's committed row until A's transaction ends. In Demo 3, the default `READ COMMITTED` level behaved differently: A's later statements saw the change B had committed (A's balance query returned -8,232.60 instead of the value A saw at the start). The two levels trade off differently. `REPEATABLE READ` gives a stable view for reports and reconciliation. `READ COMMITTED` always reads current data but a decision based on an earlier read can go stale, so for balance checks it needs a lock such as the one in Demo 4.

## Limits

- The demos are manual and use two pgAdmin sessions, not a load test.
- Only `READ COMMITTED` and `REPEATABLE READ` were run. I did not test `SERIALIZABLE`.
- Deadlocks were not tested.
- The overdraft protection in Demo 4 is in the demo SQL, not in the schema. An application that skips the lock can still overdraw an account.
