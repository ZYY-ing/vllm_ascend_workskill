---
name: model-evaluation
description: 对已部署模型运行 AISBench 文本精度性能、HallusionBench并发推理与独立API裁判、OCRBench V2，并核对token、缓存、截断和答案提取。适用于模型测试、评分复核和测试并发排障，不默认重启或重编译模型服务。
---

# 模型评测与评分复核

先确认已部署模型、API、数据版本、样本范围、输入输出预算、客户端并发、采样及缓存条件。复用现有测试环境、已完成结果和在途任务；不把编译或部署视为测试请求的默认步骤。

## 按任务读取

| 任务 | 参考 |
|---|---|
| AISBench 安装、配置、精度与性能验收 | [AISBench](references/aisbench.md) |
| 精确token、固定输出与公共前缀 | [定长数据](references/datasets.md) |
| 视觉权重和图片请求的基本检查 | [多模态服务](references/multimodal.md) |
| Hallusion数据、请求字段与计分原理 | [HallusionBench](references/hallusionbench.md) |
| Hallusion完整执行入口、并发与裁判恢复 | [并发测试与评分](references/hallusion-concurrency-api.md) |
| OCRBench V2的数据、配置与全量验收 | [OCRBench V2](references/ocrbench-v2.md) |
| 输出预算、默认采样与安全并发 | [生成配置](references/generation-settings.md) |
| 思考标记、最终答案与GPQA提取 | [答案提取](references/answer-extraction.md) |
| 评测连接、输出和独立裁判异常 | [评测排障](references/troubleshooting.md) |

## 口径与边界

服务health不等于图片或长上下文通过。确认真实请求结构、模型ID及最终答案后才运行授权负载；性能、精度和profiling不混跑，正式样本的预热/冷缓存按用户要求处理。

保留原始响应、usage、finish_reason、样本ID、提取结果和实际采样配置。区分客户端并发、服务端调度批次和KV驻留能力；没有usage时不把缺失算0，不以文本长度代替生成token。

思考模型先查权重模板和API是否分离reasoning；核对提取值是否真来自最终答案，未完成推理不能猜选项。数学、OCR外文和题目本有符号不能直接判乱码。记录失败、截断、部分样本和评分分母，不以退出0/进度100%当全量成绩。

Hallusion推理只发送问题和必要图片，不发送参考答案；外部裁判是独立阶段，涉及真实API费用，仅按用户要求执行。评分缓存只在输入、裁判模型、地址、官方提示词与规则一致时复用；失败保存在途成功结果，不无限重跑。密钥隐藏输入或私有环境传递，不写进脚本、缓存身份或日志。

命令位置和工具见对应参考；`scripts/`为运行工具，`tests/`为离线行为验证。运行目录在用户指定项目下，不在技能目录写入数据、结果或凭据。
