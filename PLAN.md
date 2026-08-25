# ComfyUI Workflow 知识库 —— 实施方案 v1

> 对齐《ComfyUI_Workflow_智能知识库总体构想》的 Phase 1-7，融合 comfyui-mcp 的设计经验。
> 路线：**先纵后横**——先打通"采集→解析→知识卡→检索"一条线（M1-M3），再做实验验证与组合（M4-M6）。

## 0. 现状与已有资产

| 构想 Phase | 现状 |
|---|---|
| Phase 1 workflow_collector | ✅ **已完成**（`rh_client.py` / `download_workflow.py`，三接口链路实测通：creation/detail → portal/workflow/detail → workflow/copy 直返完整 JSON） |
| Phase 2-7 | 未开始，本方案规划 |

比构想更优的一点：文档设想"复制到自己工作台→官方 API 取 JSON"，实际 `workflow/copy` **一步直返** workflowContent，无需二次查询。

## 1. 总体架构

```text
                    用户自然语言（DSH / 任意 Agent）
                              │
                    ┌─────────▼─────────┐
                    │  kb-mcp (MCP服务器) │   ← 学 comfyui-mcp：工具化接口
                    └─────────┬─────────┘
              search_workflows │ get_card / get_workflow / visualize
                    ┌─────────▼─────────┐
                    │   知识库核心 kb     │
                    │  SQLite + 向量索引  │
                    └─┬───────┬───────┬─┘
              采集层 │  解析层 │  分析层 │
            collector│ parser │analyzer│
              (已完成) │(确定性)│(LLM+置信度)│
                    └───┬─────┴────────┘
                        ▼
                本地 ComfyUI（实验验证，M5 起）
```

## 2. 目录规划（820/）

```text
820/
├── collector/              # M0 已完成，迁入
│   ├── rh_client.py
│   ├── rh_login.py
│   └── download_workflow.py
├── parser/                 # M1
│   ├── normalizer.py       # UI JSON → 标准图（nodes/links/params 分类）
│   └── ui_to_api.py        # UI 格式 → API 格式（学 comfyui-mcp 的 convert）
├── analyzer/               # M2
│   ├── structural.py       # 确定性提取：模型/自定义节点/参数面/子图模式
│   └── llm_card.py         # LLM 生成 Knowledge Card（带置信度标注）
├── kb/                     # M3
│   ├── schema.sql          # SQLite 表结构
│   ├── store.py            # 入库/查询
│   ├── embed.py            # 向量化（卡文本 + 图结构摘要）
│   └── search.py           # 混合检索（结构化字段 + 语义）
├── mcp/                    # M3
│   └── server.py           # MCP 服务器（stdio）
├── experiments/            # M5（预留）
└── data/
    ├── raw/<source>/<id>/  # 原始下载（永不动）
    │   ├── workflow.json / meta.json / api_inputs.json / covers
    ├── graph/<id>.json     # 标准化图
    └── cards/<id>.json     # 知识卡
```

**铁律：raw 目录只增不改**（构想第五章"同时保存原始 JSON，不破坏原始数据"）。

## 3. 数据模型（SQLite，M1 建）

```sql
workflows        -- id, source, source_id, title, author, tags, stats_json,
                 --   downloaded_at, raw_dir, status(parsed/analyzed)
wf_nodes         -- workflow_id, node_id, node_type, category, widget_values
wf_links         -- workflow_id, from_node, from_slot, to_node, to_slot, type
wf_assets        -- 模型/LoRA/ControlNet 清单（从图+元数据双源提取）
knowledge_cards  -- workflow_id, domain[], capabilities[], techniques[],
                 --   special_features[], input, output, params_face,
                 --   deps[], card_version, created_by(llm模型名)
knowledge_items  -- card_id, kind(fact|inference|hypothesis|verified_result),
                 --   content, evidence, confidence
experiments      -- (M5) workflow_id, input_set, metrics_json, verdict
patterns         -- (M6) name, category, signature_subgraph, examples[]
```

### 置信度分级（构想第十章的落地）

| kind | 来源 | 标注方式 |
|---|---|---|
| `fact` | JSON 确定性提取（节点/连线/模型） | 代码生成，不可变 |
| `inference` | LLM 对结构的解读 | 记录所用模型+prompt版本 |
| `hypothesis` | LLM 提出待验证猜测（如"此结构提升一致性"） | M5 实验的目标清单 |
| `verified_result` | 实验引擎实测 | 带实验配置与指标 |

