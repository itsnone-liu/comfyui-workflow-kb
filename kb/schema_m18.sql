-- M18-P0: Boundary Laws + Decision Rules (对话式任务闭环的最小切片)
-- Design: docs/M18_design.md §3 (P0 只建两表; task_threads/user_hypotheses/
--         thread_summaries 属 P1/P2, 届时另加 schema_m18_p1.sql)
-- 幂等: 全部 IF NOT EXISTS, 可重复执行。

CREATE TABLE IF NOT EXISTS boundary_laws (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL,                    -- BL-001 (卡片引用短码)
  name TEXT NOT NULL,                    -- 渲染一致律
  statement TEXT NOT NULL,               -- 一句话人话版(卡片"已知风险"行用)
  technical TEXT DEFAULT '',             -- 详细机制版(Why 面板/深读用)
  evidence TEXT DEFAULT '',              -- 实验/条目引用
  applies_to_json TEXT DEFAULT '[]',     -- [{family, facet, condition}]
  alternatives_json TEXT DEFAULT '[]',   -- [{"way": "...", "note": "..."}]
  status TEXT NOT NULL DEFAULT 'law',    -- law|refined|refuted|hypothesis
  attribution TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now')),
  UNIQUE(code)
);

CREATE TABLE IF NOT EXISTS decision_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL,                    -- DR-001
  name TEXT NOT NULL,                    -- 跨空间图对视频转场 -> i2v
  conditions_json TEXT NOT NULL,         -- 任务特征(词法+LLM 分类产出)
                                         -- [{"facet": "task", "op": "is", "val": "video_transition"},
                                         --  {"facet": "image_pair", "val": "cross_space"}]
  route TEXT NOT NULL,                   -- 推荐路线 key (orchestrator ROUTE_CHAINS/可执行名)
  route_label TEXT DEFAULT '',           -- 卡片标题
  what TEXT DEFAULT '',                  -- 卡片行1: 做什么(白话)
  effect_cost TEXT DEFAULT '',           -- 卡片行2: 预期效果与代价
  risk TEXT DEFAULT '',                  -- 卡片行3: 已知风险(人话, 引用 BL 码)
  when_choose TEXT DEFAULT '',           -- 卡片行4: 什么情况下选它
  coins TEXT DEFAULT '',                 -- "~2"
  tone TEXT NOT NULL DEFAULT 'info',     -- recommended|info|caution|dead
  dead_ref TEXT DEFAULT '',              -- negative_result 引用(dead 卡标红依据)
  laws_json TEXT DEFAULT '[]',           -- 引用 boundary_laws.code 列表
  source_kind TEXT DEFAULT 'experiment', -- user_hypothesis|experiment|community|agent
  attribution TEXT DEFAULT '',           -- 规则来源署名
  evidence TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active', -- active|retired
  priority INTEGER DEFAULT 100,          -- 小先出(卡片排序)
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now')),
  UNIQUE(code)
);
CREATE INDEX IF NOT EXISTS idx_dr_route ON decision_rules(route);
CREATE INDEX IF NOT EXISTS idx_dr_status ON decision_rules(status);
