# 进度快照 —— 2026-08-25（M0-M11 + M15-M18设计 + DLC/H3 全日弧；git+codegraph 已推远端 ✅）

> 重启后从这份文件恢复上下文。先读 `PLAN.md`（总方案）再看这里（当前状态）。
> 代码版本管理：本目录是独立 git 仓库（`git log` 看历史；密钥/原始采集/模型/输出图已
> gitignore，知识库本体 kb.db+graph+cards 入库；**无远端 remote**，推送需用户给地址）。
> 代码结构查询：`analyzer/codegraph.py`（59 模块 / 217 符号）。

## 当前状态：M0–M7 + M8 换脸实战 + M9 探索机制 + M10 Web 前端 + M15 专家方案层 + M11 研究通道（gap#1/#2/#3）+ M16 验证层增强 + M17 设计 + DLC 验证 ✅

## 2026-08-25 会话进展

### H3 首尾帧无缝衔接验证（用户任务：ref→825 5s 加速）✅

走完整 KB 流程（检索→选流→结构诊断→三臂实验→回写）。选流：**H3图生视频&首尾帧
量化加速V3版**（webapp 2084282198664007682，库内 use=7696 社区最热，int8+nvfp4+
4步turbo+Sage+RTX VSR×2 内置加速）。

**问题归因（三臂对照，#1906-#1909 入库 + experiments + expert_solution candidate）**：
- **A 单遍直跑**：连续运动式提示词也救不了——中段硬切（尖峰簇 0.53-0.61，
  ratio 9.4；VL 帧带确认 58%→61% 场景突变）。作者示例提示词就是分镜时间线 =
  社区默认接受分段而非解决
- **B 中间帧链（画幅不齐）**：边界反而成最大硬切（ratio 12.8@0.447）——
  **发现：H3 输出画幅跟随条件帧**（0.4MP 自适应），两段 512×768/864×480，
  "共享中间帧"被不同画幅重构
- **C 中间帧链 + 16:9 归一（解法）**：**无缝**——边界 MAD 0.00736 低于段内
  帧差中位（0.0099/0.0080），接缝曲线值 0.00149 为全片最平滑点，全片 ratio 2.15；
  VL 复核接缝三帧连续肉眼不可辨。中间帧=确定性零硬币构造（人脸中心中间尺度
  裁剪 脸/高≈0.25 + LAB 半匹配）；段长守 H3 帧数公式 17k+5（56+73=129 裁 124）

方案 `h3_fl2v_seamless_chain`（candidate，family=video_transition，route_json
完整可回放）。新指标：**帧差曲线尖峰分析**（spike_ratio + 尖峰位置 + 边界 MAD
直测）——拼接检测的通用判据。画廊 8826。

### H3 追问：用户裁决 #4 + 尾帧突兀诊断 + retiming 零硬币修复 ✅

**用户裁决**（金标准，推翻机器结论）：A 单遍直跑最好；**B/C 两段完全割裂**——
C 边界 MAD 0.0074 全片最优但感知割裂。教训：**像素接缝质量 ≠ 感知连续性**；
链式 = 两次二态切换 + 中间帧（静态裁剪构图）读作换镜头。C 链降级为接缝质量
参考技术，不作交付路线。

**尾帧突兀诊断（d825 逐帧到尾帧距离曲线）**：所谓"尾帧突兀"不是最后一帧瞬移，
而是 **f52–f88 持续 1.54s 快切带**（帧差 4–9.4x 中位，d825 0.22→0.075），
前 42% 赖在首帧态、f89 后回准静止——8 倍速反差即突兀感来源。机制：H3 把首尾
条件当两个吸引态做切换而非匀速轨迹；6 个首尾帧 webapp 参数面无尾帧强度/多
关键帧旋钮，提示词已证改不了（#1906+复现）。**单遍 fl2v 范式内快切带是模型
固有行为，只能事后处理。**

**修复（零硬币，`_tail_fix.py`）**：时间重分配——检测快切带（帧差>3x 中位），
minterpolate(mci+aobmc) 120fps 运动补偿插值拉伸 2.0–2.5x，压缩前后准静止段，
端点保真。**V1 严格 5s**：spike_ratio 9.44→2.59，快速帧占比 30.1%→0%，最大
步进 9.4x→2.6x；**V2 弹性 ~7s**（保持段不动）：3.63x/1.6%。插值质检无鬼影无
扭曲（VL 复核）。新方案 `h3_fl2v_retimed_singlepass`（candidate #19）+
#1910/#1911 入库。边界：无声（音频轨被剥）、morph 固有速度 ≥2x 中位。
画廊 8827（`A_retimed_5s_smooth.mp4` / `A_retimed_7s_smooth.mp4`），待用户
视觉复核；若不满意，备选硬币实验：分镜时间线提示词重跑 / 更长生成+retiming
（真帧无插值）。

