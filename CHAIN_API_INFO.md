# 换脸三段链（身份+发型+表情强度）· RH 工作台工作流 API 信息

> 生成于 2026-08-27 · 项目 820 · 由 dsh 制作
> 交付链 = hairchain_B v2：reactor → Klein 发型迁移 → scail2 表情复刻
> 质量基准（in/ 图对实测）：身份 0.584-0.675（线 0.363）· 表情跟随 0.026-0.05 ·
> 发型三要素全跟参考（VL 裁决）· 表情强度 AU 三主维全面恢复（BL-009 修复版）

## 三段工作流标识

| 段 | 用途 | **workflowId**（/task/openapi/create 用） | webappId（ai-app/run 替代形态） |
|---|---|---|---|
| **段1** | 换脸（身份跟参考/表情跟被换图） | `2092594001879216130` | —（自拼图，无 webapp） |
| **段2** | 发型迁移（发型跟参考，其余全保） | `2092820988747919362` | `2075052610570244098` |
| **段3** | 表情复刻（强度恢复，可选段） | `2092820995869847553` | `2072661793658462210` |

三段均已：工作台可见可编辑 · getJsonApiFormat 放行 · 编辑器首跑 SUCCESS。
来源：段1 自拼（ReActor 环境宿主 2005804455352303618 副本）；段2 源流
「发型迁移-假发模特」2075048347282526209；段3 源流「scail2表情复刻+
表情模仿」2072570517835575298。

## 输入映射（nodeInfoList）

### 段1 reactor（wf 2092594001879216130）
| nodeId | fieldName | 类型 | 填什么 |
|---|---|---|---|
| `1` | `image` | IMAGE | **被换脸图**（表情/姿势/场景来源） |
| `2` | `image` | IMAGE | **参考人像**（身份+发型来源） |

### 段2 Klein 发型迁移（wf 2092820988747919362）
| nodeId | fieldName | 类型 | 填什么 |
|---|---|---|---|
| `597` | `image` | IMAGE | **image1 = 段1输出图**（被编辑） |
| `598` | `image` | IMAGE | **image2 = 参考图**（发型来源，与段1的 2 同图） |
| `500` | `text` | TEXT | 指令（已验证模板，**勿随意改写**）：`把图一中人物的发型替换成图二人物的发型，严格保持图一人物的脸部、表情、姿态、服装、背景和光线完全不变。` |

注意：指令里**不要**追加"表情强度不得减弱"类约束——实测表情过冲 3 倍且身份
坍塌至 0.369（negative_result，KB 已录）。表情强度问题交给段3。

### 段3 scail2 表情复刻（wf 2092820995869847553）
| nodeId | fieldName | 类型 | 填什么 |
|---|---|---|---|
| `68` | `image` | IMAGE | **image = 段2输出图**（身份/发型载体） |
| `2` | `video` | VIDEO | **驱动视频 = 被换脸原图制备**（见下） |
| `85` | `value` | INT | 生成秒数，推荐 `8` |
| `88` | `value` | INT | 分辨率，推荐 `1024` |

**驱动视频制备（本地 ffmpeg，零币）**——表情来自驱动帧本体，须用被换脸原图：

```bash
ffmpeg -loop 1 -i 被换脸原图.jpg -t 2 -r 10 -pix_fmt yuv420p -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" driver.mp4
```

段3 输出为 **zip（内含最终图片）+ mp4** 双产物（2026-08-27 定稿，见下节）；

> **⚠️ 2026-08-27 晚事故修复（重要）**：段3 UI 曾带原作者**演示图**默认输入，
> 编辑器跑 / API 不传 nodeInfoList 时会吃演示图 → 直出图人物完全不对
> （identity_vs_ref 仅 0.07-0.11，vs 被换图反而更高）。**工作流接线本身无
> 问题**（IMG_PICK 300 ← GIMMVFI 130 与视频同源，用户实跑 zip 图 0.629-0.665）。
> 已修复：UI 默认输入改为正确样例（node68=klein_0.png 哈希 67561ae0…、
> node2=driver.mp4 哈希 408dca78…），并以显式传参重跑过身份门禁
> （任务 2092977881955442690，zip 图 identity_vs_ref=0.5971 ≥0.55 PASS）。
> **协议升级：直出图/zip 验证必须打身份分（FaceComparator vs ref ≥0.55），
> 禁止只验"zip 里有 PNG"（内容盲检）**。

```bash
ffmpeg -i out.mp4 -vf "select='eq(n\,6)+eq(n\,10)+eq(n\,14)'" -vsync vfr frame_%02d.png
```

## 通用调用协议（.cn/.ai 同后端）

```
上传   POST /openapi/v2/media/upload/binary   (multipart 字段 file)
       -> 返回 data.fileName 作为 fieldValue
工作流 POST /task/openapi/create
       {"workflowId": "<上表>", "apiKey": "<key>",
        "nodeInfoList": [{"nodeId":"...","fieldName":"...","fieldValue":"..."}]}
webapp POST /task/openapi/ai-app/run          (同样式, webappId 代替 workflowId)
状态   GET  /task/openapi/status?apiKey=&taskId=     (完成态返回裸 "SUCCESS")
输出   GET  /task/openapi/outputs?apiKey=&taskId=    (完成态返回 LIST [{fileUrl,...}])
```

