CREATE TABLE customers (id BIGSERIAL PRIMARY KEY, name VARCHAR(100) NOT NULL, mobile VARCHAR(16) NOT NULL UNIQUE);
CREATE TABLE invoices (id BIGSERIAL PRIMARY KEY, customer_id BIGINT NOT NULL REFERENCES customers(id) ON DELETE CASCADE, invoice_number VARCHAR(50) NOT NULL, invoice_date DATE NOT NULL, amount NUMERIC(12,2) NOT NULL CHECK (amount > 0), currency CHAR(3) NOT NULL, payment_status VARCHAR(16) NOT NULL CHECK (payment_status IN ('paid','unpaid','pending')), CONSTRAINT uq_invoice_customer_number UNIQUE(customer_id,invoice_number));
CREATE INDEX ix_invoices_customer_id ON invoices(customer_id);
CREATE TABLE conversations (id BIGSERIAL PRIMARY KEY, customer_id BIGINT NOT NULL REFERENCES customers(id) ON DELETE CASCADE, title VARCHAR(160) NOT NULL DEFAULT 'New conversation', pending_invoice JSONB, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX ix_conversations_customer_id ON conversations(customer_id);
CREATE TABLE messages (id BIGSERIAL PRIMARY KEY, conversation_id BIGINT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE, role VARCHAR(16) NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX ix_messages_conversation_created ON messages(conversation_id,created_at);
CREATE TABLE otp_challenges (id BIGSERIAL PRIMARY KEY, mobile VARCHAR(16) NOT NULL, code_hash CHAR(64) NOT NULL, expires_at TIMESTAMPTZ NOT NULL, sent_at TIMESTAMPTZ NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, used_at TIMESTAMPTZ);
CREATE INDEX ix_otp_mobile ON otp_challenges(mobile);
