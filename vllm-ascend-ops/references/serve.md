# 服务部署：先按模型配方选参数

先核对模型config、量化描述、权重分片、NPU代际和本版本CLI。单机或多机拓扑由模型容量与目标决定；MTP、EP、图模式、异步和卸载都不是任意模型可通用打开的开关。

共享机设备归属和多机通信不明确时先读[设备和跨机网络](hardware-network.md)，不通过强杀占卡者来替代资源确认。

权重尚未准备时按对应模型页的正常下载方式及授权获取，记录实际落盘目录；不将代码仓库clone命令当作模型下载，也不移动其他人的checkpoint。多节点分别验证模型可见性和元数据一致。

多模态服务还须核对视觉编码器、连接/投影层及processor是否完整；删除language-model-only并设置image限额不会补出缺失权重。详见[多模态检查](multimodal.md#服务与权重)。

## 单机短脚本

生成start_single.sh，以下取值仅示例，agent需替换为已核实配方；额外项只按需要加入。镜像环境已初始化可省source，未初始化时在脚本前加实际CANN set_env.sh；Python/PATH必须指向已安装代码。

```bash
#!/usr/bin/env bash
set -e
export ASCEND_RT_VISIBLE_DEVICES=0
export VLLM_WORKER_MULTIPROC_METHOD=spawn

exec vllm serve /mnt/models/model \
  --served-model-name model \
  --host 0.0.0.0 --port 8000 \
  --tensor-parallel-size 1 \
  --max-model-len 32768 \
  --max-num-seqs 4 \
  --max-num-batched-tokens 8192 \
  --gpu-memory-utilization 0.90
```

## 关键参数如何决定

| 参数 | 决策依据 |
|---|---|
| MODEL路径、served-model-name | 保留原始权重目录；客户端model使用服务名，tokenizer使用对应权重 |
| visible devices、TP | 用户授权设备数、模型分片要求和单机容量；A3逻辑芯片数可能不同于物理NPU数 |
| DP/PP/EP | DP一般增加副本吞吐；PP/跨机TP用于模型切分；EP仅适合受支持MoE。DP与EP组合按配方解释，不能简单当内存相加 |
| max-model-len | 至少覆盖真实输入+输出预算，也不能超过模型支持范围和可用KV容量 |
| max-num-seqs | 允许的活跃序列上限；不是每条请求都能以最大长度同时放下的保证 |
| max-num-batched-tokens | 每轮调度token预算；有chunked prefill时可小于长prompt，不是数据输入长度 |
| gpu-memory-utilization | 设备内存预算，给运行时/图捕获留余量；若显式kv-cache-memory-bytes，核对该版本覆盖关系 |
| quantization | 由实际权重格式和教程决定；Ascend量化权重才按支持情况加--quantization ascend，BF16不照搬 |
| async-scheduling | 模型、推测解码方法和后端支持时按目标打开，不能默认所有组合兼容 |
| compilation-config | 确认版本支持后按配方选择，例如FULL_DECODE_ONLY；图捕获大小和内存不要随意堆参数 |
| speculative-config | 只有模型/后端支持时选MTP等方法和步数，不默认新建draft路径；非MTP模型不照抄 |
| enable-prefix-caching | 开启缓存能力，不保证命中比例；负载与预热另行定义 |
| additional-config | 仅加入本硬件/模型所需项；weight_nz、sparse KV offload等不是统一默认值 |
| profiler-config | 本轮需要采集时按profiling章节加入，目录绝对路径 |

按[官方模型教程](https://docs.vllm.ai/projects/ascend/zh-cn/latest/tutorials/models/)生成目标模型版本；不是将表中所有项都添加。若用户明确要MTP/图/异步，应验证支持和实际启用，不暗中改成eager/no-async后声称目标完成。没有证据不新增权重加载配置来“兜底”。

## 双机示例：两节点各一个DP rank、每rank TP8

此拓扑是可选的特定部署方式，不等于所有大模型的双机方案。先确认目标模型配方允许此DP/EP布局；若需要跨机切一个dense模型，按对应跨机TP或PP教程，不能只把DP改为2。

两端权重、代码、镜像栈和参数一致。以下用文档通信IP，换成实际通信网；NIC用路由核实结果。设备0..7须均获授权。两端设置VLLM_WORKER_MULTIPROC_METHOD=spawn，CANN环境按镜像需要初始化。

node0脚本：

```bash
#!/usr/bin/env bash
set -e
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
export VLLM_WORKER_MULTIPROC_METHOD=spawn
export VLLM_HOST_IP=192.0.2.10 HCCL_IF_IP=192.0.2.10
export HCCL_SOCKET_IFNAME=eth0 GLOO_SOCKET_IFNAME=eth0
exec vllm serve /mnt/models/model \
  --served-model-name model --host 0.0.0.0 --port 8000 \
  --tensor-parallel-size 8 --distributed-executor-backend mp \
  --data-parallel-size 2 --data-parallel-size-local 1 \
  --data-parallel-address 192.0.2.10 --data-parallel-rpc-port 12890
```

node1脚本：

```bash
#!/usr/bin/env bash
set -e
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
export VLLM_WORKER_MULTIPROC_METHOD=spawn
export VLLM_HOST_IP=192.0.2.11 HCCL_IF_IP=192.0.2.11
export HCCL_SOCKET_IFNAME=eth0 GLOO_SOCKET_IFNAME=eth0
exec vllm serve /mnt/models/model \
  --served-model-name model --headless \
  --tensor-parallel-size 8 --distributed-executor-backend mp \
  --data-parallel-size 2 --data-parallel-size-local 1 \
  --data-parallel-start-rank 1 \
  --data-parallel-address 192.0.2.10 --data-parallel-rpc-port 12890
```

两个脚本均补入当前模型实际需要的相同容量、量化、EP和优化参数；不保留无关参数。RPC是节点间协调端口，不是OpenAI API。headless节点通常没有HTTP API。HCCL通信接口、buffer和传输模式仅按网络/硬件配方设置。

## 启动、日志与验证

在各自容器的项目目录执行对应脚本。下面示例仅示意node0，日志目录先建，已有进程先识别，不能重复拉起：

```bash
mkdir -p logs
nohup bash start_node0.sh > logs/node0.log 2>&1 &
echo $! > logs/node0.pid
```

exec使脚本PID成为服务入口PID，利于信号传递，不提高推理性能，也不自动保证全部worker退出。加载、节点等待、图捕获耗时不同；看首个worker异常和日志增长，不能因暂时静默立刻重启。

从客户端用真实管理IP与API端口依次验收：

```bash
API=http://192.0.2.10:8000
curl --noproxy '*' --fail-with-body "$API/health"
curl --noproxy '*' --fail-with-body "$API/v1/models"
curl --noproxy '*' --fail-with-body --max-time 120 "$API/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{"model":"model","messages":[{"role":"user","content":"你好"}],"max_tokens":64,"stream":false}'
```

embedding/rerank/多模态模型用其匹配任务接口和输入，不强行聊天；本技能定长生成性能示例仅适合文本生成服务。确认响应结构与服务名，再按用户要求做并发验证；curl一次通过不证明长输入MTP/DP/图组合稳定。

停止时核对pid文件与实际cmdline、容器/cgroup、启动时间，向确定的主进程TERM并等待；残留worker只处理同一验证后的进程树，必要时最后KILL。结束后核对端口、worker和NPU进程。不要全局pkill或默认停止整个容器。

PD分离任务须按目标版本配方确认共享组件和P/D独立API。验证真实分离链路时，业务请求打到配置好的代理，并检查P和D两端证据；直打Decode端可能绕过Prefill路径。profile控制是否经代理转发另行核对，不能从业务请求路由推定。独立实例区分设备组、服务名、API/RPC/传输端口、PID和日志，发生端口冲突先查归属，不以反复重启“碰运气”解决。
