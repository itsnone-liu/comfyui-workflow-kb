-- M18-P1/P2: Task Threads + User Hypotheses + Thread Summaries
-- Design: docs/M18_design.md §3 (P1: 线程一等对象; P2: 假设管线+四栏总结)
-- 事件不建表: data/threads/*.json 持久化(设计 §3 "不建的表")
-- 幂等: 全部 IF NOT EXISTS。

CREATE TABLE IF NOT EXISTS task_threads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key TEXT NOT NULL,                    -- 稳定 slug: h3-fl2v-arc / video-transition
  goal TEXT NOT NULL,                   -- 原始目标表述
  real_need TEXT DEFAULT '',            -- 协商后的真实需求(随理解更新)
  constraints_json TEXT DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'open',  -- open|running|negotiating|closed
  summary_id INTEGER,                   -- thread_summaries.id(收口后)
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now')),
  UNIQUE(key)
);
CREATE INDEX IF NOT EXISTS idx_thread_status ON task_threads(status);

CREATE TABLE IF NOT EXISTS user_hypotheses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_key TEXT DEFAULT '',           -- task_threads.key
  source TEXT DEFAULT 'feedback',       -- feedback|ruling|replay|direct
  source_ref TEXT DEFAULT '',           -- ruling_id / task_id / 反馈原文摘要
  statement TEXT NOT NULL,              -- "不如用首帧图做文生视频"
  status TEXT NOT NULL DEFAULT 'proposed',
    -- proposed(已记录) -> prechecked(零币预检完成) -> awaiting_coin(待用户花币确认)
    -- -> testing -> verified | rejected
  precheck_json TEXT DEFAULT '{}',      -- 零币预检结果(定律/规则/负结果命中+理由)
  verify_plan_json TEXT DEFAULT '{}',   -- 验证计划 {kind, route, cost_coins}
  verify_task_ids_json TEXT DEFAULT '[]',
  outcome_note TEXT DEFAULT '',         -- 验证结论人话版
  decision_rule_code TEXT DEFAULT '',   -- verified 升格的 decision_rules.code
  attribution TEXT DEFAULT '',          -- 署名(用户假设->验证)
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_hyp_status ON user_hypotheses(status);
CREATE INDEX IF NOT EXISTS idx_hyp_thread ON user_hypotheses(thread_key);

CREATE TABLE IF NOT EXISTS thread_summaries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_key TEXT NOT NULL,
  facts_json TEXT NOT NULL DEFAULT '[]',        -- 四栏: 实测事实
  laws_json TEXT NOT NULL DEFAULT '[]',         -- 四栏: 定律(含新草拟)
  rules_json TEXT NOT NULL DEFAULT '[]',        -- 四栏: 规则(含升格)
  open_questions_json TEXT NOT NULL DEFAULT '[]', -- 四栏: 开放问题
  status TEXT NOT NULL DEFAULT 'draft',         -- draft->confirmed
  drafted_by TEXT DEFAULT 'llm',
  kb_item_ids_json TEXT DEFAULT '[]',           -- 确认后回写 knowledge_items 的 id
  confirmed_at TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tsum_thread ON thread_summaries(thread_key);
