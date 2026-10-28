-- Production Cloud SQL for PostgreSQL DDL (pgvector + temporal claim state transitions)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS marts;

CREATE TABLE IF NOT EXISTS core.resolved_legal_entities (
    resolved_entity_id VARCHAR(32) PRIMARY KEY,
    canonical_patent_code VARCHAR(32) NOT NULL,
    patent_family_id VARCHAR(32) NOT NULL,
    canonical_assignee_name TEXT NOT NULL,
    canonical_law_firm TEXT NOT NULL,
    practice_area VARCHAR(64) NOT NULL,
    claim_element_num VARCHAR(16) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS core.temporal_claim_positions (
    mention_id VARCHAR(32) PRIMARY KEY,
    resolved_entity_id VARCHAR(32) NOT NULL REFERENCES core.resolved_legal_entities(resolved_entity_id),
    doc_id VARCHAR(32) NOT NULL,
    venue VARCHAR(64) NOT NULL,
    filing_date DATE NOT NULL,
    scope_reading VARCHAR(64) NOT NULL,
    claim_status VARCHAR(64) NOT NULL,
    stated_exposure_usd BIGINT NOT NULL,
    verified_exposure_usd BIGINT NOT NULL,
    is_cross_venue_contradiction BOOLEAN NOT NULL DEFAULT FALSE,
    is_superseded BOOLEAN NOT NULL DEFAULT FALSE,
    file_name TEXT NOT NULL,
    file_sha256 CHAR(64) NOT NULL,
    page_number INT NOT NULL,
    line_number INT NOT NULL,
    verbatim_quote TEXT NOT NULL,
    passage_embedding vector(768)
);

CREATE INDEX IF NOT EXISTS idx_claim_positions_entity_date
    ON core.temporal_claim_positions (resolved_entity_id, filing_date);
