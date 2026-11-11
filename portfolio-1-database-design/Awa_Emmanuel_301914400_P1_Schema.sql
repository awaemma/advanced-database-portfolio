-- Veracore MFB schema (PostgreSQL)

CREATE TABLE customer (
    customer_id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title          varchar(10),
    first_name     varchar(60)  NOT NULL,
    last_name      varchar(60)  NOT NULL,
    date_of_birth  date         NOT NULL,
    gender         varchar(6)   NOT NULL CHECK (gender IN ('male', 'female')),
    phone          varchar(15)  NOT NULL UNIQUE,
    email          varchar(120),
    bvn            char(11)     CHECK (bvn ~ '^[0-9]{11}$'),
    kyc_tier       smallint     NOT NULL CHECK (kyc_tier IN (1, 2, 3)),
    registered_on  date         NOT NULL DEFAULT current_date,
    street         varchar(150) NOT NULL,
    city           varchar(60)  NOT NULL,
    lga            varchar(60)  NOT NULL,
    state          varchar(30)  NOT NULL
);

CREATE TABLE account (
    account_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id     bigint      NOT NULL REFERENCES customer (customer_id),
    account_number  char(10)    NOT NULL UNIQUE CHECK (account_number ~ '^[0-9]{10}$'),
    account_type    varchar(10) NOT NULL CHECK (account_type IN ('wallet', 'savings')),
    status          varchar(10) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'frozen', 'closed')),
    opened_on       date        NOT NULL DEFAULT current_date,
    closed_on       date,
    CHECK ((status = 'closed') = (closed_on IS NOT NULL))
);

CREATE TABLE audit_event (
    event_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id  bigint REFERENCES customer (customer_id),
    event_type   varchar(40) NOT NULL,
    severity     varchar(10) NOT NULL,
    occurred_at  timestamptz NOT NULL DEFAULT now(),
    ip_address   inet,
    details      text
);

CREATE TABLE channel (
    channel_id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    channel_code  varchar(10) NOT NULL UNIQUE,
    channel_name  varchar(40) NOT NULL
);

CREATE TABLE external_institution (
    institution_id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    institution_code  varchar(10) NOT NULL UNIQUE,
    institution_name  varchar(80) NOT NULL
);

CREATE TABLE session_registry (
    session_id     char(30)    PRIMARY KEY CHECK (session_id ~ '^[0-9]{30}$'),
    transfer_type  varchar(10) NOT NULL CHECK (transfer_type IN ('intrabank', 'inward', 'outward'))
);

CREATE TABLE intrabank_transfer (
    intrabank_transfer_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id              char(30)      NOT NULL UNIQUE REFERENCES session_registry (session_id),
    source_account_id       bigint        NOT NULL REFERENCES account (account_id),
    destination_account_id  bigint        NOT NULL REFERENCES account (account_id),
    channel_id              bigint        NOT NULL REFERENCES channel (channel_id),
    amount                  numeric(18,2) NOT NULL CHECK (amount > 0),
    narration               varchar(140),
    status                  varchar(10)   NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'success', 'failed', 'reversed')),
    created_at              timestamptz   NOT NULL DEFAULT now(),
    posted_at               timestamptz,
    response_message        varchar(200),
    reversed_at             timestamptz,
    reversal_reason         varchar(200),
    CHECK (source_account_id <> destination_account_id),
    CHECK (status <> 'success' OR response_message = 'Transaction is successful'),
    CHECK ((status = 'reversed' AND reversed_at IS NOT NULL AND reversal_reason IS NOT NULL)
        OR (status <> 'reversed' AND reversed_at IS NULL AND reversal_reason IS NULL))
);

CREATE TABLE outward_transfer (
    outward_transfer_id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id                   char(30)      NOT NULL UNIQUE REFERENCES session_registry (session_id),
    debited_account_id           bigint        NOT NULL REFERENCES account (account_id),
    channel_id                   bigint        NOT NULL REFERENCES channel (channel_id),
    institution_id               bigint        NOT NULL REFERENCES external_institution (institution_id),
    beneficiary_name             varchar(120)  NOT NULL,
    beneficiary_account_number   char(10)      NOT NULL CHECK (beneficiary_account_number ~ '^[0-9]{10}$'),
    amount                       numeric(18,2) NOT NULL CHECK (amount > 0),
    narration                    varchar(140),
    status                       varchar(10)   NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'success', 'failed', 'reversed')),
    created_at                   timestamptz   NOT NULL DEFAULT now(),
    posted_at                    timestamptz,
    response_message             varchar(200),
    reversed_at                  timestamptz,
    reversal_reason              varchar(200),
    CHECK (status <> 'success' OR response_message = 'Transaction is successful'),
    CHECK ((status = 'reversed' AND reversed_at IS NOT NULL AND reversal_reason IS NOT NULL)
        OR (status <> 'reversed' AND reversed_at IS NULL AND reversal_reason IS NULL))
);

