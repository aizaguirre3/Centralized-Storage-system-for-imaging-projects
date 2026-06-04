-- ============================================================================
--  Gas Station Renovation — Project Data Model (scoped demo schema)
-- ----------------------------------------------------------------------------
--  This runs on SQLite so the demo is self-contained. Production target is
--  Azure SQL Database. Differences are noted inline as  >> PROD:  comments.
--
--  Design principles on display:
--    * Normalized: each fact stored once, related by foreign keys.
--    * Documents are LINKED, not stored. Every *_path / *_url column points to
--      a file that lives in storage (SharePoint / Blob in prod); the DB holds
--      only the queryable facts about it.
--    * Controlled vocabularies (scope_type, asset_type, status) so natural-
--      language questions resolve reliably and the data stays trustworthy.
-- ============================================================================

PRAGMA foreign_keys = ON;

-- A signed contract is what creates a project, so the two are born together.
CREATE TABLE projects (
    project_id          INTEGER PRIMARY KEY,
    site_name           TEXT NOT NULL,          -- e.g. 'Next Level Petroleum - Warner Robins'
    site_address        TEXT NOT NULL,
    customer_name       TEXT,
    general_contractor  TEXT,
    status              TEXT,                   -- 'planning' | 'active' | 'closed'
    start_date          TEXT                    -- ISO date string  >> PROD: DATE
);

-- Step 1: the signed labor contract.
--  >> CHANGED: signed copy is uploaded MANUALLY (no DocuSign API in the demo).
--  signed_doc_path points to wherever you saved the signed PDF.
CREATE TABLE contracts (
    contract_id     INTEGER PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(project_id),
    customer_name   TEXT,
    labor_amount    REAL,                       -- >> PROD: DECIMAL(12,2)
    status          TEXT,                       -- 'sent' | 'signed' | 'void'
    signed_date     TEXT,
    signed_doc_path TEXT,                       -- manual upload: link to saved signed PDF
    uploaded_by     TEXT                        -- accountability: who uploaded it
);

CREATE TABLE vendors (
    vendor_id           INTEGER PRIMARY KEY,
    name                TEXT NOT NULL,
    material_category   TEXT,                   -- 'canopy_forecourt' | 'signage' | 'bundled'
    contact_email       TEXT
);

-- Step 3: materials quotes. One ROW PER SCOPE even if they arrive in one PDF,
-- so per-scope status works. All rows for one quote share a quote_doc_path.
CREATE TABLE quotes (
    quote_id        INTEGER PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(project_id),
    vendor_id       INTEGER NOT NULL REFERENCES vendors(vendor_id),
    material_scope  TEXT NOT NULL,              -- CONTROLLED: 'canopy_forecourt' | 'signage' | 'main_id'
    amount          REAL,
    received_date   TEXT,
    quote_doc_path  TEXT                         -- saved copy of the emailed quote
);

-- Step 4: orders. status carries the lifecycle; quote_id is the audit link
-- back to the quote it came from ("did we order at what we were quoted?").
CREATE TABLE sales_orders (
    order_id        INTEGER PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(project_id),
    vendor_id       INTEGER NOT NULL REFERENCES vendors(vendor_id),
    quote_id        INTEGER REFERENCES quotes(quote_id),
    material_scope  TEXT NOT NULL,              -- carried through from the quote
    status          TEXT,                       -- 'approved' | 'ordered'
    order_date      TEXT,
    order_doc_path  TEXT
);

-- Step 5: shipping. actual_date filling in = received. Last field we track;
-- scheduling the job is the boss's domain, outside this system boundary.
CREATE TABLE shipments (
    shipment_id     INTEGER PRIMARY KEY,
    order_id        INTEGER NOT NULL REFERENCES sales_orders(order_id),
    expected_date   TEXT,
    actual_date     TEXT,
    received        INTEGER DEFAULT 0           -- 0/1 boolean  >> PROD: BIT
);

-- Step 2: permitting. We MIRROR Monday.com, not replace it. monday_item_url
-- links back to the live card; status mirrors the Monday status column.
CREATE TABLE permits (
    permit_id       INTEGER PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(project_id),
    permit_type     TEXT,
    jurisdiction    TEXT,                       -- 'Houston County', 'Hall County', etc.
    status          TEXT,                       -- mirrors Monday status
    assigned_to     TEXT,                       -- the permit person
    monday_item_url TEXT,
    submitted_date  TEXT
);

-- The permit person's free-text notes, one row per comment.
--  >> PROD: add  embedding VECTOR(1536)  and use Azure SQL native vector search.
--     The demo does semantic search in the app layer over comment_text.
CREATE TABLE permit_updates (
    update_id       INTEGER PRIMARY KEY,
    permit_id       INTEGER NOT NULL REFERENCES permits(permit_id),
    comment_text    TEXT,
    author          TEXT,
    comment_date    TEXT
);

-- The bridge asset: produced by the materials track (the sign vendor),
-- consumed by the permitting track. Its own table = one-to-many (a project
-- has many assets of different types over time). asset_type is CONTROLLED.
CREATE TABLE design_assets (
    asset_id        INTEGER PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(project_id),
    vendor_id       INTEGER REFERENCES vendors(vendor_id),
    quote_id        INTEGER REFERENCES quotes(quote_id),
    asset_type      TEXT,                       -- CONTROLLED: 'main_id_render' | 'canopy_layout' | 'monument_sign'
    asset_url       TEXT,                       -- manual link to saved art
    received_date   TEXT,
    notes           TEXT
);

-- CompanyCam site photos. Link added MANUALLY (low volume, low error cost).
CREATE TABLE site_photos (
    photo_id        INTEGER PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(project_id),
    companycam_url  TEXT,
    caption         TEXT,
    date_added      TEXT
);

-- Declares which scopes each project actually expects, and whether each is
-- permit-gated. Flagged MANUALLY at signing (human judgment, with accountability).
-- This is what makes "none yet" honest: we only report on in-scope work.
CREATE TABLE project_scopes (
    project_scope_id INTEGER PRIMARY KEY,
    project_id       INTEGER NOT NULL REFERENCES projects(project_id),
    scope_type       TEXT NOT NULL,             -- CONTROLLED: 'canopy_forecourt' | 'main_id' | 'signage' | 'options'
    in_scope         INTEGER NOT NULL DEFAULT 0, -- 1 = this work is in the signed contract
    is_permit_gated  INTEGER NOT NULL DEFAULT 0, -- 1 = ordering waits on permit approval
    set_by           TEXT,                      -- who set the flag
    set_date         TEXT,
    UNIQUE (project_id, scope_type)
);
