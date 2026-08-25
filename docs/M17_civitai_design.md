# M17 设计 —— Civitai（C 站）作为第四知识源

> 2026-08-25 立项。用户三问：①NSFW 技巧 C 站更丰富？②C 站 CLI 值得用吗？
> ③与已有三源（GitHub/Registry/HF）构成什么关系？
> 本文全部结论基于四轮零硬币实测探测（`_civitai_probe*.py`，
> 证据存 `data/explorations/civitai_probe_{1,2,3_zip}.json`）。

## 0. 一句话结论

**Civitai 是"用法与技巧层"，与三源互补而非重叠；它同时是第二工作流采集源
（Workflows 资源 zip 匿名公开、与 RH 图同构可直接入库，.com/.red 双域名同后端
可互为备份）和 M11 研究通道的第四源（desc 正文是机制句富矿）；NSFW 域它近乎
独占。不走 CLI，stdlib 直连。应用侧注意：Civitai 图的模型引用是作者本地文件名，
与 RH 文件名不一致——但 RH 模型广场（公开 API，6 万资源）实测覆盖 Civitai
主流模型（名称略异），三级解析（预置/广场/家族）+ resolution gate 解决。**

## 1. 探测实证（2026-08-25，无 key 匿名）

| # | 事实 | 证据 |
|---|---|---|
| 1 | API v1 全 GET 匿名可用：`/models`（query/types/sort/nsfw/cursor 分页）、`/models/{id}`、`/model-versions/{id}`、`/images`、`/creators`、`/tags` | probe1 全 200 |
| 2 | **Workflows 是一等资源类型**（`types=Workflows`），query 直接命中（"face swap" 前三全是 Workflows）；无独立 `/workflows` 端点（404） | probe1 |
| 3 | **workflow zip 匿名可下**：`GET /api/download/models/{versionId}` → 200/206 zip，无 key、无账号副作用 | probe2/3 |
| 4 | zip 内是**标准 ComfyUI UI 格式**（`nodes/links/groups/config/extra/version`）——与 RH `workflow/copy` 同构；一 zip 多版本图（实测 3 个 JSON：82/161/196 节点） | probe3 实下 `faceSwapThatReally_ancient.zip` |
| 5 | **NSFW API 层无登录墙**：`nsfw=true` 返回 nsfwLevel=X 图；`nsfw=True` 的 Workflows 资源直接列出；敏感词 query（nsfw/deepfake/nudity）全放行 | probe1/2/3 |
| 6 | NSFW 资源体量大：如 "Smooth Workflow Wan 2.2"（nsfw=True，12.0 万下载）"WAN 2.2 AIO"（nsfw=True，8.0 万下载） | probe2 |
| 7 | **desc 正文是技巧富矿**：单条 Workflows desc 达 5.5 万字符（HTML）/2.8 万纯文本，教程级（区域提示/ADetailer/重绘/色彩污染防治）；LoRA desc 含参数级用法（"(N)SFW Slider: weight -3~+2，负值转 SFW"——机制知识） | probe2/4 |
| 8 | **images.meta 匿名为空**（三入口 × 100+ 图全空）——生成参数富矿在 API 侧拿不到，技巧只能靠资源 desc；带 key 是否恢复待验证 | probe1/3（负发现） |
| 9 | top LoRA 的 `trainedWords` 常为空——作者把触发词写进 desc 正文，**抽取要读 desc 不要只读字段** | probe4 |
| 10 | 节点生态比 RH 更杂：GetNode/SetNode 39/27、caching_*、ttN、easy、WarpFacesBack——normalizer 分类表需扩 | probe3 节点统计 |
| 11 | `metadata.totalItems` 不返回（cursor 分页）——量级只能抽样估计 | probe2 |
| 12 | 官方 **civitai-gen-skill**（Node CLI，MIT）：orchestration 生成 API（submit→poll→download；图/视频/TTS/音乐，Buzz 计费）+ 官方 MCP（`mcp.civitai.com`，search_models/AIR URN/写操作） | probe4 README 实读 |
| 13 | **双域名 = 同一 API 后端的两个镜像**（用户线索证实）：`.com` 与 `.red` 的 models/workflows 查询**逐条相同**（同 ID 同 nsfwLevel），zip 下载两端都通；差异仅在 images feed 过滤松紧（`.com` nsfw=true 会混入 SFW 项，`.red` 纯 NSFW）。网页端 NSFW 主要在 `.red`，API 层则无墙 | probe5 逐条比对 |
| 14 | **Civitai 图的 loader 引用是作者本地文件名，与 RH 云端文件名不一致**（实测 zip：`cyberrealistic_v80Inpainting.safetensors`/`vae-ft-mse-840000-ema-pruned.safetensors`）——直接提交必然找不到模型。但"不交叠"是样本偏差：kb.db 208 流只引用了平台预置模型；真实覆盖面见事实 15 | probe5b zip 抽检 |
| 15 | **RH 模型广场公开 API：`POST /api/portal/model/list {search, current, size}`**（匿名可用），**6.05 万资源**（LORA 为主 + CHECKPOINT/UNET/GGUF，社区转存上传）。Civitai 主流模型大面积在库（实测 `search=`）：`realistic vision`→28 条含 **"Realistic Vision V6.0 B1" 原名**；`detail tweaker`→10 条含 **"Detail Tweaker XL_v1.0" 原名**；`dreamshaper`→18；`cyberrealistic`→44 含 v110 换版 + **Z-Image Turbo 跨家族移植版**；`juggernaut`→25；`noobai`→171；NSFW LoRA 明确在库（"CyberRealistic ... Catalyst NSFW"、"NSFW LoRA | Krea2, FLUX"）。**"有价值模型 RH 基本都有，名称略异"（用户判断）成立**——机制：社区把 Civitai 热门模型转传 RH 广场，命名习惯=原名±版本号±中文注记±家族后缀 | probe7/8，清单 `data/explorations/rh_model_library.json` |

