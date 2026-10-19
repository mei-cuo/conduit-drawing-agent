# 输入样例与规则

- `examples/demo_scene.json`：合成教学数据。
- `examples/reference_scene.json`、`reference_ocr_manual.json`：人工转录的暂定参考数据。
- `examples/reference_drawing.png`：参考工程图纸。
- `examples/reference_ocr_paddle.json`：历史 PaddleOCR 实际结果。
- `examples/reference_agent_response.json`：与图纸和 OCR 摘要绑定的历史外部视觉代理响应。
- `examples/original_prompt.md`：原始识别提示词。
- `knowledge/`：依据提示词和样例整理的识别规则，不包含 Coze 内部知识库。

回放数据用于复现流程，不是自动识别准确率标准答案。参考工程图纸及其派生材料的来源授权未在仓库中提供，公开再分发前需由发布者确认。