**用户复核**：V2 弹性 7s 更好（采纳基线）。追问"是不是照片差异导致转完直接
进尾帧"→ **差距→切换强度单调律**（#1912，回溯 A/B/C 数据：整跨 9.44 / 半跨
1.86-2.71 / 小跨 1.33）。

### A 方案（Klein 真实中间态）：负结果 + 规律修正 ✅

用户批准花硬币验证"首尾帧生成中间帧图"路线。Klein 双图指令生成半转身过渡
态中间帧（VL 确认姿态/景别/场景混合全合格，身份 cos 0.59/0.64 同人域）→
两段链（16:9 归一）。**结果：更差**——seg1 全程匀速 morph（中位 0.067=正常
10x，溶解感）；seg2 hold-85%+尾部硬切（spike 15.76@95%）。

**关键对照修正 #1912 假说**：D 端点外观距离（0.182/0.244）比 C 臂平滑对
（0.226/0.277）更小却更差 → 真正驱动因素是**渲染一致性**：条件帧须像同一
footage 的两帧（C_mid=825 自身裁剪→平滑；Klein 重生成=渲染边界→两段各自
morph/硬切）。指令生成中间帧路线对 fl2v **关闭**（negative_result 入库）。

**感知连续性三定律**（inference 入库）：渲染一致律 / 视差连续律（场景更换
无空间一致视差流，哪怕像素平滑也读作 dissolve=C 臂感知割裂真因）/ 遮挡豁免
律（电影剪辑用遮挡藏切换——提示词驱动"走过木隔断被短暂遮挡后入厨房"是
fl2v 范式内唯一真无缝换景路径，待验证）。产物：`D_klein_chain_FAILED.mp4`
+ `D_klein_midframe.png` 挂画廊 8827。

### E 臂（i2v 弃锚）：用户判断验证成立 ✅

用户推论"背景空间差大的两图做首尾帧，不如首帧+文生"→ 实测（159 开关
false，动作脚本：绕过橱窗→面向镜头→脱衬衫）**正结果**：帧差中位 0.038
（A 0.0063，全程有动作）、**无 >3x 带**（A 37 帧快切带）、全片 max 2.74x
（A 9.44x）、d825 平坦 0.22→0.28（三段结构消失）、动作三阶段完成（VL）、
身份 0.376（阈值上方；首帧 0.835）、结尾自由生成（0.284 vs A 0.023）。
**决策规则入库**：跨空间图对 → i2v 默认；fl2v 仅当结尾必须精确等于尾图
或两图同渲染。方法论：VL 采样条"跳变"须逐帧验证（本次 #8-#9 为采样间隔
错觉，f89-104 全 0.7-1.6x）。画廊 8827 `E_i2v_continuous_ratio2.7.mp4`。

### 当日总结 + M18 对话式任务闭环设计定稿 ✅

用户对当日实践总结：① DLC + H3 工作流实践与知识沉淀；② 系统启示——
用户可能提出技术框架内不可达的目标，AI 须给可达结果+技术解释+建议乃至
讨论，以技术路径达成真实需求；反馈交流机制须在系统与前端层面强化；
任务升级为带上下文长任务；知识模块须总结交流结果。
**当日证据链**：H3 五臂弧中最大突破（i2v 决策规则）来自用户假设而非
系统搜索——反馈是一等价值源。

**M18 设计定稿** `docs/M18_design.md`（PLAN.md §8b 已加行）。核心：
前置可行性检查（boundary_laws/decision_rules/negative_result）→ 软提示
路径卡片 → 解释器（方差置信+证据链接+为什么不选X）→ 反馈五分类
（+hypothesis 用户假设一等化：自动探针→带署名规则升格）→ task_threads
长任务线程 → 收口四栏自动总结。

**用户决策（写入设计 §1）**：① 提示明确性——生图/视频有专业性、用户在
学习中，卡片文案四行规范（做什么/效果代价/已知风险人话版/何时选它），
禁止未解释术语；前提=外部研究已完成；**允许懂行用户反向指定技术方向由
AI 搜索验证**。② 默认**软提示**不拦截（默认 8s 走推荐路径，可换；
仅必败模式标红警示也不锁死）。
验收标准用户已确认（H3 弧回放/新不可达目标软提示/假设入库/收口总结/
卡片文案非技术用户可读，共 5 条）。分期：P0 boundary 表+前置检查+卡片
（当日所学立即值班）→ P1 线程+裁决 UI → P2 假设管线+自动总结。

**收口状态（M18-P0 开工前）**：实验产物按政策入库（`0cf2f45`：输入图+
指标 json+探针条；视频/视图目录 gitignore 画廊本地服务；local/DLC 克隆
移出）；codegraph 重索引 104 模块/371 符号（`b4c929b`）；远端已推
（ba5fcfe..b4c929b）。

