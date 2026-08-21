# 进度快照 —— 2026-08-22（M0–M7 完成；git 仓库 + codegraph 索引已建 ✅）

> 重启后从这份文件恢复上下文。先读 `PLAN.md`（总方案）再看这里（当前状态）。
> 代码版本管理：本目录是独立 git 仓库（`git log` 看历史；密钥/原始采集/模型/输出图已
> gitignore，知识库本体 kb.db+graph+cards 入库）。代码结构查询：`analyzer/codegraph.py`。

## 当前状态：M0–M3 + M5/M5+ + M6-0/M6-1 + M4' + 后续三项 + **M7 H3 细分** ✅

### M7：MiniMax H3（海螺 Hailuo H3）细分专库 ✅（详见 `data/h3_report.md`）

- **采集**：`collector/batch_h3.py` webapp 四关键词定向 40 条（0 失败，全带 webapp）
- **建卡**：40/40（4★×31），零失败
- **细分画像**：两条集成路线（原生 T8 节点族本地推理 vs RH 官方 API 封装）；
  十个任务面（加速16 图生15 多参9 首尾帧8 音频6 文生4 对口型3 反推2 高清2 编辑1）
- **知识核心**：质量-成本-显存三角（渐进采样/量化/SageAttention/双时钟/BlockCache）
- 视频生成能力 18→58 条；TeaCache×14 等加速技术成为可移植段新来源

### 库内成果（最终态）

| 指标 | 值 |
|---|---|
| 工作流入库 | **208 条**（92 原始 + 76 定向 + **40 MiniMax H3**；全部已解析 `data/graph/`） |
| 知识卡 | **208 张**（全覆盖；主库 geek 5★×3 4★×113 + H3 4★×31） |
| 知识条目 | **1847 条**：fact 1027 / inference 813 / verified_result 7 |
| patterns | **1245 条**（1165 链 + 技术 signature + 65 边界挂点；TeaCache×14 新入） |
| 技术覆盖 | FaceAnalysis×44, Inpaint×37, Upscale×36, Kontext×24, **InstantID×20**, ControlNet×19, Florence2×17, WanVideo×17, **PuLID×16**, BiRefNet×11, VACE×11, **OpenPose×6**, FaceDetailer×6 |

### M4' 定向采集（完成，三渠道接力）

| 渠道 | 收获 | 适用 |
|---|---|---|
| `batch_targeted.py`（标签+元数据预过滤） | +25 | 批量/修复/姿态/写真 |
| `batch_deep.py`（整标签深翻页） | +17 | 数字人/人像写真/动作迁移 |
| `batch_webapp.py`（**webapp 搜索**，站内 creation 搜索无效） | +34 | 技术词精确命中：PuLID+6、InstantID+9、OpenPose+5、BiRefNet+6… |

webapp 渠道要点：`/api/webapp/list {search}` 有效 → `rec.id` 即 webappId →
`webapp/simple/detail` 拿 `workflowId`+inputNodes（**免费附带 api_inputs.json**）→
`workflow/copy(creationId="", workflowId, 封面fileUrl)` 直返图 JSON。

### M6-0 模式挖掘（完成，已随 M4' 刷新两轮）

`analyzer/pattern_miner.py`：从 168 图挖出 881 链模式（L1:211 L2:268 L3:402）、15 技术
signature、54 边界挂点 → 950 patterns。`data/patterns_report.md` 的 TASK_FACETS 覆盖表
（主技术≥8 例即可用）：身份注入/批量/放大/重绘/修复/人脸/视频/拼接 全部可用。

### M5+ 自拼工作流验证回路（完成，两项平台级发现）

1. **沙箱机制**：`/task/openapi/create` 的 `workflowId` 是 @NotNull 且必须真实存在于自己账号，
   但 **`workflow` 参数会整体覆盖其内容**——即：留一个副本当沙箱（`.rh_sandbox_wf` 记录 id），
   之后每次提交自拼图零拷贝、无限复用。输出文件名前缀证明跑的就是自拼图。
2. **平台级 UI→API 转换**：`POST /api/openapi/getJsonApiFormat {workflowId, apiKey}`
   （workflowId 可用**公开**工作流 id）返回带**真实输入名和精确 slot** 的 API 格式
   （`data/api_format/<id>.json` 缓存）。自己按 widgets_values 猜输入名必死
   （433 missing_node_type / 输入名校验不过）。

```
experiments/rh_task.py   +run_workflow_json(workflow, sandbox) +get_sandbox_id() +get_json_api_format()
parser/graph_ops.py      API-format 段操作：extract_segment_api / graft_api / prune_to_outputs
analyzer/composer.py     配方驱动组装：recipes / find-segment / compose upscale|face_detail [--run --metric]
```

### M6-1 Composer（六个配方均已实跑验证 ✅）

