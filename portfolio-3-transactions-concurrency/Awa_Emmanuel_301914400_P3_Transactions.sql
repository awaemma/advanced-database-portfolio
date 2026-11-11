-- Demo 1: a transfer that commits (7328253919 to 5399728535, 5,000.00)
-- Balances before
SELECT account_number, balance FROM account_balance WHERE account_number IN ('7328253919', '5399728535');

-- Transfer
BEGIN;
INSERT INTO session_registry VALUES ('777000000000000000000000000001', 'intrabank');
INSERT INTO intrabank_transfer (session_id, sender_account, destination_account, channel_id, amount, narration, status, posted_at, response_message)
VALUES ('777000000000000000000000000001', '7328253919', '5399728535', (SELECT channel_id FROM channel WHERE channel_code = 'MOB'), 5000.00, 'Demo transfer', 'success', now(), 'Transaction is successful');
INSERT INTO ledger_entry (account_number, intrabank_transfer_id, direction, amount)
SELECT '7328253919', intrabank_transfer_id, 'debit', 5000.00 FROM intrabank_transfer WHERE session_id = '777000000000000000000000000001';
INSERT INTO ledger_entry (account_number, intrabank_transfer_id, direction, amount)
SELECT '5399728535', intrabank_transfer_id, 'credit', 5000.00 FROM intrabank_transfer WHERE session_id = '777000000000000000000000000001';
COMMIT;

-- Balances after
SELECT account_number, balance FROM account_balance WHERE account_number IN ('7328253919', '5399728535');

-- Demo 2: a transfer that fails halfway and is rolled back (5503326610 to 9874690636, 3,000.00)
-- The credit entry has an invalid direction, so the last insert fails
BEGIN;
INSERT INTO session_registry VALUES ('777000000000000000000000000002', 'intrabank');
INSERT INTO intrabank_transfer (session_id, sender_account, destination_account, channel_id, amount, narration, status, posted_at, response_message)
VALUES ('777000000000000000000000000002', '5503326610', '9874690636', (SELECT channel_id FROM channel WHERE channel_code = 'MOB'), 3000.00, 'Demo transfer', 'success', now(), 'Transaction is successful');
INSERT INTO ledger_entry (account_number, intrabank_transfer_id, direction, amount)
SELECT '5503326610', intrabank_transfer_id, 'debit', 3000.00 FROM intrabank_transfer WHERE session_id = '777000000000000000000000000002';
INSERT INTO ledger_entry (account_number, intrabank_transfer_id, direction, amount)
SELECT '9874690636', intrabank_transfer_id, 'refund', 3000.00 FROM intrabank_transfer WHERE session_id = '777000000000000000000000000002';

-- After the error
ROLLBACK;

-- Check that nothing was kept
SELECT (SELECT balance FROM account_balance WHERE account_number = '5503326610') AS sender_balance,
       (SELECT balance FROM account_balance WHERE account_number = '9874690636') AS destination_balance,
       (SELECT count(*) FROM session_registry WHERE session_id = '777000000000000000000000000002') AS registry_rows,
       (SELECT count(*) FROM intrabank_transfer WHERE session_id = '777000000000000000000000000002') AS transfer_rows;

-- Demo 3: two sessions overdraw one account under READ COMMITTED (4132204106, two withdrawals of 15,000.00)
-- Session A, step 1
BEGIN;
SHOW transaction_isolation;

-- Session A, step 2: A sees enough money
SELECT account_number, balance FROM account_balance WHERE account_number IN ('4132204106');

