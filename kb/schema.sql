-- ComfyUI Workflow Knowledge Base schema (SQLite)
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS workflows (
  id TEXT PRIMARY KEY,                -- <source>:<source_id>
  source TEXT NOT NULL,               -- runninghub / local / future
  source_id TEXT NOT NULL,
  creation_id TEXT DEFAULT '',
  title TEXT,
  author TEXT,
  tags_json TEXT DEFAULT '[]',
  platform_stats_json TEXT DEFAULT '{}',  -- likeCount/useCount/downloadCount
  url TEXT DEFAULT '',
  downloaded_at TEXT,
  raw_dir TEXT,
  status TEXT DEFAULT 'collected',    -- collected|parsed|analyzed
  node_count INTEGER DEFAULT 0,
  link_count INTEGER DEFAULT 0,
  structure_hash TEXT DEFAULT '',
  techniques_json TEXT DEFAULT '[]',
  assets_json TEXT DEFAULT '[]',
  graph_path TEXT DEFAULT '',
  card_path TEXT DEFAULT '',
  UNIQUE(source, source_id)
);

CREATE INDEX IF NOT EXISTS idx_wf_hash ON workflows(structure_hash);
CREATE INDEX IF NOT EXISTS idx_wf_status ON workflows(status);

CREATE TABLE IF NOT EXISTS knowledge_cards (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
  card_version INTEGER DEFAULT 1,
  model_name TEXT DEFAULT '',          -- LLM that produced it
  domain_json TEXT DEFAULT '[]',
  capabilities_json TEXT DEFAULT '[]',
  core_techniques_json TEXT DEFAULT '[]',
  special_features_json TEXT DEFAULT '[]',
  input_json TEXT DEFAULT '{}',
  output_json DEFAULT '{}',
  design_intent TEXT DEFAULT '',
  use_case TEXT DEFAULT '',
  limitation TEXT DEFAULT '',
  parameter_knowledge_json TEXT DEFAULT '[]',
  dependencies_json TEXT DEFAULT '[]',
  geek_rating INTEGER DEFAULT 0,       -- 0-5 unconventional-structure score
  summary_text TEXT DEFAULT '',        -- concat for embedding/search
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_card_wf ON knowledge_cards(workflow_id);

CREATE TABLE IF NOT EXISTS knowledge_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  card_id INTEGER NOT NULL REFERENCES knowledge_cards(id) ON DELETE CASCADE,
  workflow_id TEXT NOT NULL,
  kind TEXT NOT NULL,                  -- fact|inference|hypothesis|verified_result
  content TEXT NOT NULL,
  evidence TEXT DEFAULT '',            -- e.g. node ids / experiment id
  confidence REAL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS idx_items_card ON knowledge_items(card_id);
CREATE INDEX IF NOT EXISTS idx_items_kind ON knowledge_items(kind);

CREATE TABLE IF NOT EXISTS experiments (   -- M5 cloud experiment engine
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
  hypothesis TEXT DEFAULT '',
  config_json TEXT DEFAULT '{}',
  metrics_json TEXT DEFAULT '{}',
  verdict TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now')),
  name TEXT DEFAULT '',
  status TEXT DEFAULT 'planned',       -- planned|dry-run|running|done|partial
  outputs_dir TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS patterns (     -- M6 placeholder
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  category TEXT DEFAULT '',
  signature_json TEXT DEFAULT '{}',
  example_workflow_ids_json TEXT DEFAULT '[]',
  notes TEXT DEFAULT ''
);
