-- Run this while connected to deadlock_db. Safe to re-run (drops and recreates).
DROP TABLE IF EXISTS lock_events      CASCADE;
DROP TABLE IF EXISTS deadlock_events  CASCADE;
DROP TABLE IF EXISTS transactions     CASCADE;
DROP TABLE IF EXISTS accounts         CASCADE;

CREATE TABLE accounts (
    account_id  VARCHAR(10)   PRIMARY KEY,
    balance     NUMERIC(12,2) NOT NULL CHECK (balance >= 0)
);

CREATE TABLE transactions (
    txn_id      VARCHAR(10)   PRIMARY KEY,
    priority    SMALLINT      NOT NULL CHECK (priority BETWEEN 1 AND 3),
    start_time  TIMESTAMP(3)  NOT NULL,
    end_time    TIMESTAMP(3)  NOT NULL,
    status      VARCHAR(20)   NOT NULL CHECK (status IN ('COMMITTED', 'ABORTED_DEADLOCK')),
    CHECK (end_time >= start_time)
);

-- Ground truth for the label. txns_in_cycle is a Postgres array so you can
-- unnest() it when building the training CSV.
CREATE TABLE deadlock_events (
    deadlock_id    VARCHAR(10)   PRIMARY KEY,
    detected_at    TIMESTAMP(3)  NOT NULL,
    victim_txn_id  VARCHAR(10)   NOT NULL REFERENCES transactions(txn_id),
    txns_in_cycle  VARCHAR(10)[] NOT NULL
);

CREATE TABLE lock_events (
    event_id    INTEGER       PRIMARY KEY,
    txn_id      VARCHAR(10)   NOT NULL REFERENCES transactions(txn_id),
    account_id  VARCHAR(10)   NOT NULL REFERENCES accounts(account_id),
    event_type  VARCHAR(10)   NOT NULL
                CHECK (event_type IN ('REQUESTED','GRANTED','WAITING','RELEASED','ABORTED')),
    event_time  TIMESTAMP(3)  NOT NULL
);

CREATE INDEX idx_lock_events_account_time ON lock_events (account_id, event_time);
CREATE INDEX idx_lock_events_txn          ON lock_events (txn_id);