检索时默认 `fact` 权重最高，`inference` 可选过滤——**不能完全相信 AI 的解释**直接变成查询参数。

## 4. Knowledge Card 生成流水线（M2 核心）

```text
workflow.json
   │
   ├─① 确定性提取（不花LLM）
   │    模型清单 / 自定义节点 / 参数面(nodeId.widget 可覆盖槽位)
   │    节点类别统计 / 输入输出边界节点 / 子图模式匹配(PuLID/InstantID/人脸筛选...)
   │         → 全部入库为 fact
   │
   ├─② 结构摘要压缩（把 60KB JSON 压成 ~2KB 文本：
   │    节点类型序列 + 关键连线 + 参数面 + 元数据）
   │
   └─③ LLM 分析（一次调用，结构化输出）
        输入：②摘要 + ①facts + 平台元数据(标题/标签/使用数/作者)
        输出：构想第七、八章的完整知识卡：
          domain / capabilities / core_techniques / special_features /
          input / output / design_intent / use_case / limitation /
          parameter_knowledge / dependencies
        每个字段允许标 kind: fact|inference|hyppothesis
```

③ 的 prompt 里注入 comfyui-mcp 式"节点知识包"（常用节点的功能说明），减少 LLM 瞎猜。设计意图、极客结构识别（构想第九章）主要靠这一步。

## 5. 检索设计（M3）

两级检索，对应构想第四章"按能力检索而非文件名"：

1. **结构化过滤**：SQL 直查 capabilities/domain/techniques/依赖（"找有 PuLID 且带人脸筛选的流"）
2. **语义检索**：知识卡文本 embedding（中文为主）+ 图结构摘要的 embedding，向量库用 **sqlite-vec**（不引入独立服务，SQLite 一把梭，符合构想"第一版不要过度设计"）

返回结果附置信度徽标：`[fact] 该流含 InstantID 节点` vs `[inference] 可能用于多人场景分区重绘`。

## 6. MCP 接口（M3，学 comfyui-mcp 的工具命名）

| 工具 | 说明 |
|---|---|
| `search_workflows` | 能力/领域/技术/语义查询，返回卡摘要列表 |
| `get_knowledge_card` | 完整知识卡（含置信度分级） |
| `get_workflow` | 取原始/标准化/API 格式 JSON（format 参数） |
| `visualize_workflow` | Mermaid 图（节点按类别分色分组，学 comfyui-mcp） |
| `compare_workflows` | 两流结构 diff（节点增删/参数差异） |
| `get_pattern` / `list_patterns` | M6 后启用 |
| `submit_experiment` | M5 后启用 |
| `ingest_workflow` | 传入 RunningHub URL → 走完整流水线入库 |

## 7. 里程碑

