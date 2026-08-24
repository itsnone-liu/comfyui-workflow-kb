-- M16: 验证/编排域知识宿主 + 用户裁决金标准
-- 原则: 验证环节知识与生成环节同构生长(可检索/可沉淀/可被 M11 更新)

CREATE TABLE IF NOT EXISTS capability_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,            -- generation / verification / orchestration
    topic TEXT NOT NULL,             -- au_thresholds / vl_model_bias / arbitration ...
    content TEXT NOT NULL,
    evidence TEXT,
    confidence REAL DEFAULT 0.7,
    status TEXT DEFAULT 'active',    -- active / superseded / corrected
    supersedes_id INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_capnotes_domain_topic
    ON capability_notes(domain, topic);

-- 用户裁决(金标准)——vl_arbiter 校准环数据源(表由 vl_arbiter.py 自建, 此处兜底)
CREATE TABLE IF NOT EXISTS user_rulings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT, target TEXT, out_a TEXT, out_b TEXT,
    name_a TEXT, name_b TEXT,
    ruling TEXT,                     -- 原文/结构化
    auto_verdict TEXT,               -- 仲裁器当时的自动结论
    created_at TEXT
);
