CREATE TABLE account_credentials (
    account_id VARCHAR(10) PRIMARY KEY,
    pin INTEGER NOT NULL,
    FOREIGN KEY (account_id)
        REFERENCES accounts(account_id)
        ON DELETE CASCADE
);

INSERT INTO account_credentials (account_id, pin)
SELECT account_id, 9000 + SUBSTRING(account_id FROM 2)::INTEGER
FROM accounts;
