# M15 设计:专家方案层 + 知识缺口(含 M11 三源修订)

> 对齐总方案《ComfyUI_Workflow_KB_专家方案与动态知识生长.md》(D 盘根目录)。
> 原则:**只补两个一等对象(Expert Solution / Knowledge Gap),不推倒任何已完成层**。
> L0(raw)→ L1(patterns)→ L2(cards.capabilities)已就位,M15 只加 L3 和驱动对象。

## 0. 范围映射

| 优先级 | 内容 | 对应总方案章节 |
|---|---|---|
| P0 | `expert_solutions` 表 + orchestrator 方案检索/终态回写 + M8 种子迁移 | §2-3 |
| P1 | `knowledge_gaps` 表 + `negative_result` kind + 失败知识规范化 | §5, §10 |
| P2 | `research_sessions` 表 + M11 三源(GitHub/Registry/HuggingFace) | §7-9, §12 |

## 1. 数据模型(三张新表 + kind 扩展)

`kb/schema_m15.sql`(幂等,IF NOT EXISTS):

- **expert_solutions**:name+version 唯一;status = candidate→validated→expert,superseded 链;
  `route_json` 直接存 ROUTE_CHAINS 形状的 steps(orchestrator 可回放,零翻译);
  metrics/cost/failure_cases/evidence 全留位;`reuse_count`/`distinct_inputs_json` 供晋升记账。
- **knowledge_gaps**:title + trigger_task + known_failures(试过什么、为何失败)+
  required_effects;status = open→researching→resolved/wont_fix;resolved 指回 solution_id。
- **research_sessions**:gap_id + 三源 queries + 漏斗阶段(collected→shortlisted→deep_read→
  mechanism→implemented→closed)+ candidates(20)→shortlist(5)→findings;operator_ref/exp_id
  闭环回指。

**kind 扩展零迁移**:`knowledge_items.kind` 无 CHECK 约束,直接写
`negative_result`(P1)和 `external_fact`(M11),evidence 列链实验/来源。

不建的表(克制清单):operator_contracts、capability 本体论全量形式化、来源价值统计表
(先在 research_sessions 存原始字段,≥20 个 session 后再聚合,避免伪科学)。

## 2. 晋升机制(方差感知)

exp015 已证平台种子极差 0.063、单次差异 <0.05 不可下结论。晋升规则写死:

