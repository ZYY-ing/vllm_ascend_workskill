# vLLM 部署与评测 Skills

用于 AI agent 的 vLLM 部署、权重下载、评测和排障技能集合。Ascend 与 NVIDIA CUDA 分开选择，下载和评测可独立使用。仓库提供流程、示例及辅助工具，不包含 vLLM 引擎源码、模型权重、个人服务器配置或实验结果。

## 选择技能

| Skill | 适用任务 | 入口 |
|---|---|---|
| `vllm-ascend-ops` | Ascend容器、配套源码、单机/多机服务、NPU/HCCL诊断和profiling | [SKILL.md](skills/vllm-ascend-ops/SKILL.md) |
| `vllm-cuda-ops` | NVIDIA H200/CUDA源码编译、依赖与JIT排障、服务和curl | [SKILL.md](skills/vllm-cuda-ops/SKILL.md) |
| `weight-download` | HF权重下载、代理与多隧道测速、断点续传和checksum验收 | [SKILL.md](skills/weight-download/SKILL.md) |
| `model-evaluation` | AISBench、定长性能、HallusionBench、OCRBench V2及答案提取复核 | [SKILL.md](skills/model-evaluation/SKILL.md) |

只加载本轮任务需要的技能。一次任务可依次使用多个技能，不要求把所有文档全部读入。综合任务的阶段衔接和原有操作约定见[完整工作流](docs/workflow.md)。

## 使用

```bash
git clone https://github.com/ZYY-ing/vllm_ascend_workskill.git
cd vllm_ascend_workskill
```

将选定的整个 `skills/<name>/` 目录交给 agent，先读其中的 `SKILL.md`；支持本地技能的工具也可安装整个目录。每个技能的运行工具和参考文档随技能一起分发，不需要安装 Blue 或同步到固定全局目录。

部署环境可从[模板](skills/vllm-ascend-ops/assets/environment.example.md)填写本地 `environment.local.md`，也可直接在会话中提供。认证使用已有 SSH 配置或私有环境变量，不保存到仓库。使用与交付注意事项见[使用说明](docs/usage.md)。

示例：

> 使用 weight-download 检查模型仓库和目标磁盘，按指定 revision 下载并完整校验；不要启动服务。

> 使用 vllm-ascend-ops 按指定模型和硬件核对配方、启动服务并验证 curl；通过后使用 model-evaluation 执行指定样本数、输入输出长度、并发与缓存条件的测试。

## 主要学习入口

- [HF权重下载与提速](skills/weight-download/references/weight-download.md)
- [Ascend源码安装](skills/vllm-ascend-ops/references/build.md)与[服务部署](skills/vllm-ascend-ops/references/serve.md)
- [H200编译、镜像、服务与curl](skills/vllm-cuda-ops/references/h200-source-build.md)
- [AISBench精度性能](skills/model-evaluation/references/aisbench.md)与[定长数据及前缀缓存](skills/model-evaluation/references/datasets.md)
- [HallusionBench并发测试和独立裁判](skills/model-evaluation/references/hallusion-concurrency-api.md)
- [Hallusion数据、请求和指标解释](skills/model-evaluation/references/hallusionbench.md)
- [OCRBench V2](skills/model-evaluation/references/ocrbench-v2.md)、[输出预算和采样](skills/model-evaluation/references/generation-settings.md)、[思考模型答案提取](skills/model-evaluation/references/answer-extraction.md)
- [Profiling采集](skills/vllm-ascend-ops/references/profiling.md)与[分析](skills/vllm-ascend-ops/references/profiling-analysis.md)

## 仓库结构

```text
README.md                   仓库入口与技能选择
CONTRIBUTING.md              新增技能、去重、检查及发布规则
SOURCES.md                   官方文档、Blue及Hallusion参考来源
.gitignore                  本地环境、凭据和运行产物忽略规则
docs/
  usage.md                  技能使用、分发和环境信息约定
  workflow.md               从部署到测试的完整流程和交付要求
  routing-acceptance.md      真实任务的技能选择验收用例
  migration-map.json        原35个文件的哈希与迁移位置
skills/
  vllm-ascend-ops/           SKILL.md、agents、assets、references
  vllm-cuda-ops/             SKILL.md、references
  weight-download/           SKILL.md、references、scripts
  model-evaluation/          SKILL.md、references、scripts、tests
tools/
  check_repository.py       结构、文档链接、语法、敏感信息与迁移完整性检查
```

`SKILL.md` 负责选择和执行导航，`references/` 负责详细命令，`scripts/` 负责可重复运行的工具，`tests/` 负责离线行为验证，`assets/` 负责可复制的模板。脚本具体参数见相应文档和帮助，不在多个 README 重复维护。

## 修改与检查

新增能力先读 [CONTRIBUTING.md](CONTRIBUTING.md)。保留原始模型和源码，测试记录实际版本、请求、token、失败、截断与评分口径；真实环境和输出放在本地项目，不写回技能。

本次目录迁移的内容保留方式和行为变化见[迁移说明](docs/migration.md)；逐个原文件的对应关系见[迁移清单](docs/migration-map.json)。

```bash
python tools/check_repository.py
```

Python为3.10及以上；能找到 Bash 时同时检查 Shell 语法，也可用 `--bash /path/to/bash` 指定。离线测试命令见贡献说明，不调用真实收费API，不代表模型精度或性能成绩。参考来源及内容归属见 [SOURCES.md](SOURCES.md)。
