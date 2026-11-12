# 从部署到评测的完整工作流

从用户指定的服务器、模型和目标出发，完成所需阶段。使用中文解释，命令保持官方教程式简洁；本技能可由具备终端、SSH和文档读取能力的agent使用，不依赖某个桌面应用或专用连接器。

用户明确使用NVIDIA H200/CUDA时，读取[H200源码编译与服务学习文档](../skills/vllm-cuda-ops/references/h200-source-build.md)，不套用下文Ascend专属设备、量化及通信参数。权重下载流程可复用。

## 开始工作

1. 环境信息优先级：本轮用户明确指定 → 用户提供的环境资料或本技能目录的 `environment.local.md` → 用户已使用的 `~/.blue_server_toolkit/config.json` 中可匹配项。Blue配置仅作可选、只读数据源，不要求安装Blue Toolkit或执行其脚本；映射方式见[环境示例](../skills/vllm-ascend-ops/assets/environment.example.md)。没有时从已有SSH配置及当前会话补齐，只问确实缺少的信息。冲突时不静默混用两台机器的字段。不读取私钥内容，不将密码或Token写进技能。
2. SSH只读确认目标机器、NPU型号、容器、可用设备与项目目录。复用已有环境；不因默认示例不同重建容器或重装软件。
3. 从[官方模型教程](https://docs.vllm.ai/projects/ascend/zh-cn/latest/tutorials/models/)找到**目标模型、硬件、权重格式**的配方，并核对相应版本的安装和特性支持。用户指定fork/分支时再读该仓库说明。不存在适配时指出缺口，不能声称换路径即可支持任何模型。
4. 将本轮实际选定的镜像、完整SHA、Python路径、模型、设备、通信地址、API和测试目标记录到项目 `RUNBOOK.md`；后续以现场检查为准。按需完成以下阶段，不重复请求已获得的授权。

## 按阶段读取

| 当前工作 | 读取 |
|---|---|
| SSH、代理、Docker、设备与挂载 | [连接和容器](../skills/vllm-ascend-ops/references/connect-container.md) |
| HF权重下载、空间检查、本地PC代理转发、多隧道加速与剩余时间 | [权重下载与加速](../skills/weight-download/references/weight-download.md) |
| NVIDIA H200中编译指定vLLM fork、保存镜像、启动服务与curl验证 | [H200源码编译与服务](../skills/vllm-cuda-ops/references/h200-source-build.md) |
| NPU归属、卡与chip编号、多机HCCL/fabric诊断 | [设备和跨机网络](../skills/vllm-ascend-ops/references/hardware-network.md) |
| 拉取配套源码、更新分支、编译和导入验证 | [源码和安装](../skills/vllm-ascend-ops/references/build.md) |
| 选择serve参数、单机／双机、启动和停止 | [服务部署](../skills/vllm-ascend-ops/references/serve.md) |
| AISBench安装、先vim再执行、精度与性能结果 | [AISBench](../skills/model-evaluation/references/aisbench.md) |
| 视觉权重、Hallusion请求参数/通用API裁判/分类评分、OCRBench V2 | [多模态测试](../skills/model-evaluation/references/multimodal.md)；并发与缓存恢复另读[Hallusion并发和API评分](../skills/model-evaluation/references/hallusion-concurrency-api.md) |
| 精确16K/128K输入、固定输出、90%前缀和预热 | [定长数据](../skills/model-evaluation/references/datasets.md) |
| 开启采集、双机控制、analyse和查看trace | [Profiling](../skills/vllm-ascend-ops/references/profiling.md) |
| trace指标、逐forward比较、计算/访存/通信瓶颈 | [Profiling分析](../skills/vllm-ascend-ops/references/profiling-analysis.md) |
| 连接、加载、版本、慢请求或结果异常 | [排障表](../skills/vllm-ascend-ops/references/troubleshooting.md) |

## 脚本风格

- 一个脚本做一件事：少量环境变量，然后一条主要命令。单机、node0、node1分别写短脚本；不写通过大量if、参数解析和自动探测拼装的万能启动器。
- 模型路径、设备、IP、端口等本轮选定值直接写清。不要将所有可选性能项都塞进基础脚本；只加入用户要求或当前模型配方确实需要的参数，并解释用途。
- 不默认迁移权重、生成模型别名目录、修改config.json、增加draft路径或额外加载配置。必要适配先给具体根因与最小改动。
- 保留用户已有参数，编辑前备份并交付diff。Shell续行反斜杠必须位于行末，不在续行中夹注释。不要重复创建已有clone、build或测试任务。
- Hallusion单独推理优先复用原客户端：不传limit即全量，按需限制前N题；不为全量测试额外生成串行调度器、监控或新的日志体系。只有用户要求恢复/串行执行时才增加对应能力。judge与模型推理是独立阶段，按用户本轮范围执行。
- Hallusion新增采样参数按真实请求字段和模型模板映射；不把外部框架开关当vLLM参数。切换judge使用独立缓存；已有裁判结果优先离线生成分类aAcc，报告样本范围、截断与judge口径。

## 验收与交付

依次区分：容器可用 → 代码可导入 → 服务健康 → curl有正确结构的输出 → 指定负载测试通过。仅完成某阶段就只报告该阶段。

保存实际启动脚本、AISBench配置、执行命令、完整日志和结果目录；精度报告样本成功/失败、分数和截断，性能报告真实token数、并发、吞吐、TTFT/TPOT及缓存条件。用户只要求启动时不自动进行整套长测试；精度、性能和profiling分开记录。

思考模型的精度验收须核对实际权重模板的思考标记、API是否已分离reasoning，以及逐题提取值与最终答案是否一致。缺少最终答案不得从未完成思考中猜选项；总分不变也可能有误判抵消，不能只验样本数和accuracy字段。

阶段切换先查已有PID、退出码和结果，连接断开后不重复发起安装、启动或测试。长命令保存完整日志后分段读取，不将`cmd | tail`的退出状态当原命令结果。多机实验记录各节点时钟及采集窗口；比较时保持代码、权重、输入输出、缓存条件和采集口径可追溯。

停止或排障先核对进程所属容器、命令与启动时间，只处理获授权服务，不全局pkill。不因显存被占用就推断API可用或终止其他任务。保持模型和驱动只读，项目文件在用户指定工作目录内；Docker和软件安装使用其正常存储。

本技能提供流程和示例，不内置某次实验结果或永久“最新版本”。已知问题是诊断线索，不能当成所有新模型的默认补丁。
