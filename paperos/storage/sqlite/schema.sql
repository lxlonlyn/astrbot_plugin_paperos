PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    canonical_title TEXT NOT NULL,
    title_norm TEXT NOT NULL,
    abstract TEXT,
    year INTEGER,
    venue TEXT,
    publisher TEXT,
    source TEXT,
    citation_count INTEGER,
    current_version_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_papers_title_norm ON papers(title_norm);
CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);

CREATE TABLE IF NOT EXISTS paper_identifiers (
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    scheme TEXT NOT NULL,
    value TEXT NOT NULL,
    source TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (scheme, value)
);

CREATE INDEX IF NOT EXISTS idx_paper_identifiers_paper_id ON paper_identifiers(paper_id);

CREATE TABLE IF NOT EXISTS paper_aliases (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    alias_norm TEXT NOT NULL,
    alias_type TEXT NOT NULL DEFAULT 'title',
    source TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(paper_id, alias_norm, alias_type)
);

CREATE INDEX IF NOT EXISTS idx_paper_aliases_norm ON paper_aliases(alias_norm);

CREATE TABLE IF NOT EXISTS objects (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    storage_key TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    mime_type TEXT,
    suffix TEXT,
    created_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_objects_sha256 ON objects(sha256);
CREATE INDEX IF NOT EXISTS idx_objects_kind ON objects(kind);

CREATE TABLE IF NOT EXISTS paper_versions (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    version_label TEXT,
    source TEXT,
    source_url TEXT,
    fulltext_status TEXT,
    object_id TEXT REFERENCES objects(id) ON DELETE SET NULL,
    published_at TEXT,
    discovered_at TEXT NOT NULL,
    is_current INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_paper_versions_paper_id ON paper_versions(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_versions_object_id ON paper_versions(object_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_paper_versions_one_current
    ON paper_versions(paper_id)
    WHERE is_current = 1;

CREATE TABLE IF NOT EXISTS paper_object_links (
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    object_id TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (paper_id, object_id, role)
);

CREATE TABLE IF NOT EXISTS fulltext_locations (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    version_id TEXT REFERENCES paper_versions(id) ON DELETE CASCADE,
    object_id TEXT REFERENCES objects(id) ON DELETE SET NULL,
    url TEXT NOT NULL,
    final_url TEXT,
    source TEXT,
    kind TEXT,
    status TEXT,
    license TEXT,
    version TEXT,
    host_type TEXT,
    confidence REAL,
    reason TEXT,
    filename TEXT,
    sha256 TEXT,
    size_bytes INTEGER,
    content_type TEXT,
    page_count INTEGER,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE(paper_id, url)
);

CREATE INDEX IF NOT EXISTS idx_fulltext_locations_paper_id ON fulltext_locations(paper_id);
CREATE INDEX IF NOT EXISTS idx_fulltext_locations_status ON fulltext_locations(status);
CREATE INDEX IF NOT EXISTS idx_fulltext_locations_object_id ON fulltext_locations(object_id);

CREATE TABLE IF NOT EXISTS paper_ingest_events (
    id TEXT PRIMARY KEY,
    paper_id TEXT REFERENCES papers(id) ON DELETE SET NULL,
    source_query TEXT,
    decision TEXT,
    message TEXT,
    candidate_score REAL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_jobs (
    id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    dedupe_key TEXT,
    paper_id TEXT REFERENCES papers(id) ON DELETE CASCADE,
    version_id TEXT REFERENCES paper_versions(id) ON DELETE CASCADE,
    object_id TEXT REFERENCES objects(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending',
    priority INTEGER NOT NULL DEFAULT 100,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    available_at TEXT NOT NULL,
    locked_by TEXT,
    locked_at TEXT,
    heartbeat_at TEXT,
    timeout_seconds INTEGER NOT NULL DEFAULT 600,
    started_at TEXT,
    finished_at TEXT,
    error_message TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(job_type, dedupe_key)
);

CREATE INDEX IF NOT EXISTS idx_paper_jobs_ready
    ON paper_jobs(status, available_at, priority, created_at);
CREATE INDEX IF NOT EXISTS idx_paper_jobs_paper_id ON paper_jobs(paper_id);

CREATE TABLE IF NOT EXISTS parser_runs (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    version_id TEXT REFERENCES paper_versions(id) ON DELETE SET NULL,
    object_id TEXT REFERENCES objects(id) ON DELETE SET NULL,
    parser_name TEXT NOT NULL,
    parser_version TEXT,
    status TEXT NOT NULL,
    raw_output_object_id TEXT REFERENCES objects(id) ON DELETE SET NULL,
    normalized_object_id TEXT REFERENCES objects(id) ON DELETE SET NULL,
    message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_parser_runs_paper_id ON parser_runs(paper_id);
CREATE INDEX IF NOT EXISTS idx_parser_runs_object_id ON parser_runs(object_id);
CREATE INDEX IF NOT EXISTS idx_parser_runs_status ON parser_runs(status);

CREATE TABLE IF NOT EXISTS document_sections (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    parser_run_id TEXT NOT NULL REFERENCES parser_runs(id) ON DELETE CASCADE,
    parent_section_id TEXT REFERENCES document_sections(id) ON DELETE SET NULL,
    title TEXT,
    level INTEGER NOT NULL DEFAULT 0,
    order_index INTEGER NOT NULL,
    page_start INTEGER,
    page_end INTEGER
);

CREATE INDEX IF NOT EXISTS idx_document_sections_paper_id ON document_sections(paper_id);
CREATE INDEX IF NOT EXISTS idx_document_sections_parser_run_id ON document_sections(parser_run_id);

CREATE TABLE IF NOT EXISTS document_blocks (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    parser_run_id TEXT NOT NULL REFERENCES parser_runs(id) ON DELETE CASCADE,
    section_id TEXT REFERENCES document_sections(id) ON DELETE SET NULL,
    block_index INTEGER NOT NULL,
    block_type TEXT NOT NULL,
    text TEXT,
    page_start INTEGER,
    page_end INTEGER,
    coords_json TEXT NOT NULL DEFAULT '{}',
    content_hash TEXT,
    UNIQUE(parser_run_id, block_index)
);

CREATE INDEX IF NOT EXISTS idx_document_blocks_paper_id ON document_blocks(paper_id);
CREATE INDEX IF NOT EXISTS idx_document_blocks_parser_run_id ON document_blocks(parser_run_id);
CREATE INDEX IF NOT EXISTS idx_document_blocks_section_id ON document_blocks(section_id);
CREATE INDEX IF NOT EXISTS idx_document_blocks_content_hash ON document_blocks(content_hash);

CREATE TABLE IF NOT EXISTS extracted_assets (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    parser_run_id TEXT NOT NULL REFERENCES parser_runs(id) ON DELETE CASCADE,
    asset_type TEXT NOT NULL,
    label TEXT,
    caption TEXT,
    page INTEGER,
    coords_json TEXT NOT NULL DEFAULT '{}',
    object_id TEXT REFERENCES objects(id) ON DELETE SET NULL,
    text_object_id TEXT REFERENCES objects(id) ON DELETE SET NULL,
    linked_block_id TEXT REFERENCES document_blocks(id) ON DELETE SET NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_extracted_assets_paper_id ON extracted_assets(paper_id);
CREATE INDEX IF NOT EXISTS idx_extracted_assets_parser_run_id ON extracted_assets(parser_run_id);
CREATE INDEX IF NOT EXISTS idx_extracted_assets_type ON extracted_assets(asset_type);

CREATE TABLE IF NOT EXISTS paper_references (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    parser_run_id TEXT NOT NULL REFERENCES parser_runs(id) ON DELETE CASCADE,
    ref_key TEXT,
    raw_text TEXT NOT NULL,
    title TEXT,
    authors_json TEXT NOT NULL DEFAULT '[]',
    year INTEGER,
    venue TEXT,
    doi TEXT,
    arxiv_id TEXT,
    resolved_paper_id TEXT REFERENCES papers(id) ON DELETE SET NULL,
    confidence REAL
);

CREATE INDEX IF NOT EXISTS idx_paper_references_paper_id ON paper_references(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_references_parser_run_id ON paper_references(parser_run_id);
CREATE INDEX IF NOT EXISTS idx_paper_references_doi ON paper_references(doi);
CREATE INDEX IF NOT EXISTS idx_paper_references_arxiv_id ON paper_references(arxiv_id);

CREATE TABLE IF NOT EXISTS paper_chunks (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    version_id TEXT REFERENCES paper_versions(id) ON DELETE CASCADE,
    object_id TEXT REFERENCES objects(id) ON DELETE CASCADE,
    parser_run_id TEXT REFERENCES parser_runs(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chunk_type TEXT NOT NULL DEFAULT 'paragraph',
    section_title TEXT,
    section_path TEXT,
    page_start INTEGER,
    page_end INTEGER,
    text TEXT NOT NULL,
    embedding_text TEXT,
    content_hash TEXT,
    source_block_ids_json TEXT NOT NULL DEFAULT '[]',
    prev_chunk_id TEXT REFERENCES paper_chunks(id) ON DELETE SET NULL,
    next_chunk_id TEXT REFERENCES paper_chunks(id) ON DELETE SET NULL,
    token_count INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(paper_id, version_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_paper_chunks_paper_id ON paper_chunks(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_chunks_parser_run_id ON paper_chunks(parser_run_id);
CREATE INDEX IF NOT EXISTS idx_paper_chunks_content_hash ON paper_chunks(content_hash);

CREATE VIRTUAL TABLE IF NOT EXISTS paper_chunks_fts USING fts5(
    chunk_id UNINDEXED,
    paper_id UNINDEXED,
    title,
    section_title,
    text,
    tokenize = 'unicode61'
);

CREATE TABLE IF NOT EXISTS index_status (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    index_name TEXT NOT NULL,
    status TEXT NOT NULL,
    profile TEXT,
    updated_at TEXT NOT NULL,
    message TEXT,
    UNIQUE(paper_id, index_name, profile)
);