## 2. 四源关系定位（用户第 3 问）

| 源 | 层 | 回答的问题 | 信物 |
|---|---|---|---|
| GitHub | **实现层** | 有没有代码/节点实现这能力（operator） | repo/README |
| Registry | **节点包层** | 装什么包、版本、依赖 | 包元数据 |
| HuggingFace | **模型层** | 能力背后的模型、机制、license | 模型卡 |
| **Civitai** | **用法与技巧层** | **个人作者实际怎么用**：自研 LoRA + workflow 变体 + 教程式 desc + 实测参数区间 | LoRA/workflow 资源 + desc |

关键结构差异：RH = 平台托管流（云端可执行、API 跑），**Civitai = 个人自研资产的
发布场**（LoRA/checkpoint 为主体，workflow 是"教你怎么用我的模型"的配套）。
Civitai 模型在 RH 库内基本无对应物——它填的是 HF（模型存在但无用法）与
RH（可执行但只用官方模型）之间的**用法空洞**。

因此 Civitai 在本项目里有**双重身份**（都接入，分先后）：

- **身份 A：第二工作流采集源**（collector 层，与 RH 采集并列）——价值最高。
  RH 完整图要登录 token + 账号留副本副作用；Civitai zip 匿名零副作用，
  且自带 NSFW 域与教程 desc。入库后直接享受既有全家桶：parser 建卡 →
  MCP 检索 → pattern 挖掘 → Composer 段移植。
- **身份 B：M11 研究通道第四源**（research 层）——gap 研究时多问一句
  "C 站有没有人解过这题"。`research_sessions.sources_json` 注释里
  `civitai` 枚举**当初就预留了**，schema 零迁移。
- 远期身份 D：**第二实验执行面**（civitai-gen orchestration API，Buzz↔coins
  对位 RH Task API）——若未来要验证"Civitai 上的 LoRA 实际效果"，
  通道现成。不进本期。

## 3. CLI 结论（用户第 2 问）

**不用。**盘点：
- 官方 `civitai-gen-skill`：**生成**客户端（跑图/跑视频），不是检索工具；
  对位本项目的 RH Task API 而非 research/external.py。
- 官方 npm `civitai`：生成器 JS client（同上错位）。
- 社区 CLI（civitdl ★72、CivitAI_Image_grabber ★115 等）：模型批量**下载器**，
  只下文件不看知识——本项目只入元数据+图 JSON，模型文件本身不下载（见 §7）。

我们的需求（检索+desc 抽取+zip 解析）三个 CLI 都不覆盖，且 external.py 的
设计约束（纯 stdlib 零依赖零 key）没有理由破例——**urllib 直连即可**，
与 gh/registry/hf 三源同构，`civitai_search` 约 60 行。