**M18-P0 完成（当日）** ✅：
- `kb/schema_m18.sql` + `kb/migrate_m18.py`（幂等 UPSERT）→ boundary_laws×7
  （渲染一致/视差连续/遮挡豁免hypothesis/二态切换/画幅跟随/GFPGAN U 型/方差规则）
  + decision_rules×4（DR-001 i2v 推荐/DR-002 retimed 备选/DR-003 AI中间帧死路/
  DR-004 同渲染直连），来源署名含"用户假设→E 臂验证"。
- `kb/boundaries.py` 前置检查：词法特征抽取（修复"不**同房间**"误匹配同渲染——
  负向后行断言）→ 全条件 AND 匹配 → 四行卡片（做什么/效果与代价/已知风险+
  定律码/什么时候选）+ Why 折叠；显式点名死路 → 死卡置顶强警示 requested。
- orchestrator 接线：`_run_task` 前置 `_pre` → negotiating 态 + 8s 软门
  （`CARD_GATE_SECONDS`，用户不点自动走推荐）→ 三条视频路线执行器
  `_exec_video_transition`（i2v 单帧 159=false；fl2v 双帧+`_to_169` 画布归一
  BL-005；retimed 后处理 `_retiming` 移植自 _tail_fix.py：spike>3x 中位检测+
  mci 插值 2.5x 局部拉伸）→ 死卡选择零云端调用直接 limited+证伪解释；
  反馈轮换 i2v↔retimed。face_swap/kb_generic 路径不动（回归通过）。
- 前端：`webapp/static/index.html` ①b 路径卡片区（推荐绿/警示黄/死路红边框、
  8s 倒计时、点选即 POST /card、Why 折叠、视频结果内联播放器）；
  `app.py` 新增 `POST /api/task/{id}/card` + `/img` 支持 mp4。
- 验收：`test_m18_p0.py` 19/19（迁移幂等/匹配/文案四行/无误报/refuted 排除）
  + `test_m18_e2e.py` 21/21 全 mock 零硬币（A 全流程含 retiming 实跑/B 死卡
  零云端/C 8s 门自动 i2v/D 换脸不受影响）。**8830 已重启上线**。
- 待办：P1 线程化+裁决 UI、P2 假设管线+收口自动总结。

**当日末批前端/其他优化** ✅：negotiating 态 700ms 自适应快轮询（稳态回 2s）、
轮询容错（连接中断不丢前端状态，重试提示）、提交按钮防抖、路径卡片区自动
滚入视野、灯箱支持视频播放、negotiating 态反馈区文案改"选择路径"引导；
codegraph 重索引 108 模块/396 符号/6705 调用点（+boundaries/migrate_m18）。
8830（webapp）/8827（画廊）双服务在线。

### M17 Civitai 第四知识源：设计定稿（用户三轮修正后实测坐实）✅

`docs/M17_civitai_design.md`（八轮零硬币探测 `_civitai_probe*.py`）。要点：
- Workflows zip 匿名公开可下，内部=标准 ComfyUI UI 图（与 RH 同构，parser 直接吃）
- desc 正文是技巧富矿（单条 5.5 万字符教程级；LoRA 参数区间/触发词要读 desc 非字段）
- `.com`/`.red` 同 API 后端镜像互备（API 层 NSFW 无墙）
- **RH 模型广场公开 API `portal/model/list {search}`（6 万资源）**——Civitai 主流模型
  同名/近名大面积在库（"名称略异"=版本号/中文注记/家族后缀），P2b=三级实时解析
  （exact/renamed/version_differs/family_port/none）+ composer/rh_task 双道 gate
- 负发现：images.meta 匿名为空；CLI（civitai-gen/社区下载器）与检索需求错位，不用
- P1（研究通道第四源）→ P2（采集源）→ P2b（资产解析）→ P3（NSFW 定向建库）待实施

### Deep-Live-Cam 作用验证（明日计划#2，RH 云端完成）✅

用户定向：不用本地算力，全部 RH。DLC 内核=inswapper_128+GFPGANv1.4 → RH 等价物
=自拼 ReActorFaceSwap 流（`_dlc_ab.py`，4 臂，图对=脸部参考图+被换脸2，跨人
cos=-0.179 硬对）：

| 臂 | identity↑ | residual↓ | expr↓ |
|---|---|---|---|
| A restore=none（纯 inswapper） | 0.6252 | 0.1137 | 0.142 |
| **B GFPGAN blend 0.4（甜点）** | **0.6644** | **0.0726** | 0.144 |
| C GFPGAN blend 1.0 | 0.6036 | 0.1331 | 0.145 |
| D = A 重复（确定性） | 0.6252 | 0.1137 | 0.142 |
| 基线 v2_reactor（同 B，昨会话） | 0.6625 | 0.0704 | 0.144 |
| 基线 v2_scail2 表情链 | 0.585-0.601 | ~0.11 | 0.136-0.170 |
| 基线 v2_lp 表情链 | 0.586-0.592 | ~0.13 | **0.112** |