CREATE TABLE inward_transfer (
    inward_transfer_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id              char(30)      NOT NULL UNIQUE REFERENCES session_registry (session_id),
    credited_account_id     bigint        NOT NULL REFERENCES account (account_id),
    institution_id          bigint        NOT NULL REFERENCES external_institution (institution_id),
    sender_name             varchar(120)  NOT NULL,
    sender_account_number   char(10)      NOT NULL CHECK (sender_account_number ~ '^[0-9]{10}$'),
    amount                  numeric(18,2) NOT NULL CHECK (amount > 0),
    narration               varchar(140),
    status                  varchar(10)   NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'success', 'failed', 'reversed')),
    created_at              timestamptz   NOT NULL DEFAULT now(),
    posted_at               timestamptz,
    response_message        varchar(200),
    reversed_at             timestamptz,
    reversal_reason         varchar(200),
    CHECK (status <> 'success' OR response_message = 'Transaction is successful'),
    CHECK ((status = 'reversed' AND reversed_at IS NOT NULL AND reversal_reason IS NOT NULL)
        OR (status <> 'reversed' AND reversed_at IS NULL AND reversal_reason IS NULL))
);

CREATE TABLE ledger_entry (
    entry_id               bigint GENERATED ALWAYS AS IDENTITY,
    account_id             bigint        NOT NULL REFERENCES account (account_id),
    intrabank_transfer_id  bigint        REFERENCES intrabank_transfer (intrabank_transfer_id),
    outward_transfer_id    bigint        REFERENCES outward_transfer (outward_transfer_id),
    inward_transfer_id     bigint        REFERENCES inward_transfer (inward_transfer_id),
    direction              varchar(6)    NOT NULL CHECK (direction IN ('debit', 'credit')),
    amount                 numeric(18,2) NOT NULL CHECK (amount > 0),
    posted_at              timestamptz   NOT NULL DEFAULT now(),
    entry_kind             varchar(10)   NOT NULL DEFAULT 'original' CHECK (entry_kind IN ('original', 'reversal')),
    PRIMARY KEY (entry_id, posted_at),
    CHECK ((intrabank_transfer_id IS NOT NULL)::int
         + (outward_transfer_id IS NOT NULL)::int
         + (inward_transfer_id IS NOT NULL)::int = 1)
) PARTITION BY RANGE (posted_at);

CREATE TABLE ledger_entry_2026_10 PARTITION OF ledger_entry FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');
CREATE TABLE ledger_entry_2026_11 PARTITION OF ledger_entry FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
CREATE TABLE ledger_entry_2026_12 PARTITION OF ledger_entry FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');
CREATE TABLE ledger_entry_other   PARTITION OF ledger_entry DEFAULT;

-- Balance is derived from the ledger. A reversal posts the opposite direction, so it nets out.
CREATE VIEW account_balance AS
SELECT a.account_id,
       a.account_number,
       COALESCE(SUM(CASE l.direction WHEN 'credit' THEN l.amount ELSE -l.amount END), 0) AS balance
FROM account a
LEFT JOIN ledger_entry l ON l.account_id = a.account_id
GROUP BY a.account_id, a.account_number;

-- Roles
CREATE ROLE veracore_app     NOLOGIN;
CREATE ROLE veracore_ops     NOLOGIN;
CREATE ROLE veracore_auditor NOLOGIN;

GRANT SELECT, INSERT ON customer, account, audit_event, session_registry,
      intrabank_transfer, outward_transfer, inward_transfer, ledger_entry TO veracore_app;
GRANT SELECT ON channel, external_institution, account_balance TO veracore_app;
GRANT UPDATE (status, closed_on) ON account TO veracore_app;
GRANT UPDATE (status, posted_at, response_message, reversed_at, reversal_reason)
      ON intrabank_transfer, outward_transfer, inward_transfer TO veracore_app;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO veracore_ops, veracore_auditor;
GRANT UPDATE (status, closed_on) ON account TO veracore_ops;
GRANT UPDATE (status, posted_at, response_message, reversed_at, reversal_reason)
      ON intrabank_transfer, outward_transfer, inward_transfer TO veracore_ops;