-- Session B, step 1: B checks, withdraws and commits
BEGIN;
SELECT account_number, balance FROM account_balance WHERE account_number IN ('4132204106');
INSERT INTO session_registry VALUES ('777000000000000000000000000003', 'outward');
INSERT INTO outward_transfer (session_id, sender_account, destination_account, beneficiary_name, channel_id, institution_id, amount, narration, status, posted_at, response_message)
VALUES ('777000000000000000000000000003', '4132204106', '0123456789', 'Demo Beneficiary', (SELECT channel_id FROM channel WHERE channel_code = 'MOB'), (SELECT min(institution_id) FROM external_institution), 15000.00, 'Demo withdrawal', 'success', now(), 'Transaction is successful');
INSERT INTO ledger_entry (account_number, outward_transfer_id, direction, amount)
SELECT '4132204106', outward_transfer_id, 'debit', 15000.00 FROM outward_transfer WHERE session_id = '777000000000000000000000000003';
COMMIT;

-- Session B, step 2
SELECT account_number, balance FROM account_balance WHERE account_number IN ('4132204106');

-- Session A, step 3: A acts on the balance it saw earlier
INSERT INTO session_registry VALUES ('777000000000000000000000000004', 'outward');
INSERT INTO outward_transfer (session_id, sender_account, destination_account, beneficiary_name, channel_id, institution_id, amount, narration, status, posted_at, response_message)
VALUES ('777000000000000000000000000004', '4132204106', '0123456789', 'Demo Beneficiary', (SELECT channel_id FROM channel WHERE channel_code = 'MOB'), (SELECT min(institution_id) FROM external_institution), 15000.00, 'Demo withdrawal', 'success', now(), 'Transaction is successful');
INSERT INTO ledger_entry (account_number, outward_transfer_id, direction, amount)
SELECT '4132204106', outward_transfer_id, 'debit', 15000.00 FROM outward_transfer WHERE session_id = '777000000000000000000000000004';
SELECT account_number, balance FROM account_balance WHERE account_number IN ('4132204106');

-- Session A, step 4: undo A's withdrawal so the data stays valid
ROLLBACK;
SELECT account_number, balance FROM account_balance WHERE account_number IN ('4132204106');

-- Demo 4: the same race with a lock (1606196817, two withdrawals of 15,000.00)
-- Session A, step 1: A locks the account row and checks the balance
BEGIN;
SELECT account_number FROM account WHERE account_number = '1606196817' FOR UPDATE;
SELECT account_number, balance FROM account_balance WHERE account_number IN ('1606196817');

-- Session B, step 1: B asks for the same lock and has to wait
BEGIN;
SELECT account_number FROM account WHERE account_number = '1606196817' FOR UPDATE;

-- Session A, step 2: A withdraws and commits, which releases the lock
INSERT INTO session_registry VALUES ('777000000000000000000000000005', 'outward');
INSERT INTO outward_transfer (session_id, sender_account, destination_account, beneficiary_name, channel_id, institution_id, amount, narration, status, posted_at, response_message)
VALUES ('777000000000000000000000000005', '1606196817', '0123456789', 'Demo Beneficiary', (SELECT channel_id FROM channel WHERE channel_code = 'MOB'), (SELECT min(institution_id) FROM external_institution), 15000.00, 'Demo withdrawal', 'success', now(), 'Transaction is successful');
INSERT INTO ledger_entry (account_number, outward_transfer_id, direction, amount)
SELECT '1606196817', outward_transfer_id, 'debit', 15000.00 FROM outward_transfer WHERE session_id = '777000000000000000000000000005';
COMMIT;

-- Session B, step 2: B now sees the new balance and stops
SELECT account_number, balance FROM account_balance WHERE account_number IN ('1606196817');

-- Session B, step 3
ROLLBACK;
SELECT account_number, balance FROM account_balance WHERE account_number IN ('1606196817');

-- Demo 5: isolation, REPEATABLE READ
-- Session A, step 1
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT count(*) AS audit_events FROM audit_event;

-- Session B: adds an audit event and commits
INSERT INTO audit_event (event_type, severity, details) VALUES ('new_device', 'low', 'Isolation demo');

-- Session A, step 2: the count has not changed inside A's transaction
SELECT count(*) AS audit_events FROM audit_event;

-- Session A, step 3: after the commit A sees the new row
COMMIT;
SELECT count(*) AS audit_events FROM audit_event;