| 配方 | 类型 | 结果 |
|---|---|---|
| `compose upscale` | 段移植（2 节点放大段） | SUCCESS，**7808×11776**（输入 680×1024） |
| `compose face_detail` | 段移植（9 节点 FaceDetailer+SAM+双检测器） | SUCCESS，1952×2944 |
| `compose batch --n 4` | 参数变换（batch_size） | SUCCESS，**恰好 4 张输出** |
| `compose bg_remove` | 段移植（2 节点 BiRefNetUltraV2 抠图段） | SUCCESS，RGBA alpha 抠图（81% 透明） |
| `compose pose_transfer` | **多端口注入 + 跨源合成** | SUCCESS，22 节点 |
| `compose h3_boost` | **H3 加速件移植（纯 JSON 新增）** | SUCCESS，23 节点，视频正常产出 |

pose_transfer 是组合能力的完整证明：
- **多端口 graft**（graft_multi）：positive+negative 双条件边同时改道经移植段
- **跨源合成段**：FLUX Union ControlNet（源 1922912583731527682）+ OpenposePreprocessor
  （源 1930214688452198401）——这个组合在库里任何单个工作流中都不存在，由 Composer 按模型
  家族匹配（FLUX base→FLUX CN）合成，union 类型自动切 "pose"
- 教训：SD1.5 openpose CN 直接接到 FLUX conditioning 会运行时 FAILED（提交校验不拦，
  跨模型不兼容在采样时爆）——家族匹配是必须的，不是优化
- **h3_boost 是声明式引擎的首个"零代码"配方**：`MiniMaxH3MemoryEfficientSageAttentionPatch`
  （单输入 MODEL 口插件）从加速版流移植进无加速底座 `2090636870803103746`，
  接线 UNET→Lora→SigmaShift→**Patch**→BasicGuider，云端 SUCCESS 出视频

两类组装能力：**跨作者段移植/合成**（extract → graft → prune）与**参数化变换**（batch_size 等）。
产物在 `data/composed/`。

**声明式配方引擎（M6-1 收尾）**：`analyzer/recipes.json` 声明配方（op 序列 load/sink/sampler/
transplant/pose_transplant/param/prune + metric 名），`composer.py` 退化为通用解释器
`compose_from_spec`。五个配方全部从 spec 重组装，节点数/段源/产物路径与手写版逐一一致
（upscale 17 / face_detail 24 / bg_remove 17 / pose 22 跨源合成同源 / batch4 同路径）。
新增配方 = 加 JSON，不再写代码。

### M5 实验引擎（exp006/010/015/016/017 + **exp019 平台期复测推翻峰值论**）

**exp019（denoise 平台期复测，#1851）——结论修正**：0.10/0.15/0.20 每点 2 次
（固定输入，6 臂）→ 均值 **0.372 / 0.340 / 0.322**，单调递减。
**"#735 的 0.15 峰值"不成立**——原 0.378 系种子噪声推高（exp015 已证极差 0.063）。
修正后：身份保持随 denoise 单调下降，0.10-0.20 为平缓区，>0.30 断崖；
实用建议：保身份取最低可用 denoise，无需迷信 0.15。

**exp020/021/022（H3 步数扫描，#1852）——首个视频实验闭环**：底座
`2085286954253791233`（唯一暴露 `124.steps` 的 H3 webapp），固定种子跨臂，
新 `--video` 模式（VideoComparator：帧间身份一致性/清晰度/运动量，无需参考图）：
steps 4/8/20 → 稳定性 **0.248 / 0.159 / 0.364**，清晰度 195/85/97。
**4/8 步加速版以牺牲帧间身份稳定为代价**（4 步帧稳但模糊，8 步漂移且最糊，
20 步满血最优）；固定种子重跑 stability 仍差 0.02（平台非完全确定性），
清晰度几乎复现（85.0/85.1）——方差在时序不在画质。arm8 首跑 805 为瞬时故障，重复臂补齐。

**denoise 完整曲线（exp006+exp010+exp019 修正版）**：0.10→0.372*，0.15→0.340*，
0.20→0.322*（*为 2 次均值），0.30→0.328，0.35→0.329——单调下降 + >0.30 断崖。

**exp015（种子稳定性，#1488）——方法学修正**：同配置同输入重跑两次 denoise=0.15
→ cos **0.339 / 0.402，极差 0.063**（臂内 std 无法算，单输出）。平台随机种子方差远超此前
估计的 ~0.02。**据此修正曲线结论**：0.10-0.20（0.351/0.378/0.356）为平台期，"0.15 峰值"
不可靠；只有 >0.30 断崖（0.328/0.329 跌破 0.363 阈值）确定。**单臂单次差异 <0.05 一律
不可作为结论，A/B 需 ≥3 次采样**（runner 的 verdict 已加此警示；`--arms r1=v,r2=v`
重复臂语法已支持，verdict 自动切换为方差模式）。

