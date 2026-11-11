-- Q1: statement for one account over a date range
SELECT posted_at, direction, amount, entry_kind
FROM ledger_entry
WHERE account_number = (SELECT account_number FROM account WHERE status = 'active' ORDER BY account_id LIMIT 1)
  AND posted_at >= '2026-10-20' AND posted_at < '2026-11-05'
ORDER BY posted_at;

-- Q2: failed transfers by channel and day
SELECT c.channel_name, t.created_at::date AS day, count(*) AS failed_transfers
FROM (SELECT channel_id, created_at FROM intrabank_transfer WHERE status = 'failed'
      UNION ALL
      SELECT channel_id, created_at FROM outward_transfer WHERE status = 'failed') t
JOIN channel c ON c.channel_id = t.channel_id
GROUP BY c.channel_name, t.created_at::date
ORDER BY day, c.channel_name;

-- Q3: ten accounts with the highest original ledger volume, 1 to 10 November
SELECT account_number, count(*) AS entries, sum(amount) AS total
FROM ledger_entry
WHERE posted_at >= '2026-11-01' AND posted_at < '2026-11-11'
  AND entry_kind = 'original'
GROUP BY account_number
ORDER BY total DESC
LIMIT 10;

-- Q4: latest 20 intrabank transfers sent from one account
SELECT created_at, destination_account, amount, status
FROM intrabank_transfer
WHERE sender_account = (SELECT account_number FROM account WHERE status = 'active' ORDER BY account_id LIMIT 1)
ORDER BY created_at DESC
LIMIT 20;

-- Indexes added after the first run
CREATE INDEX idx_ledger_account_posted ON ledger_entry (account_number, posted_at);
CREATE INDEX idx_intrabank_sender_created ON intrabank_transfer (sender_account, created_at DESC);
CREATE INDEX idx_intrabank_failed_created ON intrabank_transfer (created_at) WHERE status = 'failed';
CREATE INDEX idx_outward_failed_created ON outward_transfer (created_at) WHERE status = 'failed';
CREATE INDEX idx_ledger_posted_volume ON ledger_entry (posted_at) INCLUDE (account_number, amount, entry_kind);
