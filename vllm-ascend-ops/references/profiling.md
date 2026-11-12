# Profiling：在线采集与离线解析

按目标版本[官方指南](https://docs.vllm.ai/projects/ascend/zh-cn/latest/developer_guide/performance_and_debug/service_profiling_guide.html)操作。本文是torch profiler路线；不为了采集额外安装另一套框架级profiler。curl开关采集，analyse解析落盘原始数据，是不同阶段。

## 1. 服务准备

仅在需要采集的启动脚本中加入，路径换为项目prof目录：

```bash
--profiler-config '{"profiler":"torch","torch_profiler_dir":"/srv/ascend-work/prof","torch_profiler_with_stack":false}'
```

用绝对路径，避免输出到意外的当前目录。设置参数是配置能力，不代表已经在采集。正在运行的服务不会因编辑sh自动改变配置；需要重启时在当前授权范围内执行。检查当前版本CLI，不能默认旧VLLM_TORCH_PROFILER_DIR环境变量仍生效。

同一节点有多个引擎/端口时按实验、节点和实例分目录，例如prof/本轮/node0/api8000；每个rank具体文件由当前实现生成，先核实命名是否唯一。共享存储必须额外区分节点，不只按rank编号混放。实际输出目录在进程启动时确定，改文件中的目录不能让运行进程切到新目录。

## 2. 有实际负载时采集

确认真实API，客户端任一能访问API的机器都可控制：

```bash
API=http://192.0.2.10:8000
curl --noproxy '*' --fail-with-body -sS -i --max-time 120 -X POST "$API/start_profile"
# 另一终端执行AISBench，或当前已有稳定负载
sleep 20
curl --noproxy '*' --fail-with-body -sS -i --max-time 120 -X POST "$API/stop_profile"
```

单独sleep不产生推理，要确保该时间窗确实有prefill/decode。-i显示HTTP状态；空body可正常，404应查是否启用配置/路由，连接拒绝查端口和进程。stop可能等待同步与落盘，超时先检查服务和文件增长，不无判断重复控制。

保存开始/结束时间、curl状态、服务日志和当轮AISBench参数。profiling有开销，不能将该轮吞吐当无采集基线；先跑正式性能基线，再另轮按所需区间采集。

20秒仅为示例，窗口由目标prefill、decode或请求端到端阶段和数据量决定，不固定3秒或20秒。查running/waiting、请求日志和generation token计数的连续增量确认阶段；计数器名称及语义以当前/metrics为准，不用固定“连续几次大于某值”的阈值判断所有模型。start_profile有副作用，不能拿来做健康探测。

每轮在结果目录记录provenance：核心/插件SHA、镜像digest和本地补丁、权重标识/模板、拓扑/设备、真实输入输出/并发、缓存和预热条件、采样、采集参数及起止时间。多机先记录各节点date/时钟偏差；窗口同步应由目标拓扑统一协调，不能直接用跨主机绝对时间差归因等待。证据放用户项目内，不回写公开技能。

## 3. 多机是否逐机curl

由服务拓扑决定，不由“有两台机器”决定：

- 单一API管理多TP/DP workers：核对本版本是否广播profile控制，并确认各节点worker都生成新trace；支持广播时调一次API即可。
- headless节点通常无HTTP端口，不能向它照抄API curl；原始数据仍可能落到该节点本机。
- 独立服务、P/D分离各有API时分别控制各实例；负载代理不一定转发这些路由，不把DP广播结论套到PD。

两端prof目录可以路径相同但文件各在本机；不会因从node1发curl就全部汇总到node1。共享存储时也需核对rank命名不冲突。

## 4. 分别解析对应节点数据

stop完成且文件停止增长后，在产生数据的容器内找到本轮具体目录：

```bash
find /srv/ascend-work/prof -type d -name '*_ascend_pt'
```

用服务兼容的Python/torch_npu环境，必要时先source实际CANN环境，编辑profiler.py：

```python
from torch_npu.profiler.profiler import analyse
analyse('/srv/ascend-work/prof/本轮具体_ascend_pt')
```

```bash
python profiler.py
```

对需要的每个rank目录逐个解析，不把包含多轮trace的父目录当成必然递归入口。官方路线需要analyse；某版本trace_handler已自动解析且产物完整时可省重复执行，不泛化为所有版本都不需要。解析本身不开始采集、不发模型请求、不重启服务。

不要仅为解析自动停止仍需保留的服务。原始数据已完整、解析资源足够且不影响任务时，可解析对应完成的目录；CPU/内存/磁盘资源竞争明显时，待测量结束或安排维护窗口。特定环境明确要求服务完全退出后解析时遵循本轮要求，不将其写成通用前置条件。共享盘上不要多个节点重复解析同一rank目录。

## 5. 验收

区分原始*_ascend_pt与解析后ASCEND_PROFILER_OUTPUT。按实际产物查看trace_view.json、kernel_details.csv、operator_details.csv/op_statistic.csv等；trace可用MindStudio Insight等支持工具打开。文件列表随版本变化，不凭目录存在就报告分析完成。

目录为空或路径不符时核对运行进程profiler-config、容器挂载、相对路径、写权限、磁盘、控制窗口内是否有负载、各rank日志和是否还在落盘。不要自动移动旧trace或指认文件被删。交付两机对应目录、采集窗口、解析状态及失败原因，停止profiling不等于停止服务。

需要解释瓶颈时继续读[Profiling分析](profiling-analysis.md)，不要把生成trace文件就当成完成性能归因。