**结论（#1898-#1905 入库，experiments 行，tech_families 更新）**：
1. **GFPGAN U 型律**：0.4 混合=免费增益（+0.039 身份/−0.041 残差）；1.0 全强度
   反噬（先验拉向均值脸，身份跌破无增强档）——"塑料感"首次定量
2. **前向链确定性**：D≡A 完全一致 + B 跨会话复现差 ≤0.002 → inswapper 族单次
   A/B 有效（对照扩散族 exp015 极差 0.063 需 ≥3 采样）——A/B 方差规则按族区分
3. **M15 接入结论**：DLC 单图换脸上限已被 RH reactor 等价覆盖（本 A/B 即证明，
   无需本地部署）；不可替代性仅实时场景（live 摄像头）。可借机制：GFPGAN 甜点参数、
   mouth mask（可作确定性后处理算子，无需 DLC 本体）

## 明日计划（用户 2026-08-24 收工时定）

1. **新方向实验**：换一个比换脸简单的方向（用户判断依据：表情+一致性是生图难点，
   换方向可降低验证复杂度、考验系统泛化）。候选由用户明日定；KB 知识体系
   （研究通道/专家方案/验证层）应直接复用。
2. ~~**Deep Live Cam 试点**~~ → **✅ 已完成（2026-08-25，RH 云端验证）**：
   机制等价 A/B 证明单图价值已被 reactor 覆盖，定位=实时场景专用算子；
   GFPGAN U 型律+前向链确定性入库（见上）。本地部署路线关闭。
3. **可交付化**：前端（webapp 8830）+ 流程细节打磨——capability_notes 只读视图、
   仲裁升级的用户交互面、任务/反馈闭环 UI；目标是"可交付水平"。

## 收工状态（2026-08-24 夜）

- git：`4061171`（M16 + codegraph 重索引）已推远端；工作树干净
- 服务：OpenTutor web/api/lab 正常；820 webapp 8830（含反馈路由端点）；
  画廊 8824（仅挂 v2 三目录，按"本次运行"政策）
- 环境：`.venv-kb`（mediapipe 0.10.35 + face_landmarker.task）已就绪并被
  au_geometry/vl_arbiter/auto_explore 子进程桥接使用；hermes PYTHONPATH 污染
  需 `$env:PYTHONPATH=''`（见 课件lab服务注意事项.md）
- KB 增量：gap#3 开（眉维几何盲区待补）；scail2 链 validated；LP 链 candidate；
  capability_notes ×10；user_rulings ×2；Deep-Live-Cam 线索 external_fact

### 2026-08-24 晚 M16 全量落地（用户: "系统优化是最重要的事情"）✅

**A1 验证层 AU 通道**：`analyzer/au_geometry.py`（MediaPipe Tasks FaceLandmarker
blendshape 52 AU，独立 `.venv-kb` 环境子进程桥接）。回归（v1+v2 全输出，金标准=
用户裁决）：**眼/嘴/嘟嘴三维与用户裁决三次吻合**（LP表情更强=pucker过冲2.4×；
双链眼微睁=欠闭0.35；scail2嘟嘴保真）；**眉维 contested**——VL+几何双机器通道
一致偏 LP 而用户裁 scail2（人感"皱眉"≈browDown+纹理，browInnerUp 读作悲伤）。
多帧分布稳定，单帧比较可用。

**A2 仲裁器**：`analyzer/vl_arbiter.py` 双通道+分维度信任表+升级规则（争议维
主导→必用户仲裁，即使双通道一致；TIE_MARGIN=0.05）。在线回归 v2 案 auto=
prefer_a 与金标准一致。回归集 `data/arbiter_regression.json`。

**B 反馈路由**：`kb/feedback.py` 四分类（verdict/operator_lead/meta_capability/
new_requirement），webapp feedback 端点接线+冒烟通过；三类真实反馈分类全对。

**C 验证域知识宿主**：capability_notes（10 条：AU 通道验证/眉维争议/信任表/
双链 AU 签名/vl 偏差）+ user_rulings（2 条金标准）。

auto_explore 接入 au_channel 一级指标；`analyzer/au_regression.py` 常设校准工具；
_tmp 全清；webapp 已重启（pwsh-24）。详见 docs/M16_design.md §6。

### 2026-08-24 v2 实验 + 系统评价（用户）+ M16 设计 ✅

