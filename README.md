# vllmascend_workskill

用于 AI agent 的 vLLM Ascend 部署、测试和排障技能仓库。覆盖服务器连接、Docker、配套源码安装、权重下载、单机与多机服务、AISBench 精度与性能、多模态评测及 profiling，并提供 NVIDIA H200/CUDA 源码编译参考。

仓库包含 **一个主 skill：`vllm-ascend-ops`**。`references/` 是按阶段读取的操作文档，`scripts/` 是辅助工具；它们共同构成完整技能，不是互相独立的 skill。仓库不包含 vLLM 引擎源码、模型权重或某次实验的私有环境配置。

## 技能入口与关键引用

agent 从 [vllm-ascend-ops/SKILL.md](vllm-ascend-ops/SKILL.md) 开始，按当前任务读取参考资料。人工学习可先阅读 [技能目录说明](vllm-ascend-ops/README.md)。

| 工作内容 | 关键文档 |
|---|---|
| 主 skill、执行原则与验收口径 | [SKILL.md](vllm-ascend-ops/SKILL.md) |
| 服务器、容器、模型和测试信息填写 | [环境配置示例](vllm-ascend-ops/environment.example.md) |
| SSH、代理、Docker 和挂载 | [连接与容器](vllm-ascend-ops/references/connect-container.md) |
| HF 权重下载、代理加速、断点续传与校验 | [权重下载](vllm-ascend-ops/references/weight-download.md) |
| Ascend 配套源码与安装验证 | [源码安装](vllm-ascend-ops/references/build.md) |
| NVIDIA H200/CUDA 编译、镜像、启动与 curl | [H200 学习文档](vllm-ascend-ops/references/h200-source-build.md) |
| 单机、多机服务参数与进程管理 | [服务部署](vllm-ascend-ops/references/serve.md) |
| AISBench 精度、性能及结果验收 | [AISBench](vllm-ascend-ops/references/aisbench.md) |
| 精确输入长度、固定输出与前缀缓存条件 | [测试数据](vllm-ascend-ops/references/datasets.md) |
| HallusionBench、OCRBench V2 与评分适配 | [多模态测试](vllm-ascend-ops/references/multimodal.md) |
| Hallusion 并发、通用 API 裁判与缓存恢复 | [并发和 API 评分](vllm-ascend-ops/references/hallusion-concurrency-api.md) |
| NPU 编号、归属与跨机通信诊断 | [硬件和网络](vllm-ascend-ops/references/hardware-network.md) |
| Profiling 采集与 trace 分析 | [采集流程](vllm-ascend-ops/references/profiling.md)、[分析方法](vllm-ascend-ops/references/profiling-analysis.md) |
| 连接、安装、加载和推理问题 | [排障表](vllm-ascend-ops/references/troubleshooting.md) |

## 如何使用

先获取仓库：

```bash
git clone https://github.com/ZYY-ing/vllmascend_workskill.git
cd vllmascend_workskill
```

将整个 `vllm-ascend-ops/` 目录交给具备终端、SSH 和文件读取能力的 agent，要求先读 `SKILL.md`。支持本地 skill 目录的工具可以安装整个技能目录；其他工具也可以直接按文档执行，不需要专用连接器。

复制环境模板后填写实际环境，保留在本地：

```bash
cp vllm-ascend-ops/environment.example.md \
   vllm-ascend-ops/environment.local.md
```

环境资料说明 SSH 配置位置、硬件、容器、源码、权重、设备、端口和本轮测试目标。凭据使用已有 SSH 登录或私有环境变量，不写入文档。也可以在会话中提供环境资料，无需创建本地配置文件。

示例任务：

> 阅读 vllm-ascend-ops/SKILL.md 和我的本地环境资料。先只读检查服务器、容器、源码版本、权重完整性和设备占用，再按该模型的官方配方部署服务。服务健康和 curl 请求通过后，使用 AISBench 执行我指定的输入输出长度、样本数和并发，保存实际参数、原始日志及结果。

只要求下载、排障或启动时，执行对应阶段即可，不自动扩展为整套评测。NVIDIA 环境先读 H200 文档，不直接套用 Ascend 的设备、通信和量化参数。

## 仓库代码结构

```text
vllmascend_workskill/
├── README.md                         # 仓库入口和文档索引
└── vllm-ascend-ops/
    ├── SKILL.md                      # 主 skill 指令和阶段导航
    ├── README.md                     # 技能使用说明、文件说明和来源
    ├── environment.example.md        # 可公开的环境模板
    ├── .gitignore                    # 忽略本地环境、密钥、日志和数据
    ├── agents/
    │   └── openai.yaml               # skill 展示名称和简介
    ├── references/                   # 部署、测试和排障参考文档
    └── scripts/                      # 下载、数据构造、推理和评分辅助脚本
```

脚本按用途划分如下，参数和使用前提见对应参考文档及脚本帮助：

| 用途 | 脚本 |
|---|---|
| 固定 HF revision、文件清单与 checksum 验收 | `hf_weight_manifest.py` |
| Windows 当前用户认证代理转发、服务器多隧道连接分配 | `windows_sspi_proxy.ps1`、`tcp_proxy_pool.py` |
| 精确 token 输入、公共前缀数据与缓存指标 | `make_chat_data.py`、`cache_delta.py` |
| Hallusion 图片获取与模型推理 | `download_hallusion_images.sh`、`run_hallusionbench_hy4.py` |
| 评测前检查与原始结果核对 | `preflight.py`、`check_results.py` |
| 裁判 API 适配、并发与结果汇总 | `prepare_evaluation.py`、`prepare_concurrent_judge.py`、`judge_concurrency.py`、`run_judge_api.sh`、`summarize_hallusion_scores.py` |
| 推理和裁判并发行为验证 | `verify_concurrency.py`、`verify_judge_concurrency.py` |

辅助脚本不是通用模型启动器。服务脚本和框架配置按本轮模型、硬件、代码版本及用户要求生成；不能只换模型路径就承诺支持任意模型。

## 使用与结果约定

- 保留原始模型和源码，修改前核对目标；停止服务先确认所属容器、命令及启动时间。
- 分别验收容器可用、代码可导入、服务健康、真实请求成功和指定测试通过。
- 性能报告真实 token 数、吞吐、TTFT/TPOT、并发和缓存条件；精度报告全量范围、失败、截断及评分提取规则。
- 思考模型核对实际 tokenizer 的标记和 API 返回字段，避免从推理过程误取最终答案。
- 仓库只保存可公开的流程、示例和工具；本地环境、认证文件、私有日志、权重及数据集留在运行环境。

## 参考来源

部署和评测流程参考 [vLLM Ascend 官方文档](https://docs.vllm.ai/projects/ascend/zh-cn/latest/)、[vLLM GPU 安装说明](https://docs.vllm.ai/en/latest/getting_started/installation/gpu/)及各模型、评测框架的版本说明。执行时核对实际分支、镜像和依赖，不把不同版本的参数混用。

环境信息复用、PID 归属、容器挂载和诊断经验参考 [Blue Server Toolkit](https://github.com/xuchi-0808/blue-server-toolkit)。本 skill 独立组织流程，不依赖安装该工具；已有 Blue 配置仅作为可选、只读的环境信息来源。具体保留原则见[技能目录说明](vllm-ascend-ops/README.md#融合来源与保留原则)。
