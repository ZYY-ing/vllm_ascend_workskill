# 多模态：HallusionBench 与 OCRBench V2

用于视觉权重、数据准备、独立Hallusion推理/judge及AISBench OCR测试。本文参数是示例或核实后的模型推荐，不是任意模型的固定设置。真实IP、容器、目录、版本、采样和成绩写项目RUNBOOK，不写入可公开分发的技能。

## 服务与权重

1. 检查config架构、processor/tokenizer、视觉编码器、连接/投影层，以及safetensors索引和分片是否确实含视觉张量；不能只凭架构名字认为图片权重完整。多节点分别检查文件可见性与关键文件hash。
2. `--language-model-only`会禁用多模态；去掉它，并在版本支持时按负载设置`--limit-mm-per-prompt '{"image":1,"video":0}'`。该参数只是输入限额，不会生成缺失的视觉权重，也不证明服务已适配目标VL架构。
3. 量化语言权重与原精度视觉组件能否混用，须确认同一模型版本、张量映射、量化规则及后端实现。不要默认拼接、建别名或修改metadata；模型路径保持原样。
4. 用真实图片验证OpenAI兼容请求。文本curl、health或显存占用不能证明视觉推理通过。依次验收模型ID、图片请求成功、有效最终答案，再执行授权的测试。
5. `--allowed-local-media-path`按实际所需目录配置，路径必须在容器内存在。某些版本即使发送Base64也会在媒体处理阶段检查白名单目录；按400响应body定位，不当作所有版本的通则。


流程入口：[HallusionBench](hallusionbench.md)、[OCRBench V2](ocrbench-v2.md)。采样和输出预算见[生成配置](generation-settings.md)，并发和恢复见[Hallusion并发与评分](hallusion-concurrency-api.md)。
