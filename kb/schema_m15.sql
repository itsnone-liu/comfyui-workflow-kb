-- M15: Expert Solutions + Knowledge Gaps + Research Sessions
-- Design: docs/M15_design.md
-- 总方案: D:\ComfyUI_Workflow_KB_专家方案与动态知识生长.md (§3 §5 §12)
-- 幂等: 全部 IF NOT EXISTS,可重复执行。
-- 注: knowledge_items.kind 为自由文本(无 CHECK),negative_result / external_fact
--     直接可用,无需 ALTER。

CREATE TABLE IF NOT EXISTS expert_solutions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,                        -- hybrid_final / reactor_pure / ...
  version INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'candidate',  -- candidate|validated|expert|superseded|retired
  family TEXT DEFAULT 'face_swap',
  requirements TEXT DEFAULT '',              -- 需求自然语言(检索用)
  capabilities_json TEXT DEFAULT '[]',       -- L2 词表: identity_transfer / expression_preserve / ...
  route_json TEXT DEFAULT '[]',              -- ROUTE_CHAINS 形状的 steps,orchestrator 可直接回放
  workflow_ref TEXT DEFAULT '',              -- data/api_format/*.json 或 runninghub:<id>
  applicable_conditions TEXT DEFAULT '',
  limitations TEXT DEFAULT '',
  key_params_json TEXT DEFAULT '{}',         -- 已实测的参数杠杆(api_mods 形状)
  metrics_json TEXT DEFAULT '{}',            -- 指标+输入语境(跨输入不可直接比,方差>=0.063)
  cost_json TEXT DEFAULT '{}',               -- coins / 耗时
  success_cases_json TEXT DEFAULT '[]',
  failure_cases_json TEXT DEFAULT '[]',
  evidence_exp_ids_json TEXT DEFAULT '[]',   -- 关联 experiments.id
  evidence_note TEXT DEFAULT '',             -- M8 终榜 / verified_result 条目等文字证据
  source TEXT DEFAULT 'agent_composed',      -- agent_composed|human|community
  success_count INTEGER DEFAULT 0,           -- 真实任务成功次数(晋升记账)
  reuse_count INTEGER DEFAULT 0,             -- 命中复用次数(编译缓存命中率的分子)
  distinct_inputs_json TEXT DEFAULT '[]',    -- 输入指纹去重(candidate->validated 门槛)
  superseded_by INTEGER,                     -- 新版本 expert_solutions.id
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now')),
  UNIQUE(name, version)
);
CREATE INDEX IF NOT EXISTS idx_sol_status ON expert_solutions(status);
CREATE INDEX IF NOT EXISTS idx_sol_family ON expert_solutions(family);

CREATE TABLE IF NOT EXISTS knowledge_gaps (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  trigger_task_id TEXT DEFAULT '',           -- data/webtasks/<id> 或 ''(历史任务)
  trigger_note TEXT DEFAULT '',
  known_failures_json TEXT DEFAULT '[]',     -- [{what, why, evidence}]
  required_effects_json TEXT DEFAULT '{}',   -- {effect: high|medium|low}
  status TEXT NOT NULL DEFAULT 'open',       -- open|researching|resolved|wont_fix
  resolved_solution_id INTEGER,              -- expert_solutions.id
  resolution_note TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_gap_status ON knowledge_gaps(status);

CREATE TABLE IF NOT EXISTS research_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  gap_id INTEGER,                            -- knowledge_gaps.id(可空:自主探索)
  objective TEXT DEFAULT '',
  sources_json TEXT DEFAULT '[]',            -- github|registry|huggingface|web|bilibili|civitai
  queries_json TEXT DEFAULT '[]',
  funnel_stage TEXT DEFAULT 'collected',     -- collected|shortlisted|deep_read|mechanism|implemented|closed
  candidates_json TEXT DEFAULT '[]',         -- ~20 原始命中 {url,title,source,score}
  shortlist_json TEXT DEFAULT '[]',          -- ~5 元数据初筛后
  findings_json TEXT DEFAULT '[]',           -- 深读笔记 / external_fact 引用
  outcome TEXT DEFAULT 'pending',            -- mechanism_found|operator_found|no_hit|pending
  operator_ref TEXT DEFAULT '',              -- 填补缺口的 node/package/model
  exp_id INTEGER,                            -- 验证实验 experiments.id
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_rs_gap ON research_sessions(gap_id);
CREATE INDEX IF NOT EXISTS idx_rs_stage ON research_sessions(funnel_stage);