**v2 极端表情（痛苦：皱眉+闭眼+O嘴+头后仰）双链对比**，用户裁决：**scail2 更胜一筹**
（皱眉比 LP 好），双链眼微睁/嘴张开细节都好，**双链保留**。触发 M15 晋升机制首个活例：
`scail2_expression_chain` candidate → **validated**（2 不同输入）；`lp_expression_chain`
注册 candidate #17（v1 校准"表情强/一致性弱"+v2"头姿迁移成功"）。
VL 失准三次实证入库（v1 glm 单图 / v2 qwen 对比 / v2 glm 单图，用户裁决均相反）。

**用户系统评价**：①生成链（外寻知识→验证→沉淀）已达设计目标；②图片细节识别
（表情 AU 级）不足是主要短板；③用户反馈应强化为系统调整的一等输入（工具线索、
能力评价都要能驱动知识库——不只生成环节，还有验证环节）。

**落账**：gap#3 验证层缺口开启（au_geometry/multi_model_arbitration/user_calibration_loop）；
Deep-Live-Cam 用户线索 → external_fact（★96k 视频换脸候选，research 下目标）；
**M16 设计定稿** `docs/M16_design.md`（A 验证层增强：AU 密集几何/多模型仲裁/用户校准环；
B 反馈四分类路由器；C 验证域知识宿主）。

### 2026-08-24 会话：gap#2 表情 AU 迁移（用户反馈驱动，全链第二次闭环）✅

**触发**：换脸任务 reactor 输出身份/嘴形达标但"委屈表情"（AU1+4 皱眉 + AU15 撇嘴）丢失，
用户目测发现——**指标盲区实证**：几何 5 关键点不含眉毛、VL 嘴形分类粒度不足，双指标均未报警。

**闭环路径**（gap#2：open → research 通道 → 5 探针 → resolved）：
1. VL FACS 取证：被换图 = AU1+4+AU15 复合委屈；reactor 输出 = 中性抿嘴（6.5/10）
2. M11 三源研究：operator_found（FSRT/LivePortrait AU 级重演族）+ RH 零硬币核查 15 webapp 候选
3. 探针淘汰赛（5 负 1 正，全部入库 negative_result ×5）：
   - LivePortrait 静态驱动 → 零相对运动=保留源表情（身份 0.750 但表情不变）
   - LivePortrait 相对运动驱动（首帧中性+后段委屈）→ 跨人增量被运动归一化压制
   - qwen_swap 显式 AU 指令 → 身份坍塌（-0.17/0.03）：指令路线身份与表情约束互相挤占
   - qwen_edit 解耦编辑 → webapp 不稳（两次超时/FAILED，同 exp016 模式）
   - **平台负发现：remix 副本(workflow/copy)处于未保存态，create/getJsonApiFormat 均 810**
   - **✅ scail2 表情复刻 webapp 2072661793658462210：绝对表情模仿机制，驱动帧表情直接迁移**
4. **最终链 reactor→scail2：委屈还原 8/10（四图对比协议），身份 0.726，表情跟随 0.073**

**新方案 #16 `scail2_expression_chain`**（candidate，1/2 晋升输入）：两阶段 webapp 链 +
ffmpeg 静态驱动视频制备，route_json 已入库可回放。gap#2 → resolved。

**方法论沉淀**：**四图对比 VL 裁决协议**（目标/阶段1/探针A/探针B 同框打分）比单图评审灵敏
（单图判 lp2 中性，对比协议判 7.0）——AU 级表情评审应走对比协议。gallery :
8824（Tailscale 100.84.28.40:8824）。

### M11：外部研究通道三源 v1（2026-08-23）✅ session#1 全链闭环（gap#1 resolved）

**模块**（`research/`，纯 stdlib 零 key）：`external.py`（GitHub/ComfyUI Registry
`api.comfy.org/nodes/search`/HF 三源适配器 + 候选评分 + 机制句抽取）、
`session.py`（漏斗 collected→shortlisted→deep_read→mechanism→closed 全程落
research_sessions + external_fact 写卡 + RH webapp 零硬币核查）、`run.py`
（CLI：`python -m research.run --gap 1 --rh-check`）、`probe_webapp.py`
（通用 webapp 探针：上传双图+指令→跑→几何+VL 正确语义评审）。

**session#1 全链（gap#1 发型+表情 → resolved）**：21 候选 → 5 初筛 → qwen 深读
（GitHub StyleGAN 族 ×5 机制契合）→ **花硬币探针**（2 任务，M8 图对）→
gap resolved + 方案回写。**operator：FLUX.2 Klein 9B 指令双图编辑**
（webapp 2075052610570244098；零硬币阶段曾误判 img2img 模板库——**教训：
机制分类必须看暴露 inputNodes + UNET loader，不能只看节点类型清单**）。
实测：发型颜色/纹理/长度全跟 ref + 表情(嘟嘴)/身份(0.629)/场景全保 target
（VL 三图裁决；发色直方图 dark-on-dark 无区分度已记入 metrics 注记），
仅发丝/手指轻微伪影。**`expert_solutions.flux2_klein_hair`**（candidate，
family=hair_transfer，route_json=webapp step 形态待 M14 接线回放）；
晋升 validated 需 ≥2 不同输入。external_fact ×6 + verified_result ×1 入库
（verified_result 总数 23→24）。