| 迁移 | 门槛 |
|---|---|
| candidate → validated | **≥2 个不同输入**成功且指标达阈值(指标比较需 ≥3 采样) |
| validated → expert | **≥3 个真实任务**稳定成功 + 失败边界已表征 + 参数杠杆已知 |
| expert 新版 | 旧版 status=superseded + superseded_by 指新版本(参考 exp019 推翻 #735 的教训) |

种子数据按此标注:hybrid_final / reactor_pure = **validated**(M8 多测试对调参 +
1 个真实任务确认 + 支撑实验);其余五路线 = **candidate**。hybrid_final 距 expert
还差 2 个真实任务——正好作为晋升机制的活例。

注意:指标跨输入不可直接比(探针跨人对 instantid_cfg 身份 0.314 vs M8 真实图对
0.673),metrics_json 记录输入语境,evidence_note 注明方差警示。

## 3. 检索与接线(orchestrator)

```python
# plan_task 之前(webapp/orchestrator.py::_run_task)
sol = search_solutions(task.requirement)   # capabilities 硬过滤 + LLM 打分 top-k
if sol and sol["score"] >= THRESHOLD:
    task.plan = {"family": sol["family"], "route": sol["name"], "reused_solution": sol["id"]}
    # 直接回放 route_json(_exec_face_swap 已支持),跳过规划 LLM —— 零规划硬币
else:
    task.plan = plan_task(task)             # 现有规划链

# 终态回写(_run_task 的三个出口)
# satisfied → upsert_solution_run(solution, task):success_count++, 输入指纹去重入
#             distinct_inputs_json,候选晋升检查(达 §2 门槛自动升或提示)
# limited   → 若失败原因是"能力不可达"(而非缺输入/执行错):open_gap(task, ev)
#             known_failures 记本次尝试的路线+指标+诊断规则命中
```

- 第一版检索不上 embedding:capabilities 标签 SQL 硬过滤 + LLM 对 top-k 语义打分,
  够用且可解释。
- **复用率指标从第一天记**:reuse_count / 规划硬币节省 / gap 转化数;
  `data/webtasks/*/task.json` 可回填历史。
- MCP 后续加 `search_solutions` 工具(10→11),协议自测沿用 `mcp/test_server.py`。

**实现落点(2026-08-23,已完成)**:
- `kb/solutions.py`:检索(`search_solutions`/`hit_solution`,capabilities 位置加权
  词法评分,可解释 matched_caps)+ `record_reuse` / `record_success`(输入指纹去重 +
  晋升检查)+ `open_gap`(同题去重,追加 known_failures)。纯 stdlib。
- `webapp/orchestrator.py`:`_pick_solution` 前置(命中→零规划硬币,时间线留痕);
  `_chain_for` 回放 `route_json`(方案可不进 ROUTE_CHAINS 直接执行);`_writeback`
  挂三终态(satisfied→成功记账+晋升;limited 且有能力迭代/kb_no_hit→open_gap;
  缺输入 limited 与 error 不写)。
- `mcp/server.py`:`search_solutions` 工具(11 工具,`mcp/test_server.py` 自测通过)。
- LLM 复排只在词法弱信号(top<2)或并列时触发,失败回退词法序——离线可用。

## 4. 种子数据(migrate_m15.py,幂等)

| name | status | 依据 |
|---|---|---|
| hybrid_final(final_v3) | validated | M8 终榜 0.720/0.049/9/8,用户确认采纳 |
| reactor_pure | validated | 0.741/0.032 双冠;自拼最小流=组合能力证明 |
| klein_double | candidate | 0.621/0.064/8-7;锚定权衡 0/1/2→0.741/0.694/0.599 |
| instantid_cfg | candidate | 0.673/0.084;kps-slot 耦合,嘟嘴丢失 |
| pulid_flux | candidate | 高上限路线,M8 未量化 |
| qwen_swap | candidate | 指令路线,探针中 |
| maskflux | candidate | 探针 0.42-0.47,表情跟参考 |

negative_result 种子(挂到对应 workflow 的 card):
1. instantid_pulid 流探针 805 默认输入即败,勿投币(探针法分界)。
2. SD1.5 CN 接 FLUX conditioning 运行时爆——跨家族段移植必须家族匹配(pose_transfer 教训)。

knowledge_gaps 种子(1 条 open,真实缺口):
- **发型跟参考 + 表情跟底图(非指令路线)**:known_failures = InstantID 族耦合定律 /
  swap_full hair=True 无效 / ReActor 不迁移发型;现仅 qwen_swap 指令路线可能满足。

## 5. M11 修订:三源研究通道(含 HuggingFace)

三源分工互补,不是三个平行搜索:

| 源 | 回答的问题 | 落点 |
|---|---|---|
| GitHub | 有没有**代码/节点**实现这个能力 | operator 发现 → Composer 段移植 |
| ComfyUI Registry(M12) | 这个**节点包**叫什么/版本/依赖 | operator 安装清单、契约 |
| **HuggingFace** | 能力背后的**模型**是什么、机制、license | tech_families 机制知识 + wf_assets 解析 |

HF 定位与边界:
- **模型层定位**,不是又一个泛化搜索源;模型卡即机制富矿,顺带桥接论文(总方案 §7 的
  L4 由模型卡牵引,而非从论文出发)和 GitHub 实现。
- 公开 REST 无需 key(`/api/models?search=...`),`huggingface_hub` 一个依赖,适配器半天。
- license 标签机器可读——专家方案复用的合规约束早晚要自动化。
- downloads/likes 直接喂 20→5 初筛排序,为 §9 来源统计留数据。
- **边界 1**:换脸域权重(inswapper/InsightFace 系)因授权不在 HF,社区靠网盘分发——
  HF 在该域只提供机制卡与论文线索,不是权重源。
- **边界 2**:RH 云端场景下 HF 是元数据源(节点该填哪个模型名),hf_hub_download
  只服务本地 onnx 工具(YuNet/SFace)。
- **边界 3**:卡片质量方差大,digest 时区分官方 org vs 社区上传(author 字段)。

B站/C站仍按 STATUS 原计划"等用户定渠道后扩",不阻塞主线。

## 6. 验收标准

**M15**(2026-08-23 验收,`test_m15_wiring.py` 23 checks 全过,MCP 自测 11 工具):
1. ✅ 7 条种子方案 SQL/CLI/MCP 可检索;route_json 被 `_chain_for` 原样回放(test2);
2. ✅ 换脸任务命中方案直接复用——零规划硬币、时间线留痕、reuse/success 记账
   (离线打桩 e2e;**真实硬币活例待下个真实任务**:hybrid_final 差 2 个真实任务晋升
   expert,正好是晋升机制的活例);
3. ✅ 缺口任务(发型+表情双需求)正确产出 knowledge_gaps(known_failures 带
   路线+指标);缺输入的 limited 不误开 gap(test3);
4. ✅ instantid_pulid 勿投币、跨家族爆点 negative_result 均可检索(test4);
   晋升:candidate→validated(≥2 输入)/ validated→expert(≥3 任务+边界+参数)
   均按规则触发(test5)。

**M11(三源)**:一个 open gap → research_session(gap_id 链)→ GitHub/Registry/HF
三源查询留痕 → 发现 operator/机制 → 实验 → gap.status=resolved + solution 回写,
全链一次。(未启动;M15 已就绪不阻塞)

## 7. 部署与运行

```powershell
cd D:\qjcNetDiskDownload\deepseek-harness\project\820
$env:PYTHONPATH=''
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" kb\migrate_m15.py   # 幂等,可重复跑
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" kb\migrate_m15.py --no-seed   # 只建表
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" test_m15_wiring.py # 接线验收(临时库,不动 kb.db)
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" mcp\test_server.py  # MCP 11 工具自测
```

文件:`kb/schema_m15.sql`(DDL)、`kb/migrate_m15.py`(迁移+种子,纯 stdlib)、
本文档 `docs/M15_design.md`。PLAN.md §8b 已加 M15 行、更新 M11 行;STATUS.md 下一步已记。
