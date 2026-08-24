# M16 设计：验证层增强 + 反馈一等公民

> 创建：2026-08-24。触发：用户系统评价（v2 实验后）。
> **实现状态：A1/A2/B/C 全部落地并回归（同日晚）。见 §6。**

## 6. 实现结果与关键发现（2026-08-24 晚）

### 落地清单
| 件 | 文件 | 状态 |
|---|---|---|
| A1 AU 通道 | `analyzer/au_geometry.py`（MediaPipe Tasks blendshape，52 AU 分数） | ✅ 回归通过 |
| A1 校准回归 | `analyzer/au_regression.py` + `data/arbiter_regression.json` | ✅ 常设工具 |
| A1 环境隔离 | `.venv-kb`（uv + cpython3.12 + mediapipe==0.10.35 + face_landmarker.task） | ✅ 与 OpenTutor venv 隔离，子进程桥接 |
| A2 仲裁器 | `analyzer/vl_arbiter.py`（VL 语义 + AU 几何双通道 + 分维度信任表 + 升级规则） | ✅ 离线+在线回归 |
| B 反馈路由 | `kb/feedback.py` 四分类 + `webapp /api/task/{id}/feedback` 接线 | ✅ 三类真实反馈测试 + 冒烟 |
| C 知识宿主 | `kb/schema_m16.sql` → capability_notes/user_rulings 表 + 存量迁移 6 条 | ✅ |

### 关键发现（已入库 capability_notes）
1. **AU 通道在眼/嘴维与用户裁决三次吻合**：LP"表情更强"=pucker 过冲 2.4×；"双链眼微睁"=欠闭 0.35；scail2 v1 嘟嘴保真 0.350/0.333 → 这三维 trusted。
2. **眉维 contested（最重要发现）**：v2 用户裁 scail2 皱眉更好，但 VL 语义（LP 7:5）与 blendshape 几何（knit 0.426:0.260 vs 目标 0.465）**双机器通道一致偏 LP**。分量分析：scail2 是唯一 browDown>0 的输出——人感"皱眉"≈browDown+眉间纹理，browInnerUp 读作"悲伤"。→ 规则：眉维主导时必须用户仲裁。
3. **帧稳定性**：链输出 3 帧方差小，单帧比较可用（排除了帧选择偏差解释）。
4. **仲裁升级规则**（v2 教训代码化）：双通道分歧→用户；目标表情由争议维主导（top-1 或 top-2 且激活≥0.35）→用户（即使双通道一致）；TIE_MARGIN=0.05（agg|Δ|差小于此=感知平局）。
5. **在线回归**：v2 案 auto=prefer_a 与用户金标准一致（旧单通道偏 LP）；v1 keep_both 语义与链内偏好兼容。

### 遗留（下轮）
- BARS 未加 AU 阈值（需更多校准例避免误报）；眉维几何改进（纹理/眉间线检测）→ gap#3 后续
- capability_notes 的 UI 呈现（webapp 只读视图）；user_rulings few-shot 校准 VL prompt

## 0. 问题陈述（三次实证失准，均已入库）

| 案例 | 失准 | 证据 |
|---|---|---|
| v1 glm 单图 | LP 输出判"中性"，实际表情已迁移 | auto_1787576849 + 用户校准 |
| v2 qwen 四图对比 | 判 LP 7.0 / scail2 5.0，用户裁决相反（皱眉 scail2 优） | 20260824 双链 |
| v2 glm 单图 | 判 scail2"眉毛未皱起"，用户判皱眉更优 | 20260824 双链 |

共性：**纹理级 AU（皱眉、眼睑微睁）超出当前双通道（5 点几何 / VL 单模型）的分辨力**。
gap#3 已登记（required: au_level_geometry / multi_model_arbitration / user_calibration_loop）。

## 1. Track A：验证层增强（解 gap#3）

### A1. AU 几何指标（密集关键点，零硬币确定性）

