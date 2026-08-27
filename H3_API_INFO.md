# H3 双采文生视频 · RunningHub 工作台 API 信息

## 工作流

- **workflowId**: `2092847765977378817`（账号内云端副本，已定稿烤入）
- 编辑器: https://www.runninghub.ai/workflow/2092847765977378817
- 形态: 49 节点，**零预览节点**；终端 = SaveVideo(mp4) + CompressImages(zip)
- 当前 UI 默认: 时长 10s / 放大 1.2x / 提示词 = 现代纪实反AI感版（KB 卡 209 模板档3）

## Task API

```
POST https://www.runninghub.cn/task/openapi/create
Content-Type: application/json

{
  "apiKey": "<你的 apiKey>",
  "workflowId": "2092847765977378817",
  "nodeInfoList": [
    {"nodeId": "138", "fieldName": "value", "fieldValue": "<提示词，四段结构>"},
    {"nodeId": "132", "fieldName": "value", "fieldValue": "10"},
    {"nodeId": "182", "fieldName": "value", "fieldValue": "1.2"}
  ]
}
```

### 输入参数（nodeInfoList 覆盖）

| nodeId | 字段 | 说明 |
|---|---|---|
| 138 | value | **提示词**（必填）。四段结构: `subject_definitions:`（人物定义）/ `summary:`（[reference generation]+场景一句话）/ `retention_analysis:` / `detailed_description:`（摄影语言）。风格完全由此决定——写实/纪实模板见 KB 卡 209 |
| 132 | value | 时长秒数，1–10 |
| 182 | value | 二采放大倍率。**1.2 稳**；1.25 在 default 实例临界（同配置可能 OOM）；1.5 必 OOM |

### 轮询与产物

```
POST /task/openapi/status   {"apiKey","taskId"}          → 裸字符串 RUNNING/SUCCESS/FAILED
POST /task/openapi/outputs  {"apiKey","taskId"}          → 成功后调用（未完成时调会报 805）
```

- 产物 2 个：`video/MiniMax_H3_*.mp4` + `h3_video_*.zip`（**zip 内含最终视频 comfy_video_000.mp4，取 zip 即可**）
- 10s/1.2x 实测 ≈ 500–670s，1504×864、24fps、10.125s

### 注意

- 提示词与写实度的关系、反AI感配方、三档风格模板全在知识库**卡 209**（prompt_template）
- 平台节点坑：CompressImages 的 `images or video_path` 槽吃 **IMAGE 张量或 VIDEO 对象**，不吃远程 URL 字符串（SaveVideo 的 video_url 喂进去 ValueError）
