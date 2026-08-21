# MiniMax H3（海螺 Hailuo H3）细分领域报告

> 生成于 2026-08-22 · 40 条定向采集（webapp 搜索渠道：`MiniMax H3` / `海螺H3` / `Hailuo H3` / `H3`）
> 采集器 `collector/batch_h3.py`，标题锚定 h3/minimax/海螺/hailuo，全部带 webapp（可直接云端执行）

## 1. 两条集成路线（库内实证）

| 路线 | 代表节点 | 特征 |
|---|---|---|
| **原生 T8 本地推理** | `MiniMaxH3ReferenceToVideo`×18、`MiniMaxH3ImageToVideo`×11、`MiniMaxH3AVDecodeT8`、`MiniMaxH3BlockCacheT8`、`MiniMaxH3DualClockSamplerT8`、`MiniMaxH3AudioConditioningT8`、`MiniMaxH3SigmaShift` | 社区 T8 压缩版节点族；配 `MemoryEfficientSageAttentionPatch`×17 显存优化；图更大（中位 ~25 节点，最大 132） |
| **RH 官方 API 封装** | `RH_MinimaxHailuoH3ImageToVideo`×4、`RH_MinimaxHailuoH3TextToVideo`×3 | 单节点封装整条管线，图极小（最小 4 节点：Load→RH→Save），无本地显存需求 |

社区增强件：`PT_H3ConcatAVLatent`（音视频 latent 拼接）、`VRGDG_MiniMaxH3AudioDrive`（音频驱动）、`RTXVideoSuperResolution`（超分输出）。

## 2. 任务面覆盖（按标题归面，40 条）

| 面 | 条数 | 说明 |
|---|---|---|
| 加速/量化版 | 16 | 4步/8步/量化/极速/Turbo/SageAttention/TeaCache——**该细分最强演化轴** |
| 图生视频 | 15 | 单图参考生视频（含 9图3视频3音频"全能参考"） |
| 多图/全能参考 | 9 | 多图一致性角色/场景参考 |
| 首尾帧 | 8 | 首帧/首尾帧插值控制 |
| 音频参考/音色克隆 | 6 | 参考音频 + 声音克隆 |
| 文生视频 | 4 | |
| 对口型/数字人 | 3 | lip-sync、单人数字人 |
| 提示词反推/扩写 | 2 | 自动反推参考图提示词 |
| 高清/放大 | 2 | 2K/4K 输出管线 |
| 视频编辑/换装 | 1 | 角色替换/换装 |

图规模：4–132 节点（中位 25）——原生路线大图，RH 封装路线小图。

## 3. 与主库（人像一致性细分）的关系

- 视频生成能力从 18 条（wan/LTX/VACE）扩展为 **58 条**（+40 H3），H3 是当前平台最活跃的视频模型
- 交叉点：H3 换装/角色替换流（1 条编辑类）= 主库"换装"能力（28 条）的视频化路径
- 加速技术沉淀（TeaCache×14、SageAttention、BlockCache、双时钟采样、SigmaShift）对主库视频流同样适用——**可移植段的新来源**

## 4. 卡片层洞察（40 张卡全部生成，4★×31 / 3★×3 / 1★×5 / 0★×1）

知识密度：步数/加速知识提及 119 处、显存/量化方案 189 处、分辨率/时长 197 处、
音频能力 191 处——**该细分的知识核心是"质量-成本-显存"三角**。

代表性特殊结构（卡片 special_features 摘录）：
- **两段式渐进采样**：3 步 beta scheduler 粗采 → H3SigmaRefiner 8 步 euler 精修（8步加速流）
- **多底模矩阵**：4 个 UNETLoader 并列（FeiHou_MiniMax-H3_Remix / 10Eros 系）+ 6 个 LoRA 加载器
- **双管线并行**：I2VA 与 Ref2VA 两条 H3 管线共存，mode4 后缀切换
- **多级分割编辑**：SAM3 视频分割 + SeC 语义分割 + PointsEditor 人工点选 + BiRefNet（局部编辑流）
- **Get/Set 参数中枢**：35 GetNode + 31 SetNode 管理 9图/3视频/3音频输入矩阵
- **rgthree Any Switch + Fast Groups Bypasser**：素材分组旁路（素材不齐也能跑）

## 5. 实验与移植（进展）

- **h3_boost 配方已验证（2026-08-22）**：`compose h3_boost --base 2090636870803103746`
  把 `MiniMaxH3MemoryEfficientSageAttentionPatch`（源 2085772872768839681）插入无加速
  底座的模型管线（UNET→Lora→SigmaShift→**Patch**→BasicGuider），云端 SUCCESS 出视频。
  声明式引擎首个零代码新增配方（recipes.json 加一段 JSON）。
- **exp020/021/022 步数扫描完成（#1852）**：固定种子，steps 4/8/20 → 帧间身份稳定性
  **0.248 / 0.159 / 0.364**，清晰度 195/85/97。**4/8 步加速版牺牲帧间身份稳定**
  （4 步帧稳但模糊、8 步漂移最糊、20 步满血最优）；固定种子重跑 stability 仍差 0.02
  （平台非完全确定），清晰度几乎复现（85.0/85.1）。新 `--video` 实验模式
  （VideoComparator：帧间身份/清晰度/运动量）自此可用。

实验候选（每臂成本按视频任务估 ~2-4× 图片臂，先 dry-run + 探针）：

1. ~~**步数扫描**~~ ✅ exp021/022（4/8/20 完成）
2. **量化 vs 全精度**：int8/T8 量化版 vs 满血全精度无损版（库内两版都有现成流）
3. **多参上限**：3图 vs 9图参考的一致性增益
   （方法学：固定 noise_seed + 视频指标；单臂 805 疑瞬时故障，重复臂即可补）