## 4. 接入设计

### P1：研究通道第四源（改动最小，先行）

```
research/external.py   + civitai_search(query, types=None, nsfw=None, limit=8)
                       + civitai_desc(model_id)  -> HTML 清洗 -> 纯文本
                       （score_candidate/extract_mechanism_quotes 复用，
                        stars 信号位用 stats.thumbsUpCount/downloadCount）
research/session.py    SOURCES += civitai；漏斗各阶段照旧
research/run.py        --source civitai 可选过滤
```

- HTML 清洗：`re.sub(r"<[^>]+>", " ")` + 实体反转义（probe4 见过 `&gt;&gt;`）
- desc 截断 24KB 与 README 同规格
- 节流：≥1 rps 间隔（GitHub 未认证同款待遇；Civitai 未公布限额，保守为上）

### P2：第二采集源（collector 扩展）

```
collector/civitai_client.py   API 客户端（models 搜索/详情/zip 下载/节流）
                              域名可配置：CIVITAI_HOST= civitai.com(默认) | civitai.red
                              （probe5: 两域同后端；.com 遇 Cloudflare/区域墙时切 .red）
collector/batch_civitai.py    批量采集器：query 或 tag 驱动
                              → data/raw/civitai/<modelId>_<slug>/
                                 meta.json（资源元数据+全 versions+stats+baseModel 家族）
                                 desc.md（清洗后正文，技巧富矿）
                                 wf_<vN>.json（zip 内每个 UI 图，全版本入库）
                                 cover_*.jpg（仅元数据引用 URL，可选不落盘）
parser/parse_all.py           已按目录扫描，加 civitai 分支或直接兼容
kb/store.py                   source='civitai' 入库（source 列自由文本零迁移）
                              + nsfw 标记：workflows 表加一列 nsfw INTEGER(0/1)
                              + asset_status：'declared'（civitai）/ 'executable'（rh）
                                （结构 hash 去重复用 M4 机制，跨源同流自动合并）
```

- **normalizer 兼容性是 P2 技术风险之一**：先跑 20 条样本看 unknown 节点分类
  比例，扩 CATEGORY 表（预判要加：GetNode/SetNode→io 变量类、ttN/easy→ui 辅助、
  caching_*→辅助、WarpFacesBack 等 roop 族→face）
- MCP `search_workflows` 加 `--source`/`--nsfw` 过滤参数（默认排除 nsfw，
  显式请求才返回——见 §7）
- 建卡走既有 `analyzer/llm_card.py`，desc.md 一并喂给 LLM（作者亲述的设计
  意图，比纯结构猜强——顺带提升卡质量）

### P2b：跨平台资产解析层（事实 14/15 的对策，应用侧安全网）

Civitai 图的 loader 引用是**作者本地文件名**，直接提交 RH 必然找不到模型。
但事实 15 表明这不是墙而是**解析问题**——RH 模型广场（6 万资源）实测覆盖
Civitai 主流模型，名称略异有规律（±版本号 / 中文注记 / 家族后缀 / 量化后缀）。
据此把映射层设计为**实时解析服务**而非人工映射表：

```
kb/asset_resolve.py           resolve(civitai_filename, baseModel) -> {
                                match_kind: exact|renamed|version_differs|
                                            family_port|none,
                                rh_name, rh_type, source, confidence }
                              三级解析:
                                ① 预置层: kb.db assets_json ∪ 平台常见名
                                   (flux1-dev-fp8 等, 归一化精确/模糊匹配)
                                ② 广场层: portal/model/list {search: 归一化核心词}
                                   (匿名实时查, 60k 库; 命中即带 resourceType)
                                ③ 家族层: civitai baseModel 字段 + desc 交叉验证
                              归一化: 去量化后缀(fp8/e4m3fn/bf16/pruned/ema/scaled)
                              + 去 .safetensors + 小写 + 去分隔符
composer.py                   resolution gate: source=civitai 段移植时 loader 引用
                              逐个过 resolve; exact/renamed 自动替换,
                              version_differs/family_port 标注警告(默认仍可组装,
                              --strict 才拦), none 未解析→强制 dry-run
experiments/rh_task.py        提交前同 gate(防线二)
(可选) rh 广场转存: 完整重放若引用广场资源, 需登录态转存到 workspace 再引用
      ——.rh_token 已有; 转/引用 API 待 P2b 实施期逆向一次
```

