---
name: vllm-ascend-ops
description: 在 Ascend NPU 上安装配套 vLLM/vllm-ascend、管理容器和单机多机服务，诊断设备归属、HCCL 与 profiling。适用于昇腾部署、服务排障和性能采集；独立权重下载或数据集评测交给对应技能。
---

# Ascend vLLM 部署与排障

先核对用户本轮指定的服务器、硬件、镜像、源码、权重和操作范围。已有任务先检查真实 PID、容器、启动时间、退出码及日志，避免重复安装、启动或采集。使用中文解释，命令保持简短。

## 输入与范围

- 环境来源优先级：本轮明确指令 → 用户环境资料或本地 `environment.local.md` → 已有 Blue 配置中可匹配项。Blue 仅为可选只读信息来源，不要求安装或同步工具。
- 环境模板见 [assets/environment.example.md](assets/environment.example.md)。真实 IP、密码、Token、私钥及运行结果留在用户本地或服务器，不回写公开技能。
- 用户指定 NVIDIA/CUDA 时使用 `vllm-cuda-ops`；独立下载使用 `weight-download`；AISBench/Hallusion/OCR 测试使用 `model-evaluation`。这些技能可分别安装，部署本身不强制依赖其安装。

## 按阶段读取

| 任务 | 参考 |
|---|---|
| SSH、代理、容器、挂载 | [连接与容器](references/connect-container.md) |
| 配套版本、编译和导入检查 | [源码安装](references/build.md) |
| 参数、单机/双机、启动、日志与验证 | [服务部署](references/serve.md) |
| NPU进程归属、卡/chip编号、跨机通信 | [硬件和网络](references/hardware-network.md) |
| 采集 profiling | [采集流程](references/profiling.md) |
| 已有 trace 的判读 | [分析方法](references/profiling-analysis.md) |
| 已知故障线索 | [排障表](references/troubleshooting.md) |

只加载本轮需要的参考。根据模型、硬件、权重格式与分支核对官方配方；镜像和源码版本不能静默混用。不默认迁移权重、改 config 或补建模型别名。镜像、完整 SHA、Python、API 和实际参数记录到本地项目 RUNBOOK。

## 执行与验收

保留用户已有参数，编辑前备份并给出 diff；单机/node0/node1 分别使用短脚本。先核对设备资源与端口；停止服务只处理已授权目标，不全局 pkill、不默认清理共享缓存或其他容器。

依次区分：容器可用 → 代码实际导入正确 → 服务健康 → curl 真实输出成功。用户未要求测试时，不自动扩展长负载；profiling 与性能/精度分开记录。

长任务保存完整日志与真实退出码，不以管道 tail 的状态代替原命令退出码。多机记录各节点时钟、采集窗口和设备映射。改动版本或图模式后重新验证受影响阶段，不把某次故障当所有模型的默认补丁。