**exp016（InstantID amount 4v8，partial）**：两臂均 805 FAILED。逐层排查：缓存与线上
inputNodes 一致（无漂移）→ **webapp 全默认 payload 探针 SUCCESS（8 输出 = 2 SaveImage ×
amount 4）** → 结论：工作流本身健康，失败由我们上传的图（该流自己的 cover）触发，
特定输入图会让该 webapp 运行时崩溃（提交校验不拦）。教训：**805 状态不区分"图坏了"和
"流坏了"，探针（空 nodeInfoList 全默认跑一次）是分界线**。

**exp017（InstantID amount 4v8 重试，done，#1490+#1491）**：换标准人像图后两臂 SUCCESS。
amount=4 → cos **0.839±0.026**（8 输出），amount=8 → **0.856±0.036**（16 输出）；
Δ=0.017 < 种子噪声 0.063 → **amount 不影响身份一致性**（批量翻倍只是多采样）。
另证：该流 cos~0.84 远强于 PuLID 流（~0.34），**库内最强身份保持方案**；输出数 =
amount × 2（双 SaveImage 分支）。

**官方 Task API 正确形态（实跑验证，别再踩坑）**：
- 路径**无 /api 前缀**：`/task/openapi/ai-app/run`（webapp）、`/task/openapi/create`（自己账号工作流，
  workflowId 必填真值 + `workflow` 参数可覆盖内容=沙箱自拼）、`/task/openapi/{status,outputs,cancel}`
- `apiKey` 在 body（`Authorization: Bearer` 头亦可）；`/api/task/openapi/*` 是网页网关，API key 会报
  TOKEN_MISSION/TOKEN_INVALID——**不是 key 的问题，是路径的问题**
- 上传：`POST /openapi/v2/media/upload/binary`（multipart 字段 `file`）→ `data.fileName` 作 LoadImage 的 fieldValue
- `status` 完成态返回裸字符串 `"SUCCESS"`；`outputs` 完成态返回 **LIST** `[{fileUrl,fileType,taskCostTime,consumeCoins}]`
- `.cn` 与 `.ai` 共享后端：.ai 采集的 webappId 在 .cn 直接可跑
- 权威参考：`HM-RunningHub/ComfyUI_RH_OpenAPI`（官方插件）、`Waym1ng/runninghub-studio`（文档抄本）

```
experiments/rh_task.py    Task API 客户端（upload→fileName、run_webapp、轮询、下载、沙箱自拼）
experiments/metrics.py    YuNet+SFace 人脸身份度量（data/models/*.onnx，cos≥0.363 同人）
experiments/runner.py     A/B 跑批：inputs / run(--var --arms --image --fixed --ref --domain --dry-run) / show
mcp/server.py             10 工具（+list_patterns / get_pattern）
```

### ⚠️ 环境注意（每条命令前）

```powershell
$env:PYTHONPATH=''    # 必须！harness 全局 PYTHONPATH 污染 OpenTutor venv
```

### 下一步

- **H3 细分实验**（`data/h3_report.md` §5）：步数 4/8/满血扫描、量化 vs 全精度、
  3图 vs 9图参考；视频臂成本高，先重复臂标定种子方差
- H3 可移植段验证：把 H3 加速件（SageAttentionPatch/BlockCache/双时钟）移植到主库视频流
- M6-1 再扩展：多段同时移植、pose 定量指标（关键点 IoU）
- denoise 平台期三臂各重跑 2 次取均值（检验"0.15 峰值"是否成立）
- MCP 10 工具已注册 DSH（`cordis.patch.yml` 的 `comfyui_kb`），重启 DSH 生效

**关键命令**（cwd=820）：
```powershell
$env:PYTHONPATH=''
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" experiments\runner.py inputs <wf_id>
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" experiments\runner.py run <wf_id> --var <node.field> --arms a,b --image "<node.field>=<path>"
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" analyzer\composer.py compose upscale --base <wf_id> --run --metric
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" mcp\test_server.py   # MCP 自测
```

**Token/key**：`.rh_token` 网页 token（采集用，~2026-09 中过期）；`.rh_apikey` 官方 Task API key
（已验证可用）；`.rh_sandbox_wf` 沙箱副本 workflowId（自拼流验证用，勿删）。

## 其他挂起事项

- OpenTutor 侧 3 个文件改动未 commit——用户知情，等用户决定。
- RunningHub 账号里的工作流副本：92 采集副本 + M4' 定向副本（~76）+ 1 沙箱副本（内容会被
  自拼图覆盖，属预期）——用户知情。
- web_search 工具未配置（缺 DEEPSEEK_API_KEY）——用直接 HTTP 探测 + GitHub 权威源替代。
- exp006 首跑因 outputs 解析 bug 浪费了 70 coins——已修复并用 taskId 恢复了全部指标。
- 组合流首跑教训：自猜 widget 输入名必被 ComfyUI 校验拒绝，必须走 `getJsonApiFormat`；
  云端 API 实例未必装了 rgthree 等 UI 辅助节点（prune_to_outputs 顺带解决）。