**match_kind 语义**（对应实测样本）：
- `exact`：原名直接命中（"Realistic Vision V6.0 B1"、"Detail Tweaker XL_v1.0"）
- `renamed`：归一化后命中（"DreamShaper XL v2.1 Turbo 闪电"=原名+中文注记）
- `version_differs`：同族不同版（civitai v80 → rh v110）——权重/参数可能要重调
- `family_port`：跨家族移植（CyberRealistic → Z-Image Turbo）——语义等价但
  sampler/cfg/分辨率随家族变，**不是 drop-in**，重放需按家族规则变换参数
- `none`：广场确实没有 → unmappable，技巧可借鉴、重放不可能

映射数据全部可自动获得：kb.db assets_json（预置层）+ 广场实时搜索（主力）+
civitai baseModel（家族信号）。人工只处理 version_differs/family_port 的
参数变换规则，进 capability_notes 而不是硬编码。

### P3：NSFW 域定向建库（P2 之上的一次实战）

用户判断"NSFW 技巧 C 站更丰富"已实证。定向采集建议 query 组：
`face swap + nsfw`、`deepfake`、`nudity`、`(N)SFW slider`（tool LoRA 机制）、
`ADetailer + nsfw`（自动修手/修脸技巧域）。产出 NSFW 技巧知识卡 +
对应 LoRA 用法条目（weight 区间/触发词/baseModel 兼容矩阵）。

P3 的真实价值锚点：**给 gap 研究供弹**——例如换脸域 NSFW 场景的边缘伪影、
肤色一致性问题，C 站作者的 desc 常有现成解法（区域重绘/after-detailer 链）。

## 5. 与 RH 采集的关系（防重复）

- 同一流两边发的可能性存在：结构 hash（M4 决策 3）跨源去重，命中则
  Civitai 版作为补充（desc 技巧挂到已有卡），不新建卡
- 差异化价值排序：**NSFW 独占 > LoRA 用法 > 教程 desc > 普通工作流**
  （普通 SFW 工作流 RH 已有 208 条，别为量而量）

## 6. 验证计划（每阶段验收线）

| 阶段 | 验收 |
|---|---|
| P1 | 一个真实 gap 走 `--source civitai` 漏斗，产出 ≥1 条带 desc 引用的 external_fact |
| P2 | 20 条样本全链路：zip → UI JSON → 标准化图 → 卡入库 → MCP 可检索（含 --nsfw 过滤）；unknown 节点分类占比 <10% |
| P2b | 解析层上线：20 条样本 loader 引用全量过 `resolve()`，match_kind 分布清楚（exact/renamed 应占多数）；gate 生效——none 未解析图提交被拦、解析后段移植 `--run` 成功 ≥1 例 |
| P3 | NSFW 域 ≥30 资源入库，技巧条目（参数区间/链式解法）≥20 条，且至少 1 条被后续 gap 研究引用 |

## 7. 边界与合规

1. **只入知识不搬运资产**：模型/LoRA 文件一律不下载入库（zip 里只有 UI JSON
   与说明）；封面只存 URL 引用。desc 摘录引用带出处 URL——C 站内容多为
   CC-BY-NC 或作者自定义条款，摘录+归因用于研究可接受，全文重分发不行。
2. **NSFW 双层控制**：库内 nsfw 标记默认过滤（MCP/检索默认不出，显式
   `--nsfw` 才出）；仅研究用途（换脸/一致性技术的 NSFW 场景表现），不做内容
   分发。deepfake 相关资源同样只取"技巧结构"（节点链/参数），不取产物。
3. 接口改版风险同 RH：四个 probe 脚本保留为回归工具。
4. 网络实测本机直连 OK（civitai.com Cloudflare）；如环境受限需代理则
   `HTTPS_PROXY` 环境变量即可（urllib 自动尊重）。

## 8. 不做清单（本期明确排除）

- 不接 civitai-gen 生成 API（执行面，远期 D）
- 不接官方 MCP server（search_models 能力 urllib 已覆盖；写操作无需求）
- 不采 images feed（meta 实测空，feed 图无知识密度）
- 不批量下载任何模型文件
- 不做 Civitai 全量镜像（按 gap/覆盖率报告驱动，同 M4' 纪律）