**路径注意**：Task API 基址 `https://www.runninghub.cn`，**无 `/api` 前缀**
（带前缀会 TOKEN_MISSION/TOKEN_INVALID——不是 key 的问题，是路径的问题）。

## Python 一键驱动（项目 820 封装）

```python
import sys; sys.path.insert(0, r"<820路径>"); sys.path.insert(0, r"<820>/experiments")
from experiments import rh_task
key = rh_task.load_api_key()          # 读 820/.rh_apikey

# 段1
u_t = rh_task.upload_file(key, "被换脸.jpg"); u_r = rh_task.upload_file(key, "参考.jpg")
t1 = rh_task.run_workflow(key, "2092594001879216130", [
    {"nodeId": "1", "fieldName": "image", "fieldValue": u_t},
    {"nodeId": "2", "fieldName": "image", "fieldValue": u_r}])
o1 = rh_task.wait_task(key, t1, poll=8, max_wait=600)
p1 = rh_task.download(rh_task.collect_file_urls(o1)[0], "step1.png")

# 段2
u1 = rh_task.upload_file(key, "step1.png")
t2 = rh_task.run_workflow(key, "2092820988747919362", [
    {"nodeId": "597", "fieldName": "image", "fieldValue": u1},
    {"nodeId": "598", "fieldName": "image", "fieldValue": u_r},
    {"nodeId": "500", "fieldName": "text",
     "fieldValue": "把图一中人物的发型替换成图二人物的发型，严格保持图一人物的脸部、表情、姿态、服装、背景和光线完全不变。"}])
o2 = rh_task.wait_task(key, t2, poll=8, max_wait=900)
p2 = rh_task.download(rh_task.collect_file_urls(o2)[0], "step2.png")

# 段3(先本地制 driver.mp4, 再上传)
u2 = rh_task.upload_file(key, "step2.png")
uv = rh_task.upload_file(key, "driver.mp4")
t3 = rh_task.run_workflow(key, "2092820995869847553", [
    {"nodeId": "68", "fieldName": "image", "fieldValue": u2},
    {"nodeId": "2",  "fieldName": "video", "fieldValue": uv},
    {"nodeId": "85", "fieldName": "value", "fieldValue": "8"},
    {"nodeId": "88", "fieldName": "value", "fieldValue": "1024"}])
o3 = rh_task.wait_task(key, t3, poll=8, max_wait=900)
# 段3 返回 zip(最终图片在内) + mp4(动态佐证); 按后缀取用
urls = rh_task.collect_file_urls(o3)
z = next(u for u in urls if u.endswith(".zip"))
rh_task.download(z, "final.zip")     # 解压即最终图片
```

### 段3 输出 = 压缩包，无预览节点（2026-08-27 定稿）

- 终端节点 `ZIP_OUT(CompressImages, 节点302)`：吃 `IMG_PICK
  (ImageFromBatch, 节点300, batch_index=14)` 的最终帧，打包成
  **zip**（内含 image_00000.png ≈1MB）；prefix `scail2_final`，
  支持 password 选项
- 附带 mp4（VHS_VideoCombine，动态佐证，非预览节点）
- **图内无任何预览节点**（ShowText 已删；段1/段2 本就干净）
- 换抽帧位：编辑器改 IMG_PICK 的 `batch_index`（0 基；6/10/14 备选）
- 历史沿革：初版出 mp4→ffmpeg 本地抽帧；二版内置 SaveImage 直出
  PNG；本版按需改为 zip 终端（任务 2092888227938611202 验证，
  zip+mp4 双产物，apiFormat 39 节点）
- 踩坑备查：手工造节点输入名必须严格对准节点定义
  （ImageFromBatch 是 `image`，CompressImages 是 `images or video_path`），
  错名分支被静默丢弃——setContent 后 getContent 回读 inputs 可零币自查

webapp 替代形态（不需要工作台副本、无 810 概念，效果同源）：
段2 `rh_task.run_webapp(key, "2075052610570244098", node_info)`、
段3 `rh_task.run_webapp(key, "2072661793658462210", node_info)`，node_info 同上表。

## 成本与时长（实测）

| 段 | 单次成本 | 时长 |
|---|---|---|
| 段1 | ~10 币 | 30-90 s |
| 段2 | ~35-80 币 | 60-170 s |
| 段3 | ~50-100 币 | 100-160 s（8s 视频） |

整链 3 任务 ≈ 4-6 分钟。只要两约束（不要求表情强度）可省段3。

## 解锁记录（810 门槛）

| 副本 | setContent V1 | 编辑器首跑 | gate |
|---|---|---|---|
| 段2 klein | versionId 2092823337876619266 | task 2092823688720703490 SUCCESS (png) | OPEN (32 节点) |
| 段3 scail2 | versionId 2092823346336530434 | 编辑器 Run 触发 Generating → SUCCESS | OPEN (38 节点) |

经验：810 = NOT_SAVED_OR_NOT_RUNNING，**编辑器保存/setContent 不够，必须
成功跑过一次**；编辑器加载检测用顶栏 "Save manually"/FPS 信号（canvas 计数
失效——新版编辑器无 canvas 标签）。