### M15：专家方案层 + 知识缺口（2026-08-23）✅

**对齐总方案**《ComfyUI_Workflow_KB_专家方案与动态知识生长.md》（D 盘根目录）；
设计 `docs/M15_design.md`。原则：只加 L3（Expert Solution）与驱动对象，不动已有层。

**数据**（`kb/schema_m15.sql` + `kb/migrate_m15.py`，幂等）：
- `expert_solutions` **7 条种子**（M8 七路线）：hybrid_final / reactor_pure =
  validated，其余 5 条 candidate；`route_json` 与 ROUTE_CHAINS 同形状可直接回放
- `knowledge_gaps` 1 条 open（发型跟参考+表情跟底图，非指令路线）；
  `research_sessions` 空（M11 填）；`negative_result` ×2（探针勿投币 / 跨家族爆点）

**接线**（本次新增代码）：
- `kb/solutions.py`：检索（capabilities 位置加权词法评分，matched_caps 可解释）/
  `record_reuse` / `record_success`（**输入指纹去重** + 晋升检查）/
  `open_gap`（同题去重追加 known_failures）
- `webapp/orchestrator.py`：`_pick_solution` 前置——face_swap 任务先查方案，
  **命中零规划硬币**直接回放（弱信号/并列才用 LLM 复排，失败回退词法）；
  `_chain_for` 回放 route_json（方案可不进 ROUTE_CHAINS）；`_writeback` 三终态：
  satisfied→success_count+指纹+晋升，limited（能力不可达/kb_no_hit）→open_gap，
  缺输入 limited 与 error 不写
- `mcp/server.py`：`search_solutions` 工具（10→11，自测通过）

**晋升规则**（方差感知，写死在代码）：candidate→validated 需 ≥2 不同输入成功；
validated→expert 需 ≥3 真实任务 + limitations/key_params 已表征。
指标跨输入不可直接比（exp015 极差 0.063），故按成功次数不按指标数值。

**验证**：`test_m15_wiring.py` **23 checks 全过**（临时库副本，不动 kb.db）——
检索命中/零硬币复用留痕/route_json 回放/gap 登记（缺输入不误开）/negative 检索/
晋升双向触发。MCP `test_server.py` 11 工具通过。
**活例待跑**：首个真实换脸任务走复用路径；hybrid_final 差 2 个真实任务晋升 expert。

### M10：Web 前端 + 自主编排后端（v1）✅

**架构**（`webapp/`，端口 8830，绑定 0.0.0.0 走 Tailscale 可达）：
```
webapp/orchestrator.py   任务循环线程: planning(qwen-plus 规划) -> building/running
                         (swap_face 预设链/composer/RH) -> evaluating(auto_explore
                         几何+VL 双评审+规则诊断) -> review(等用户反馈) ->
                         修订(反馈分类->意图->路线切换) -> final(satisfied/limited/error)
webapp/app.py            ThreadingHTTPServer: / 静态UI + /api/task(POST/GET) +
                         /api/task/{id}/feedback + /api/task/{id}/workflow(下载) +
                         /img?path=(限 data/webtasks+data/swap)
webapp/static/index.html 零依赖前端: 需求+双图上传 -> 时间线 -> 结果图+指标 ->
                         反馈框[修订/达标] -> 结论+机制解释+工作流 JSON 下载
```

**路线链注册表** `ROUTE_CHAINS`：hybrid_final（reactor→klein单锚→LAB，默认）/reactor_pure/
klein_double/instantid_cfg/pulid_flux/qwen_swap/maskflux。反馈意图→路线映射：
expression→hybrid_final、color→klein_double、identity→reactor_pure、hair→pulid_flux。

**验证**（2026-08-22）：
- 零硬币路径：缺图任务 → 规划 LLM 正确分类 face_swap → limited + 补图指引
- 真实端到端（花硬币）：换脸任务 → reactor 执行 → 自动评审**正确触发色彩规则**
  （vl_color_harmony≤7）→ review 态 → 结果图 HTTP 服务 464KB → 达标反馈 →
  final：identity 0.682/expr 0.101/嘴形9 + LLM 机制解释（准确引用 inswapper
  128 分辨率潜空间不重生成光照的机制）+ 工作流清单（含 task_id/指标/预设链）
- 拼图安全：klein 步骤自动 extract_result_image 裁结果面板

