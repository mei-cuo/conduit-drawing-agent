# 输入与输出契约

## 图像与 OCR

输入支持 PNG/JPG/WebP 和 PDF。页面准备阶段将方向归一化并生成 p1、p2 等内部 ID。打印页号保存在结果字段中。

OCR sidecar 可参考 `examples/ocr.json`。多页输入格式：

```json
{
  "pages": [{
    "page_id": "p1",
    "sha256": "准备阶段页面 PNG 的 SHA-256，可省略",
    "evidence": [{
      "evidence_id": "p1-ocr-1",
      "kind": "ocr",
      "page": "p1",
      "text": "K116+266",
      "bbox": [100, 100, 230, 140]
    }]
  }]
}
```

页号集合必须与图像一致，证据 ID 全局唯一，坐标为原图像素。提供 sha256 时严格匹配准备后的页面内容。

PaddleOCR HTTP 适配器接收 `POST /ocr`：

```json
{"image_base64":"不带 data URL 前缀的 PNG Base64"}
```

返回：

```json
{"width":900,"height":420,"lines":[{"text":"K116+266","bbox":[0.1,0.2,0.3,0.3],"confidence":0.98}]}
```

服务 bbox 是裁剪图上的归一化坐标，客户端再映射回整页像素。项目所带适配器实现此契约。

## 结果与内部对象

results.json 为固定 16 字段数组，与原领域规范一致。Evidence、Candidate 和 DeviceRelation 保存在 evidence.json：

- Candidate 原始名称、标注组和符号区域独立保存。
- field_evidence 将中文业务字段关联到当前页证据 ID。
- neighbor_ids 只记录其他已识别管井 ID。
- DeviceRelation 记录设备名称、桩号、距离、关联依据及证据引用。
- 多设备字段按同一列表顺序使用中文分号拼接。

## 状态与退出码

| 状态 | CLI 退出码 | 含义 |
|---|---|---|
| completed | 0 | 完成导出 |
| awaiting_review | 2 | 已保存检查点，等待复核 |
| rejected | 3 | 复核驳回 |
| 错误 | 1 | 输入、配置、依赖或执行失败 |

API 同步调用返回状态；等待复核时也返回 HTTP 200 和 awaiting_review。完成前请求 results 端点返回 409。

## 人工复核

`approved` 必须为 JSON 布尔值；`reviewer` 和 `reason` 均为非空文字。corrections 中每项给出 object_id、中文字段名、新值及 evidence_ids。修订后重新检查全部证据。memories 可显式提交 convention / review_policy，项目 ID 继承原任务。