| 里程碑 | 内容 | 验收标准 | 状态 |
|---|---|---|---|
| **M0** | collector | 命令行下载完整工作流 | ✅ 完成 |
| **M1** | parser + SQLite store；collector 批量模式（标签抓 N 页） | 50 条入库，图结构可 SQL 查询 | ✅ 完成（92 条入库，80 条解析；**注意：站内 search 参数无效，须走 tag 过滤**） |
| **M2** | analyzer：确定性提取 + LLM 知识卡 | 抽 10 条人工审卡，fact/inference 区分清晰 | ✅ **完成并全覆盖**（168/168 卡，1485 条目：fact 796 / inference 686 / verified_result 3；geek 5★×3 4★×113 3★×38） |
| **M3** | 检索 + MCP server | DSH 里用自然语言查库、看图、取 JSON | ✅ 完成（`mcp/server.py` 5 工具协议自测通过；已注册 DSH web profile `comfyui_kb`，重启 DSH 后生效） |
| **M4** | 批量扩库 + 去重（结构 hash） | ~~500-1000 条盲采~~ → **定向补缺**（覆盖率报告驱动） | ✅ **完成**（92→168 条全解析；三渠道：标签+元数据预过滤 / 整标签深翻页 / webapp 搜索；PuLID 5→16、InstantID 4→20、OpenPose 1→6、BiRefNet 2→11，主技术面全部可用） |
| **M5** | 实验引擎（**RunningHub 云端**，不用本地 ComfyUI）：hypothesis→verified_result | 至少 1 组 A/B 实验闭环 | ✅ **完成**（exp006：PuLID 流 denoise 0.15/0.35 → cosine 0.378/0.329，首条 verified_result #586；正确 API 形态已逆向并实跑验证） |
| **M5+** | 自拼工作流验证回路 | `/task/openapi/create` 接受自拼图 | ✅ **完成**（沙箱机制：workflowId 校验真值 + `workflow` 参数整体覆盖，`.rh_sandbox_wf` 复用；`getJsonApiFormat` 平台级 UI→API 转换） |
| **M6-0** | Pattern 挖掘 | 链/技术 signature/边界挂点入库 | ✅ **完成**（950 patterns；`pattern_miner.py`；`data/patterns_report.md` 覆盖率报告） |
| **M6-1** | Composer 雏形 | 段移植组装 + 云端验证 | ✅ **五配方 + 声明式引擎**（upscale 7808×11776；face_detail 检测器链；batch 恰好 N 张；bg_remove alpha 抠图；pose_transfer 跨源合成+多端口注入；recipes.json spec 表驱动重组装逐一比对一致） |
| **M7** | MiniMax H3 细分专库 | 新细分领域全流程复用（采集→建卡→画像） | ✅ **完成**（`batch_h3.py` 定向 40 条 0 失败；40/40 卡；`data/h3_report.md`：T8 原生 vs RH API 两路线、十任务面、质量-成本-显存知识核心；patterns 950→1245，视频能力 18→58 条） |
| **M8** | 端到端任务实战：换脸管线 | 用户图对→最优结果+全链路机制沉淀 | ✅ **完成**（6 路线 19 预设全实测；最终混合管线 final_v3：ReActor 0.741/0.032 → Klein 单锚 → LAB；两耦合定律+锚定权衡+表情机制入库；`swap_face.py` 一键工具） |
| **M9** | 自主探索机制 v1 | 结果反馈→自动诊断→候选修复（闭环 A） | ✅ **完成**（`auto_explore.py` 接入 run_swap 默认路径；`diagnosis_rules` 6 条+`tech_families` 7 族入库；回放验证自动复现专家诊断路径；VL 语义评审上线） |
| **M10** | Web 前端 + 自主编排后端 | 需求→AI 建流→出图→反馈修订→最终工作流/不可行解释 | ✅ **完成 v1**（`webapp/`：`orchestrator.py` 任务循环[规划LLM→路线选择→RH执行→自动评审→等反馈→修订→终局]，`app.py` REST+图服务 :8830，`static/index.html` 零依赖前端；真实任务端到端验证通过，limited 路径带机制解释） |
| **M15** | 专家方案层 + 知识缺口（总方案《专家方案沉淀与动态知识生长》） | 检索复用闭环 + 失败知识化 + 晋升机制 | ✅ **完成**（`expert_solutions/knowledge_gaps/research_sessions` 三表 + M8 七路线种子；`kb/solutions.py` 检索/回写/晋升/缺口；orchestrator `_pick_solution` 前置[命中零规划硬币]+`_chain_for` route_json 回放+`_writeback` 三终态回写；MCP `search_solutions` 11 工具；`test_m15_wiring.py` 23 checks + MCP 自测全过。活例：hybrid_final 差 2 个真实任务晋升 expert） |

M1-M3 完成即达成构想的核心命题：**机器可理解、按能力检索的知识库**。M5/M6 是增强。
M8/M9 把库变成了**能干活的系统**：前者证明"检索→组合→修改→验证"全链路可走通（自拼
ReActor 4 节点流即证据），后者把"人当裁判"升级为"系统自判"（笨拙→纠正→完善的飞轮起点）。

## 8. 关键决策点（历史拍板记录）

1. **LLM 用什么做知识卡分析？** → 已定：DeepSeek API（M2 全覆盖完成）
2. **首批入库规模** → 已定：50 起步控质量（M1 92 条），M4' 定向补缺至 168，M7 +40 H3 = 208
3. **本地有没有 ComfyUI 环境？** → 已定：无本地，全部走 RunningHub 云端（M5 起）
4. **语言** → 已定：知识卡中文为主，节点/参数名英文原文
5. **（M8 起）语义评审用什么？** → 已定：Qwen-VL（dashscope `qwen-vl-max`；注意
   `-latest` 别名可能 403，`vl.py` 已默认安全名；key 在 `.qwen_key`）