**已知边界（v1）**：kb_generic 族只跑单图 webapp；反馈修订为路线级切换
（参数级微调在 M14）；任务态存内存+task.json 落盘（重启不恢复运行线程）。

**访问**：本机 http://localhost:8830 ；Tailscale http://100.84.28.40:8830

### M9：自主探索机制 v1（闭环 A）✅

**问题背景**：换脸测试暴露自主性缺口——色彩/表情问题靠用户目测发现，Klein/FaceFusion
方向靠用户领域知识给出。系统只自主完成了"方向→实现"中段。

**机制三层**（`53b08e4` + `1de278f`）：
1. `analyzer/auto_explore.py`：逐脸分类（拼图安全：host-copy=resid≥0.8 /
   ref-render=ident<0.3 / result=其余最高 ident）→ 几何+VL 双评审 → 规则匹配 →
   候选算子+可执行命令。**已接入 `swap_face.py run_swap` 默认路径**
2. `diagnosis_rules` 表 6 条：症状→机制假设→排序候选，全部带 evidence/status
3. `tech_families` 表 7 族：inswapper/InstantID/PuLID-Flux/Klein/VACE/Qwen-Edit/本地算子
   ——机制级知识（表情按构造保留 vs 扩散向均值脸松弛 vs 稠密逐帧条件）

**验证**：回放旧 icfg 输出（零提示）自动复现了用户会话中的完整诊断路径（色彩+嘴形
双规则触发→Klein/LAB/inswapper 建议）；reactor 端到端自动检出色彩弱点。
**校准**：VL identity 打分主观偏严（cos 0.74 给 6/10）→ 身份判定权归几何 cos 0.363 线，
VL 线降 5；VL 管几何看不见的语义维度（嘟嘴分类/色彩协调/光照方向）。

### M8：换脸任务管线（端到端实战）✅

**用户需求**：身份+发型跟参考图，表情跟被换图。**最终 final_v3 达标**（用户确认）。

**全路线终榜**（用户真实图对，身份差 cos 0.127）：

| 路线 | 身份 | 表情跟随 | 色彩/光照(VL) | 嘟嘴 | 结论 |
|---|---|---|---|---|---|
| instantid_cfg（扩散一阶） | 0.673 | 0.084 | 7/8 | ✗丢成微笑 | 表情向均值脸松弛 |
| final_v2（Klein 双锚） | 0.621 | 0.064 | 8/7 | ✓ | 色彩↑身份↓ |
| **run3 reactor（纯 inswapper）** | **0.741** | **0.032** | 7/6 | ✓ | 身份+表情双冠 |
| **final_v3（混合管线）** | 0.720 | 0.049 | **9/8** | ✓ | **最终采纳** |

final_v3 = **ReActor → Klein 单锚 → LAB 统一**。锚定次数-身份权衡实测：
0/1/2 锚 → 身份 0.741/0.694/0.599，色彩 7/8/9。

**沉淀的机制知识**（全部 verified_result 入库，共 23 条）：
- kps-slot 耦合定律：InstantID 族身份+表情经同一槽位锁死
- 发型-表情耦合定律：非指令路线发型与表情同源，`hair=True` mask 不迁移发型
- 表情传递机制：扩散重生成→均值脸松弛；inswapper 按构造保留；VACE 表情是输入不是推断
- 身份杠杆优先级：路线 > cfg > weight/denoise（后两者实测无效）
- Klein 拼图陷阱：debug SaveImage 输出 [结果|参考] 拼图，最大脸启发式会取错（LRN-002）
- 视频换脸表情好的机制拆解（用户提问驱动）

**工具与资产**：
- `swap_face.py`：19 预设一键流（上传→跑→逐脸评分→自动诊断→画廊）；`--wf reactor`
  走自拼 4 节点流（`data/api_format/_reactor_single.json`，从视频流提取 ReActorFaceSwap
  节点自拼——组合能力的直接证明）
- `analyzer/vl.py`：Qwen-VL 客户端（dashscope，`qwen-vl-max`；`.qwen_key`）
- `analyzer/vl_judge.py`：三图语义评审（六维+瑕疵+嘴形分类）
- `analyzer/color_match.py`：LAB 色彩统一算子（零硬币后处理）
- 画廊：本机 :8820（全量）、**Tailscale http://100.84.28.40:8821**（data/swap）
- `.learnings/`：self-improvement 日志（LRN-001 dashscope 模型名 403 / LRN-002 拼图取脸 /
  ERR-001 下载损坏 / FEAT-001~003）

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
| 工作流入库 | **208 条**（92 原始 + 76 定向 + 40 MiniMax H3；全部已解析 `data/graph/`） |
| 知识卡 | **208 张**（全覆盖；主库 geek 5★×3 4★×113 + H3 4★×31） |
| 知识条目 | **1873+ 条**：fact/inference 若干 + **verified_result 23**（M8 换脸实证 16 条为最大增量） |
| patterns | **1245 条**（1165 链 + 技术 signature + 65 边界挂点） |
| 探索机制 | **diagnosis_rules 6 条 + tech_families 7 族**（M9） |
| 技术覆盖 | FaceAnalysis×44, Inpaint×37, Upscale×36, Kontext×24+11编辑族, **InstantID×20**, ControlNet×19, Florence2×17, WanVideo×17, **PuLID×16**, BiRefNet×11, VACE×11, **OpenPose×6**, FaceDetailer×6, Klein×7, ReActor×2 |

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