新模块 `analyzer/au_geometry.py`：
- 密集关键点模型（MediaPipe FaceMesh 468 点或 68 点 ONNX，与 YuNet/SFace 并存）计算：
  - **EAR** 眼纵横比 → AU43 闭眼/微睁（v2 用户提到的"眼睛微睁"正是此维度）
  - **MAR** 嘴纵横比 → AU25/26 张口程度与形状
  - **眉内端高度**（眉心点 vs 眼眶基准）→ AU1/AU4 皱眉（当前完全盲区）
  - 头姿（复用现有）
- 输出形式：`au_delta_vs_target`（输出图与被换图的各 AU 几何差），接入
  `auto_explore.py` 作为一级指标；阈值用 v1/v2 已有图对标定。
- 价值：皱眉/闭眼这类**纹理+几何复合 AU**，几何通道给出确定性下界，VL 只补语义。

### A2. 多模型仲裁协议

新模块 `analyzer/vl_arbiter.py`：
- 双通道独立评审：qwen-vl-max 四图对比协议 + 第二通道（不同 prompt 变体或第二模型）
- 分歧度 > 阈值（如排序相反）→ 标记 `contested` → **自动升级用户仲裁**，不再给单一结论
- 回归测试集：v1/v2 三次失准案例 + 用户裁决做金标准

### A3. 用户校准环（判定权数据化）

- 用户裁决持久化为标注对 `(target, output, chain, verdict)` —— `user_rulings` 表
- 用途：① VL prompt 的 few-shot 校准例子；② 定期测各 VL 模型偏差（哪个对皱眉最灵）；
  ③ 判定权规则显式化：**纹理级 AU → 几何+用户；强度/风格 → VL；contested → 用户**

## 2. Track B：反馈一等公民（feedback router）

新模块 `kb/feedback.py`——用户反馈四分类路由：

| 类型 | 例 | 路由 |
|---|---|---|
| verdict（裁决） | "这次 scail2 更胜一筹" | record_success/failure + 晋升检查 + 择优规则更新 + user_rulings |
| operator lead（工具线索） | "DeepLiveCam 有参考价值" | 自动建 research session（具名查询 GitHub/Registry/HF）+ external_fact（本次已手工演示） |
| meta-capability（能力评价） | "细节识别要加强" | 按域（generation/verification）开 knowledge_gap → 驱动 Track A 类改进 |
| new requirement | "再做个实验" | 任务规划 |

接线：`webapp /api/task/{id}/feedback` 端点扩展分类字段；CLI 同步。
M10b 的"宽泛提示解析器"可复用此分类器。

## 3. Track C：知识域扩展（验证环节知识的宿主）

现状：knowledge_items 挂 workflow 卡（生成域）——验证环节知识（AU 阈值、VL 模型偏差、
仲裁规则）没有自然宿主。方案（择一）：
- 新表 `capability_notes(domain, topic, content, evidence, confidence)`，
  domain ∈ {generation, verification, orchestration}
- 或 tech_families/diagnosis_rules 扩展 verification 族

原则：**验证环节的知识与生成环节同构生长**（可检索、可沉淀、可被 M11 研究通道更新）。

## 4. 落地顺序（建议）

1. A1 AU 几何（收益最大、纯本地、可立刻用 v1/v2 案例标定）
2. A2 仲裁协议（有现成冲突案例做回归）
3. B feedback router（本次手工路由的机制化）
4. A3 校准环 + C 知识域（随案例积累生长）

## 5. 本次已完成的前置动作

- scail2_expression_chain → **validated**（2 输入晋升，M15 晋升机制首个活例）
- lp_expression_chain 注册 candidate #17（双链保留策略，route_json 含择优规则）
- v2 用户裁决 + 三次失准实证入库；gap#3（验证层缺口）开启
- Deep-Live-Cam 线索入库 external_fact（★96k，视频换脸 family 候选）