6. **（M9 起）自主探索的边界？** → 已定：机制先行、不追求一次到位；规则必须带
   evidence/status，未验证假设不得当真理执行；身份判定以几何 cos 为权威，VL 主观分
   只管语义维度（嘟嘴/色彩/光照）

## 8b. 后续里程碑（未开始）

| 里程碑 | 内容 | 依赖 |
|---|---|---|
| **M10b** | 闭环 B：宽泛提示解析器（比较型断言→tech_families 机制差→改进假设→节点检索） | tech_families 已就位 |
| **M11** | 外部研究通道（三源）：GitHub（operator 实现）+ ComfyUI Registry（节点包元数据）+ HuggingFace（模型/模型卡/license 层，定位与边界见 `docs/M15_design.md` §5）→ research_sessions 漏斗（候选20→初筛5→深读1-2）→ external_fact；B站/C站后续按用户定渠道后扩 | ✅ **v1 全链闭环**（`research/`：external/session/run/probe_webapp；session#1：gap#1 发型+表情 → 21 候选 → FLUX.2 Klein 9B operator 探针实证 → gap resolved + flux2_klein_hair(candidate) 回写） |
| **M17** | Civitai（C 站）第四知识源：**用法与技巧层**（个人自研 LoRA/workflow + 教程 desc；NSFW 域近独占）。双重身份：第二工作流采集源（Workflows zip 匿名公开、UI 图与 RH 同构直接入库）+ 研究通道第四源。设计定稿 `docs/M17_civitai_design.md`（八轮零硬币探测实证：desc 技巧富矿 5.5 万字符/条、NSFW API 无登录墙、`.com`/`.red` 双域名同后端互为备份、**模型引用经解析而非墙——RH 模型广场公开 API `portal/model/list{search}` 6 万资源，Civitai 主流模型同名/近名大面积在库（Realistic Vision V6.0 B1/Detail Tweaker XL 原名、cyberrealistic 换版+Z-Image 跨家族移植），P2b 三级解析(exact/renamed/version_differs/family_port/none)+resolution gate**、images.meta 空/CLI 错位等负发现） | 📐 设计完成（P1/P2/P2b 待实施） |
| **M12** | ComfyUI 官方 registry 元数据采集器（零硬币补节点清单） | 无 |
| **M13** | 边界羽化算子（Rope 式 poisson/blend）补 inswapper 边缘伪影 | diagnosis_rules 已有对应症状条目 |
| **M14** | webapp 任务族扩展：kb_generic 视频任务、多图输入、反馈修订的参数级微调（锚次数/GFPGAN 权重） | M10 架构 |
| **M18** | 对话式任务闭环（协商式管线）：前置可行性检查（boundary_laws/decision_rules/negative_result 匹配→**软提示**路径卡片，默认 8s 走推荐路径可换）+ 解释器升级（方差置信标注+证据链接+为什么不选X）+ 反馈五分类（+hypothesis：用户假设/技术方向一等化→自动探针→带署名规则升格）+ task_threads 长任务线程（上下文/持久化/时间线视图）+ 线程收口四栏自动总结（事实/定律/规则/开放问题）。**用户决策（2026-08-25）**：① 卡片文案必须明确可读（生图/视频专业性→用户在学习中，禁止未解释术语；前提=外部研究已完成；允许懂行用户反向指定技术方向由 AI 搜证）② 默认软提示不拦截。设计定稿 `docs/M18_design.md`。触发证据：H3 五臂弧（当日最大突破 i2v 决策规则来自用户假设而非系统搜索） | 🔨 P0 完成（laws×7+rules×4 入库；boundaries 前置检查；negotiating 态+8s 软门+三条视频路线执行器 i2v/fl2v/retimed；前端卡片区+倒计时+Why 折叠；验收 19+21 全过，8830 上线）。P1 线程+裁决 UI；P2 假设管线+自动总结 |

## 9. 风险与对策

| 风险 | 对策 |
|---|---|
| RunningHub 接口改版 | probe 脚本已留；collector 单独成层，坏了只修一层 |
| LLM 分析质量差/幻觉 | 置信度分级 + fact/inference 分离存储 + 卡版本号（换模型可重跑） |
| 工作流结构重复（同一流多人发） | M4 做结构 hash（节点类型集合+拓扑）去重 |
| remix-copy 在账号里留副本 | 批量采集后定期清理 Workspace；或接受（也是云端实验的入口） |