- **M15 活例**：首个真实换脸任务走方案复用路径（零规划硬币）——hybrid_final 差
  2 个真实任务晋升 expert，是晋升机制的第一个活例
- **flux2_klein_hair 晋升验证**：第 2 个不同输入跑 `research/probe_webapp.py`
  （candidate→validated 需 ≥2 输入）；M14 给 orchestrator 接 webapp step 回放
- **组合管线机会**：reactor（换脸）+ flux2_klein（发型）串联——M8 完整需求
  （身份+发型+表情）可能一次达标，值得设计成一个 expert 方案
- **M10b 闭环 B**：宽泛提示解析器（"视频换脸比生图好"→ tech_families 机制差→改进假设）
- **M14 webapp 扩展**：反馈参数级微调（锚次数/GFPGAN）、kb_generic 视频任务、任务持久化恢复
- **B站/C站知识源方案等用户定**；web_search 工具待配 DEEPSEEK_API_KEY
- 夸张表情压力测试（用户待办；`swap_face.py --wf reactor` 自动诊断已就位）
- M13 边界羽化算子（Rope 式）——若夸张表情测试放大边缘伪影则提前
- H3 细分实验（`data/h3_report.md` §5）；MCP 11 工具已注册 DSH（+`search_solutions`，重启 DSH 生效）
- ~~git remote 仍未配置~~ → **已配置并首推**（`github.com/itsnone-liu/comfyui-workflow-kb`，`c2b9d92`，2026-08-23）

**关键命令**（cwd=820）：
```powershell
$env:PYTHONPATH=''
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" experiments\runner.py inputs <wf_id>
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" experiments\runner.py run <wf_id> --var <node.field> --arms a,b --image "<node.field>=<path>"
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" analyzer\composer.py compose upscale --base <wf_id> --run --metric
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" mcp\test_server.py   # MCP 11 工具自测
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" test_m15_wiring.py  # M15 验收(临时库)
```

**Token/key**：`.rh_token` 网页 token（采集用，~2026-09 中过期）；`.rh_apikey` 官方 Task API key
（已验证可用）；`.rh_sandbox_wf` 沙箱副本 workflowId（自拼流验证用，勿删）；
`.qwen_key` Qwen-VL key（dashscope 国内站，模型 `qwen-vl-max`——**`-latest` 别名 403 勿用**）。

**关键命令**（cwd=820，均需先 `$env:PYTHONPATH=''`）：
```powershell
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" swap_face.py --wf reactor --target in\target.jpg --ref in\ref.jpg --tag <名>   # 一键换脸+自动诊断
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" analyzer\vl_judge.py <输出图>            # 单图语义评审
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" analyzer\color_match.py <图> <基准图>     # LAB 色彩统一
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" analyzer\auto_explore.py <目录> --target <t> --ref <r>  # 回放诊断
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" serve_results.py --host 100.84.28.40 --port 8821 data\swap  # Tailscale 画廊
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" webapp\app.py --port 8830                    # 自主构建 Web 前端(浏览器开)
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" experiments\runner.py run <wf_id> --var <node.field> --arms a,b --image "<node.field>=<path>"
& "D:\AI-Teaching-Assistant\OpenTutor\apps\api\.venv\Scripts\python.exe" analyzer\composer.py compose upscale --base <wf_id> --run --metric
```

## 其他挂起事项

- OpenTutor 侧 3 个文件改动未 commit——用户知情，等用户决定。
- RunningHub 账号里的工作流副本：92 采集副本 + M4' 定向副本（~76）+ 1 沙箱副本（内容会被
  自拼图覆盖，属预期）——用户知情。
- web_search 工具未配置（缺 DEEPSEEK_API_KEY）——用直接 HTTP 探测 + GitHub 权威源替代。
- exp006 首跑因 outputs 解析 bug 浪费了 70 coins——已修复并用 taskId 恢复了全部指标。
- 组合流首跑教训：自猜 widget 输入名必被 ComfyUI 校验拒绝，必须走 `getJsonApiFormat`；
  云端 API 实例未必装了 rgthree 等 UI 辅助节点（prune_to_outputs 顺带解决）。
