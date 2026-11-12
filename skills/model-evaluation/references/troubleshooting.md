# 评测与评分排障

| 现象 | 优先证据与处理 |
|---|---|
| AISBench连localhost失败 | localhost是客户端网络命名空间；跨机填实际node0管理IP，并设置NO_PROXY |
| warmup失败后仍显示evaluation | 不代表有效结果；核对逐请求成功数、失败文件和评分是否基于本轮答案 |
| KeyError generation_kwargs | 配置至少留{}；采样默认值看客户端、模型generation_config和服务配置 |
| --models/--seed command not found | 前一行漏续行或反斜杠后有空格/注释；用单行命令先纠正Shell语法 |
| tee日志空/路径异常 | 提前结束的AISBench不在后续tee管道；先mkdir，路径前不多写$，确认WORK/RUN赋值 |
| 输入不是16K、输出不足1K | max-model-len不是输入生成器；模板和真实usage需核对，ignore_eos/max_out_len传递及数据字段优先级需查 |
| prefix caching没到0.9 | 共享前缀不是实际命中，核对各DP预热、块大小、逐出、metrics差值和重复整条命中 |
| 分数低/回答乱码 | 分开检查预算截断、语义答错、异常字符/重复、思考标签后处理；请求success不代表答对 |

## 多模态与独立judge

- 图片请求400：读取HTTP响应body；核对图片根目录、visual_input=1/2、媒体白名单真实存在、prompt+输出预算及模型名。不要拿OCR路径替代Hallusion路径。
- Hallusion evaluation长时间无进度：检查是在调用judge还是推理，旧版utils可能吞异常无限重试；402是judge余额不足，401是凭据问题，不能靠重启HY4解决。
- 停vLLM后仍评分：若模型回答已保存且judge为外部API，评分不依赖vLLM；保留客户端容器和评分进程，不全局杀Python。
- 完整性、评分字段与具体恢复边界见[多模态测试](multimodal.md)。
