-- SafeLedger PostgreSQL schema.  Run once:  python seed_postgres.py   (it executes this file)
-- Safe to re-run: every statement is IF NOT EXISTS / OR REPLACE.

-- ---------------------------------------------------------------- master data
CREATE TABLE IF NOT EXISTS accounts (
    account_id      INT    PRIMARY KEY,
    holder_name     TEXT   NOT NULL,
    account_type    TEXT   NOT NULL CHECK (account_type IN ('customer', 'merchant', 'fee')),
    opening_balance BIGINT NOT NULL CHECK (opening_balance >= 0)
);

-- ------------------------------------------------- the dataset (train / test / ...)
-- One row per named slice of transfer requests.  split decides how the slice is used.
CREATE TABLE IF NOT EXISTS workloads (
    workload_id SERIAL      PRIMARY KEY,
    name        TEXT        NOT NULL UNIQUE,            -- e.g. 'train-101'
    seed        INT         NOT NULL UNIQUE,            -- the key make_specs(n, seed) looks up
    split       TEXT        NOT NULL CHECK (split IN ('train', 'test', 'benchmark', 'sweep', 'selftest')),
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Each row becomes one client thread in run_load().  fee is optional (3-account transfer).
CREATE TABLE IF NOT EXISTS transfer_requests (
    workload_id INT      NOT NULL REFERENCES workloads(workload_id) ON DELETE CASCADE,
    tid         INT      NOT NULL,                      -- order inside the workload
    src_account INT      NOT NULL REFERENCES accounts(account_id),
    dst_account INT      NOT NULL REFERENCES accounts(account_id),
    amount      INT      NOT NULL CHECK (amount > 0),
    fee         INT      NOT NULL DEFAULT 0 CHECK (fee >= 0),
    fee_account INT      REFERENCES accounts(account_id),
    priority    SMALLINT NOT NULL CHECK (priority BETWEEN 1 AND 3),
    PRIMARY KEY (workload_id, tid),
    CHECK (src_account <> dst_account),
    CHECK ((fee = 0 AND fee_account IS NULL) OR (fee > 0 AND fee_account IS NOT NULL))
);

-- --------------------------------------------------------------- one row per run
CREATE TABLE IF NOT EXISTS runs (
    run_id          BIGSERIAL   PRIMARY KEY,
    workload_id     INT         REFERENCES workloads(workload_id) ON DELETE SET NULL,
    purpose         TEXT        NOT NULL CHECK (purpose IN ('train', 'test', 'benchmark', 'sweep', 'selftest', 'adhoc')),
    mode            TEXT        NOT NULL,               -- naive | wfg | ordered | banker | wfg+ml | banker+ml
    workers         INT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    txns INT, committed INT, failed INT, retries INT, deadlocks INT, timeouts INT,
    banker_waits INT, ml_delays INT, ml_fallbacks INT,
    wall_s REAL, tps REAL, p50_ms REAL, p95_ms REAL, cpu_ms_per_txn REAL,
    money_conserved BOOLEAN
);

-- ------------------------------------- live bank for one run (replaces SQLite DB)
CREATE TABLE IF NOT EXISTS bank_state (
    run_id     BIGINT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    account_id INT    NOT NULL REFERENCES accounts(account_id),
    balance    BIGINT NOT NULL CHECK (balance >= 0),
    PRIMARY KEY (run_id, account_id)
);

CREATE TABLE IF NOT EXISTS txn_log (
    log_id BIGSERIAL   PRIMARY KEY,
    run_id BIGINT      NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    tid    INT         NOT NULL,
    ts     TIMESTAMPTZ NOT NULL DEFAULT now(),
    detail TEXT
);
CREATE INDEX IF NOT EXISTS txn_log_run_idx ON txn_log(run_id);

-- ---------------------------- ML telemetry: one row per lock attempt (RF data)
CREATE TABLE IF NOT EXISTS lock_events (
    event_id                 BIGSERIAL PRIMARY KEY,
    run_id                   BIGINT   NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    tid                      INT      NOT NULL,
    attempt                  SMALLINT NOT NULL,          -- 0 = first try, 1.. = retries
    -- the five model features (measured BEFORE the transfer asks for its locks)
    locks_held_on_target     SMALLINT NOT NULL,
    wait_queue_length        SMALLINT NOT NULL,
    account_contention_count SMALLINT NOT NULL,
    wait_time_ms             REAL     NOT NULL,
    priority                 SMALLINT NOT NULL,
    -- outcome (known only AFTER the attempt; never a feature)
    outcome                  TEXT     NOT NULL CHECK (outcome IN ('COMMIT', 'TIMEOUT', 'DEADLOCK_VICTIM', 'REJECTED')),
    label                    SMALLINT NOT NULL CHECK (label IN (0, 1))   -- 1 = attempt aborted
);
CREATE INDEX IF NOT EXISTS lock_events_run_idx ON lock_events(run_id);

-- The Random Forest reads its data from these two views.
CREATE OR REPLACE VIEW v_train_set AS
    SELECT e.event_id, e.run_id, e.tid, e.attempt,
           e.locks_held_on_target, e.wait_queue_length, e.account_contention_count,
           e.wait_time_ms, e.priority, e.outcome, e.label
    FROM lock_events e JOIN runs r USING (run_id) WHERE r.purpose = 'train';

CREATE OR REPLACE VIEW v_test_set AS
    SELECT e.event_id, e.run_id, e.tid, e.attempt,
           e.locks_held_on_target, e.wait_queue_length, e.account_contention_count,
           e.wait_time_ms, e.priority, e.outcome, e.label
    FROM lock_events e JOIN runs r USING (run_id) WHERE r.purpose = 'test';

-- ------------------------------------------------------------- trained models
CREATE TABLE IF NOT EXISTS model_registry (
    model_id            SERIAL      PRIMARY KEY,
    trained_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    train_rows          INT,
    test_rows           INT,
    positive_share_test REAL,
    precision_score     REAL,
    recall_score        REAL,
    f1_score            REAL,
    roc_auc             REAL,
    false_positive_rate REAL,
    predict_ms_per_call REAL,
    confusion_matrix    JSONB,
    feature_importance  JSONB,
    artifact_path       TEXT
);

-- ====================================================================
-- Security tables used by dbms.py (users, roles, audit log)
-- ====================================================================
CREATE TABLE IF NOT EXISTS roles (
    role_name TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_name  TEXT NOT NULL REFERENCES roles(role_name) ON DELETE CASCADE,
    permission TEXT NOT NULL,                     -- transfer:own, transfer:any, view:own, view:any, audit:read, backup, restore, checkpoint
    PRIMARY KEY (role_name, permission)
);

-- Passwords are never stored: only a random salt and the PBKDF2-HMAC-SHA256 hash.
CREATE TABLE IF NOT EXISTS app_users (
    username          TEXT        PRIMARY KEY,
    role_name         TEXT        NOT NULL REFERENCES roles(role_name),
    password_salt     BYTEA       NOT NULL,
    password_hash     BYTEA       NOT NULL,
    pbkdf2_iterations INT         NOT NULL,
    failed_attempts   INT         NOT NULL DEFAULT 0,
    locked_until      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Which accounts a customer may move money from (ownership check).
CREATE TABLE IF NOT EXISTS user_accounts (
    username   TEXT NOT NULL REFERENCES app_users(username) ON DELETE CASCADE,
    account_id INT  NOT NULL REFERENCES accounts(account_id),
    PRIMARY KEY (username, account_id)
);

-- Tamper-evident audit log: each entry stores the hash of the previous entry of the same chain.
-- One chain per Bank directory. ts is epoch seconds (DOUBLE PRECISION) so the hash can be recomputed exactly.
CREATE TABLE IF NOT EXISTS audit_log (
    chain      TEXT             NOT NULL,
    seq        BIGINT           NOT NULL,
    ts         DOUBLE PRECISION NOT NULL,
    username   TEXT             NOT NULL,          -- no foreign key: entries must outlive the user
    action     TEXT             NOT NULL,
    detail     TEXT             NOT NULL,
    result     TEXT             NOT NULL,
    prev_hash  CHAR(64)         NOT NULL,
    entry_hash CHAR(64)         NOT NULL,
    PRIMARY KEY (chain, seq)
);

-- Append-only enforced by the database itself (the hash chain still catches anyone who bypasses this).
CREATE OR REPLACE FUNCTION audit_log_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only (% not allowed)', TG_OP;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_log_no_change ON audit_log;
CREATE TRIGGER audit_log_no_change BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_append_only();

DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log;
CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION audit_log_append_only();
