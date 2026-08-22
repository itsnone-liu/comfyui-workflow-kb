# RunningHub 工作流下载器 + ComfyUI 工作流知识库

用程序从 [runninghub.ai](https://www.runninghub.ai)（ComfyUI 云平台）搜索并下载工作流，并构建 agent 可检索的**工作流知识库**（采集 → 解析 → LLM 知识卡 → MCP 检索）。

## 逆向结论（2026-08-21 实测）

RunningHub 前端是 Nuxt SPA，所有接口 `POST https://www.runninghub.ai/api/...`，JSON 体，`code==0` 为成功。

### 公开接口（无需登录）

| 接口 | 请求体 | 作用 |
|---|---|---|
| `POST /api/portal/creation/list` | `{"current":1,"size":30,"sort":"RECOMMEND","search":"","tags":[]}` | 作品广场浏览/搜索，返回作品卡片（含 id、封面、统计） |
| `POST /api/creation/detail` | `{"creationId":"...","queryType":"current","sort":"","search":"","tags":[]}` | 作品详情 → `creationDetailInfos[].workflowId`（作品背后的工作流 ID） |
| `POST /api/portal/workflow/detail` | `{"workflowId":"..."}` | 工作流公开元数据：名称、封面、`customNodes`、`primitiveNodes`、`usedModels`、`nodeCount`、`webappId`。**`workflowContent` 为 null（内容不公开）** |
| `POST /api/webapp/simple/detail` | `{"webappId":"..."}` | webapp 的 `inputNodes`（API 格式输入定义），可直接驱动官方 Task API |

### 需要登录的接口

**认证方式**：请求头 `Authorization: <token>`，token 存在浏览器 localStorage 的 `Rh-Accesstoken` 键；有效期见 `Rh-Expire-In`。

| 接口 | 说明 |
|---|---|
| `POST /api/workflow/copy` | **页面 "Remix" 按钮的真实接口**。请求体：`{"creationRequest":{"requestType":2,"fileUrl":"<作品输出图URL>"},"workflowId":"...","creationId":"...","copyMode":1,"contentType":1}`。返回完整 `workflowContent`（ComfyUI 图 JSON），**同时会把工作流复制一份到自己账号（副作用）** |
| `POST /api/workflow/detail`（body `{"id":"..."}`） | 只能查自己账号里的工作流，查他人的返回 404 |

**页面 URL 规律**：作品详情页 `https://www.runninghub.ai/works-details-page/{creationId}`；"Remix" 即"取回工作流到我的账号"。

**完整下载链路**（三步）：
1. `creation/detail` → 拿 `workflowId` + 作品输出图 `fileUrl`
2. `portal/workflow/detail` → 拿元数据（节点/模型清单，公开）
3. `workflow/copy`（带 token）→ 响应里直接是完整 `workflowContent`

## 使用

环境：任意 Python 3.10+（标准库即可）；登录工具额外需要 playwright（`pip install playwright && playwright install chromium`）。

```bash
# 1)（一次性）登录并保存 token —— 会开浏览器，手动登录即可
python rh_login.py

# 2) 下载：支持作品 URL / 裸 ID
python download_workflow.py "https://www.runninghub.ai/works-details-page/2085702514952347649"
python download_workflow.py 2085702514952347649 --out downloads

# 3) 在代码里搜索/浏览
import rh_client as rh
rh.list_creations(search="flux", size=20)   # 搜索
rh.creation_detail(id)                       # -> workflowIds + fileUrl
rh.workflow_meta(wfid)                       # 元数据
rh.workflow_copy(cid, wfid, file_url)        # 完整图（需 token）
```

实测输出示例：

```
[workflow] reduxV2-反推洗图万能流 (id=1915605940337577985)
  nodes=33 custom_nodes=21 models=8
  saved meta.json
  saved api_inputs.json (webapp 1925074572192718850, 1 inputs)
  remix-copy 成功（副本 id=2090423494231564290）
  saved workflow.json  ✔ 完整 ComfyUI 图（44 节点）
  saved cover_0.jpg / cover_1.jpg
```

输出目录结构（`downloads/<名称>_<workflowId>/`）：

```
meta.json         工作流公开元数据（节点清单、模型清单、封面）
workflow.json     完整 ComfyUI 图（需先 rh_login.py 登录一次）
api_inputs.json   webapp 输入节点（官方 Task API 格式）
cover_*.jpg       封面图
```

## 文件说明

| 文件 | 作用 |
|---|---|
| `rh_client.py` | API 客户端（公开 + 授权接口、token 存取、URL 解析） |
| `rh_login.py` | 一次性登录：开浏览器 → 手动登录 → 抓 `Rh-Accesstoken` 存 `.rh_token` |
| `download_workflow.py` | 命令行下载器 |
| `collector/batch_domain.py` | 按标签批量采集人物一致性窄域工作流入库 |
| `parser/normalizer.py` | UI 图 → 标准化图（分类/资产/技术/参数面/结构哈希） |
| `analyzer/llm_card.py` | LLM 知识卡生成（bailian deepseek-v4-flash-0731） |
| `kb/` | SQLite 存储、检索 CLI、schema |
| `mcp/server.py` | MCP stdio server（DSH 已注册为 `comfyui_kb`） |
| `probe*.py` | Playwright 逆向探针（保留供参考，可删） |
| `probe_out/` | 探针产物（HTML、截图、抓包 JSON） |

## 边界与注意

1. **未登录也能拿到**：搜索、列表、作品详情、工作流元数据（含自定义节点和模型清单——本地复刻工作流最需要的信息）、API 格式输入。
2. **完整图 JSON 需要登录**，走 `workflow/copy`（即站内 Remix）。副作用：每次下载会在你账号里留一份工作流副本，介意的话可在 Workspace 手动删除。
3. 部分作者可能对工作流加密（`publishAccess.encrypted`），此类即使登录也拿不到明文。
4. 本工具只做个人研究用途；批量抓取请节制，尊重平台与作者权益。
5. 接口为逆向所得，RunningHub 改版可能失效；`probe*.py` 可用于重新定位接口。

## 逆向补充（2026-08-22 批量采集时发现）

- **`search` 参数无效**：`creation/list` 传 `search` 会被忽略（返回与不传一样的推荐流）。真正有效的发现途径：
  - `POST /api/portal/tag/tree` `{"rang":"CREATION"}` → 全量标签树（含 `childTags`），人像域标签如 `人像写真/换脸/角色一致性/换装/证件照/数字人/局部重绘/精修/老照片修复/妆容`；
  - `creation/list` 的 `tags:[<tagId>]` **有效**，按标签翻页即可稳定采集。
- `POST /api/webapp/list` `{"size":30,"current":1,"search":"...","sort":""}` → webapp 搜索有效，但很多 webapp 的 `workflowId` 不公开（作者未公开工作流），拿不到图 JSON。
- 部分工作流作者加密（错误码 1913「您暂无权限访问该工作流」），跳过即可。
- 同一底层工作流常被多个作品复用，采集时按 `workflowId` 去重。

## 知识库（KB）流水线

```
collector/batch_domain.py   按标签批量采集（人物一致性窄域）→ data/raw/runninghub/<slug>_<wfid>/
parser/normalizer.py        UI 图 → 标准化图（节点分类/资产/技术/参数面/结构哈希）→ data/graph/
parser/parse_all.py         批量解析安全网（采集时已顺带解析，此为查漏）
analyzer/llm_card.py        LLM 生成中文知识卡（能力/特殊结构/设计意图/fact-inference 分级）→ data/cards/ + kb.db
analyzer/pattern_miner.py   模式挖掘（链/技术 signature/边界挂点）→ patterns 表 + data/patterns_report.md
kb/query.py                 命令行检索（--capability/--technique/--min-geek/--stats）
mcp/server.py               MCP stdio server：10 个工具（见下）
```

数据落在 `data/kb.db`（SQLite：workflows / knowledge_cards / knowledge_items[fact|inference|hypothesis|verified_result] / patterns / experiments）。

当前规模：**208 工作流 / 208 卡 / 1847 知识条目 / 1245 patterns**。
其中 **MiniMax H3 细分专库 40 条**（`collector/batch_h3.py` 采集，`data/h3_report.md`
细分报告：T8 原生节点族 vs RH API 封装两条路线，十个任务面，质量-成本-显存知识核心）。

## Git 仓库与 CodeGraph 索引

独立 git 仓库（父目录 harness 仓库不跟踪本目录）。**已入库**：全部代码/文档 +
`data/kb.db`（3.2MB 知识库本体）+ `data/graph|cards|api_format`（解析产物）+
`data/composed/*.api.json`（已验证的自拼图）。**已排除**（.gitignore）：`.rh_*`
密钥与浏览器 profile、`data/raw`（782MB 原始采集，可用 collector 重采）、
`data/models`（onnx）、实验/组合的输出图片（结论都在 kb.db）。

```powershell
git log --oneline                  # 94a52b0 init(M0-M7) → aec29ff codegraph → ...
$env:PYTHONPATH=''
& "...\python.exe" analyzer\codegraph.py index     # 重建索引（改代码后）
& "...\python.exe" analyzer\codegraph.py stats     # 模块/def/热点（fan-in 榜）
& "...\python.exe" analyzer\codegraph.py query graft_api    # 符号 + 1 跳调用者/被调
& "...\python.exe" analyzer\codegraph.py tree      # 模块/def 树
& "...\python.exe" analyzer\codegraph.py dot       # 模块导入图 (graphviz)
```

索引产物：`data/codegraph.json`（50 模块 / 178 defs / 2901 调用点，别名感知解析
`go.graft_api → parser.graph_ops.graft_api`）+ `data/codegraph_modules.dot`。

## 运行结果临时画廊（serve_results.py + 公网隧道）

自建/实验工作流跑完后的下载产物（`data/composed/*/`、`data/experiments/*/`）
自动出现在一个自刷新网页里（4 秒轮询，图片+视频混排，按目录分组）：

```powershell
$env:PYTHONPATH=''
& "...\python.exe" serve_results.py                 # 本地 http://localhost:8820
ssh -R 80:localhost:8820 nokey@localhost.run        # 公网 https://<random>.lhr.life
```

零依赖（纯 stdlib）；实验在后台跑时页面自动长出新结果。隧道域名每次随机，
免费层够临时演示用。

### MCP 工具（`mcp/server.py`，已注册到 DSH web profile，名为 `comfyui_kb`）

| 工具 | 作用 |
|---|---|
| `search_workflows` | 按能力/技术/关键词/geek 评分检索，返回卡片摘要 |
| `get_knowledge_card` | 完整知识卡：能力、特殊结构（极客点）、设计意图、场景、限制、置信度分级条目 |
| `get_workflow` | 取 raw UI 图 / 平台元数据 / 标准化图 |
| `visualize_workflow` | Mermaid 流程图（按类别分组） |
| `kb_stats` | 库统计 |

协议自测：`python mcp/test_server.py`。

## 实验引擎（M5 ✅ 已闭环）

用官方 Task API 在 RunningHub 云端跑工作流做参数 A/B，把 inference 升级成 verified_result。

**正确 API 形态（2026-08-22 实跑验证）**——路径**无 /api 前缀**，`apiKey` 在 body（Bearer 头亦可）：

```
POST /task/openapi/ai-app/run      {webappId, apiKey, nodeInfoList}   跑 AI 应用(webapp)
POST /task/openapi/create          {workflowId, apiKey, workflow?, nodeInfoList}  跑工作流
POST /task/openapi/status          {taskId, apiKey}  -> "SUCCESS"（裸字符串）
POST /task/openapi/outputs         {taskId, apiKey}  -> 完成态为 LIST[{fileUrl,fileType,taskCostTime,consumeCoins}]
POST /task/openapi/cancel          {taskId, apiKey}
POST /openapi/v2/media/upload/binary  multipart(file) -> data.fileName（作 LoadImage fieldValue）
POST /api/openapi/getJsonApiFormat {workflowId, apiKey}  -> 平台级 UI→API 格式转换（真实输入名+精确 slot）
```

两个沙箱机制（2026-08-22 发现，Composer 的基石）：
- `create` 的 `workflowId` 是 @NotNull 且须真实存在于自己账号，但 **`workflow` 参数会整体覆盖其内容**——留一份副本当沙箱（id 存 `.rh_sandbox_wf`），之后自拼图零拷贝无限复用；
- `getJsonApiFormat` 接受**公开** workflowId，返回官方 API 格式（`data/api_format/` 缓存）——自己猜 widget 输入名必被校验拒绝，必须走它。

注意：`/api/task/openapi/*`（带 /api 前缀）是网页网关，API key 在那边报 TOKEN_MISSION/TOKEN_INVALID。`.cn` 与 `.ai` 两域名共享后端（webappId 通用）。

```
experiments/rh_task.py    Task API 客户端（run_webapp/run_workflow/run_workflow_json[沙箱自拼]/get_json_api_format/上传/轮询/下载）
experiments/metrics.py    人脸身份度量：YuNet 检测 + SFace 嵌入（模型 data/models/，cos≥0.363 同人）
experiments/runner.py     A/B(n) 跑批器：inputs/run/show 子命令；--domain --dry-run --max-arms
collector/backfill_api_inputs.py  api_inputs.json 补齐器（103 条已有）
```

**API key**：`.rh_apikey`（一行）或 `RH_API_KEY` 环境变量。已就位并实跑成功。

**首个 A/B（exp006，已入档）**：PuLID 流 `1920447051887214593`，KSampler `143.denoise`
0.15 vs 0.35 → SFace cosine **0.378 vs 0.329**（Δ=-0.050）：denoise 越高身份漂移越大，
0.35 已跌破同人阈值 0.363。每臂 ~171s / 35 coins。知识条目 586 = 首条 verified_result。

**实验方法学（exp015 种子方差，#1488）**：同配置同输入重跑两次极差达 **0.063**——
单臂单次差异 <0.05 不可作为结论，A/B 需 ≥3 次采样。runner 支持 `--arms r1=v,r2=v`
重复臂语法（自动出方差 verdict），常规 verdict 也带方差警示。
**805 排障（exp016）**：空 nodeInfoList 全默认探针能分清"流坏了"还是"图坏了"
（该 InstantID webapp 本身健康，特定上传图会运行时崩溃）。

```powershell
cd D:\qjcNetDiskDownload\deepseek-harness\project\820
$env:PYTHONPATH=''   # 防 venv 被污染
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" experiments\runner.py inputs 1920447051887214593
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" experiments\runner.py run 1920447051887214593 `
  --var 143.denoise --arms 0.15,0.35 `
  --image "158.image=data\raw\runninghub\1920447051887214593_1920447051887214593\cover_0.jpg"
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" experiments\runner.py run 1920447051887214593 `
  --var 143.denoise --arms r1=0.15,r2=0.15   # 种子稳定性重复臂
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" experiments\runner.py show 6
```

## 模式挖掘与 Composer（M6-0 ✅ / M6-1 首配方 ✅）

**M6-0 模式挖掘**：`analyzer/pattern_miner.py` 从标准化图挖三类模式入库（patterns 表，305 条）：
链模式（typed-edge DFS，L1-L3 df≥5/4/3）、技术 signature（PuLID/InstantID/FaceDetailer 等的
节点集+共边，≥60% 共享率）、边界挂点（LoadImage→X / X→SaveImage 可组装位）。
`data/patterns_report.md` = TASK_FACETS 覆盖率报告 + M4' 采购清单。

**M6-1 Composer**：**声明式配方**（`analyzer/recipes.json`：op 序列 + metric 名；
`composer.py` 是通用解释器 `compose_from_spec`，新增配方=加 JSON 不写代码），五配方实跑验证——

```
compose upscale      --base <wf> [--run --metric]   段移植：4x放大 → 7808×11776
compose face_detail  --base <wf> [--run --metric]   段移植：FaceDetailer+SAM 检测器链 → 24 节点
compose batch        --base <wf> --n 4 [--run]      参数变换：batch_size → 恰好 N 张输出
compose bg_remove    --base <wf> [--run --metric]   段移植：BiRefNet alpha 抠图（81% 透明）
compose pose_transfer --base <wf> [--run --metric]  多端口注入 + 跨源合成（见下）
```

- 段移植：`parser/graph_ops.py` 在**平台 API 格式**上操作（extract_segment_api 抽锚节点+上游、
  graft_api/graft_multi 类型端口缝合、prune_to_outputs 剔除死分支/UI 辅助节点）
- 参数变换：直接改 API 格式的具名输入（batch_size 等），无需移植
- pose_transfer：positive+negative 双条件边经 graft_multi 改道；段由**两个库工作流跨源合成**
  （FLUX Union CN + Openpose 预处理器，模型家族匹配——SD1.5 CN 接 FLUX conditioning 会运行时爆）
- 验证回路：组装 → 沙箱提交 → 轮询 → 下载 → 配方专属指标（分辨率/张数/alpha 通道）

**MCP 10 工具**（`mcp/server.py`，DSH profile `comfyui_kb`）：

| 工具 | 作用 |
|---|---|
| `search_workflows` / `get_knowledge_card` / `get_workflow` / `visualize_workflow` / `kb_stats` | 检索与知识卡 |
| `list_workflow_inputs` / `submit_experiment` / `get_experiment` | 实验引擎入口 |
| `list_patterns` / `get_pattern` | 模式库浏览（Composer 拼接字典） |

协议自测：`python mcp/test_server.py`。

## 定向采集（M4' ✅ 三渠道）

覆盖率报告驱动，不做盲采（`data/patterns_report.md` 的 gap 清单即采购单）：

```
collector/batch_targeted.py   标签+customNodes 元数据预过滤（copy 前确认相关性，不污染账号）
collector/batch_deep.py       顽固缺口深挖（整标签翻页）
collector/batch_webapp.py     webapp 搜索（技术词命中率高；附赠 inputNodes=api_inputs）
```

webapp 渠道（最高效）：`webapp/list {search}` → `rec.id`=webappId →
`webapp/simple/detail` 拿 `workflowId`+inputNodes → `workflow/copy("", workflowId, 封面url)`。

## 下一步（项目规划）

- [x] 批量模式：按标签抓取并全部下载（92 条 → M4' 后 **168 条**，全部已解析）
- [x] 知识卡生成 + 检索 + MCP（62 张卡，586 条知识条目；新增 106 条待 card_gen）
- [x] **M5 闭环：云端实验引擎实跑成功**（exp006 denoise A/B → 首条 verified_result #586）
- [x] **M6-0 模式挖掘**（950 patterns + 覆盖率报告，主技术面全部可用）
- [x] **M5+ 自拼工作流验证回路**（沙箱 workflow 覆盖参数 + getJsonApiFormat 平台级转换）
- [x] **M6-1 Composer 五配方云端验证**（upscale；face_detail；batch；bg_remove；pose_transfer 跨源合成+多端口注入）
- [x] **M5 扩展：denoise 完整曲线**（exp010 0.10/0.20/0.30 + exp006 → 5 点曲线，>0.30 断崖，综合结论 #735）
- [x] **M5 再扩展：种子稳定性 + InstantID 实验**（exp015 极差 0.063 方差修正 #1488，重复臂语法；exp016 805 排障探针法；exp017 amount 无影响 + InstantID 系库内最强身份保持 cos~0.84，#1491）
- [x] **M6-1 再扩展：配方声明式化**（recipes.json spec 表驱动，五配方重组装逐一比对一致）
- [ ] M6-1 再扩展：多段同时移植、pose 定量指标（关键点 IoU）
- [x] **知识卡全覆盖**（168/168；fact 796 / inference 686 / verified_result 5，共 1487 条）
- [x] **M7：MiniMax H3 细分专库**（40 条定向采集 + 40 卡，两条集成路线画像，`data/h3_report.md`；视频能力 18→58 条）
- [x] **M7 扩展①：H3 步数实验**（exp021/022 固定种子 4/8/20 → 帧间稳定性 0.248/0.159/0.364，#1852：加速版牺牲身份稳定；新 `--video` 视频指标模式 + VideoComparator）
- [x] **M6-1 再扩展：h3_boost 配方**（第 6 配方，SageAttention 补丁 MODEL 口移植，声明式零代码新增，云端 SUCCESS）
- [x] **M5 再扩展：denoise 平台期复测**（exp019 每点 2 次 → 0.10/0.15/0.20 均值 0.372/0.340/0.322 单调降，#1851 推翻"0.15 峰值"）
- [ ] M7 扩展②：量化 vs 全精度、3图 vs 9图多参上限
- [ ] 与 runninghub.cn（国内站）接口差异验证（已证实两域名共享后端，此项基本无必要）

