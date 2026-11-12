# 常见问题：先找证据，再做最小修改

| 现象 | 优先证据与处理 |
|---|---|
| SSH失败/首次指纹 | 核对用户、端口、已有SSH配置和可信指纹；认证交由本机凭据，不试历史密码 |
| 反向转发17890失败 | 查目标宿主监听占用，复用可用隧道或换端口；再查sshd转发权限，不杀未知隧道 |
| Git代理报错/要求认证 | CONNECT等连接错误与仓库授权分开排；不开全局TLS绕过，不把镜像仓库当Git代理 |
| fetch后HEAD仍旧 | 查看FETCH_HEAD、remote-tracking ref与HEAD；显式fetch refspec后快进；本地修改阻挡不是远端没拉到 |
| 本地代码会被merge覆盖 | 先git diff；只有用户明确放弃才reset已成功fetch的目标，不附带clean |
| 编译失败 | 找首个error，区分Python构建包、系统编译工具、SOC、CANN库、torch ABI；不反复盲目pip升级 |
| 安装成功但还是旧代码 | 同时核对sys.executable、vllm shebang、__file__和editable源码；版本号相同也可能目录不同 |
| main插件与release核心导入/补丁不兼容 | 按当前分支的main-verified/CI核对开发锚点，release路线另按发布配套；不将两种依据混用 |
| rsync后metadata或dubious ownership失败 | 检查容器uid与实际源码owner，不先无依据升级setuptools，不全局safe.directory=* |
| 源码只改Python是否重编 | editable正确通常重启进程即可；原生算子/ABI变化才重编对应组件 |
| source/PATH能否省 | 当前环境已初始化可冗余；OPP override换的是算子来源，不因PATH正确就可删 |
| 路径报Repo id格式错误 | 容器内模型目录、config可读性、软链接、挂载优先；本地路径不可用可能转入Hub解析 |
| 模型文件“消失” | 宿主与容器分别readlink/findmnt/docker inspect，查覆盖挂载；无证据不判定删除，不擅自umount/改fstab |
| 挂载文件变目录或更新不可见 | 查宿主源类型、容器挂载及inode；原子替换可能保留旧挂载，不直接改Docker overlay2 |
| vLLM没变却配置失败 | Transformers/tokenizers也参与config/模板解析；记录配套版本和实际字段，避免无关升级 |
| MTP/量化key/rope形状错误 | 区分checkpoint格式、draft推导、量化映射和运行期padding；核对模型分支补丁，不默认加别名目录或改模型metadata |
| EngineCore整体退出 | 向前追最早worker异常；后续AISBench500/reset/refused多是服务失败结果 |
| 显存占用但API拒绝连接 | ss定位真实监听及PID/cgroup/容器；可能还在加载、已无API或属其他人，不能据显存猜端口 |
| docker ps无端口映射 | host网络常无Ports显示；服务--port才是API，RPC/HCCL端口不是HTTP |
| TCP互通但HCCL/UB仍失败 | 区分协调面与NPU数据面，查本机身份、endpoint及活网；见[设备和跨机网络](hardware-network.md) |
| prompt throughput为0 | 可能空闲或仅decode，查服务日志的decode推进、running/waiting，不据此单独认定死锁 |
| POST若干/RECV0、末尾数题很慢 | 长prefill或长推理可能正常；结合health、tokens推进、worker日志与NPU，不重复启动测试 |
| 1.x token/s看起来慢 | 先辨单请求/聚合、是否含TTFT、上下文、并发、输出预算、profiler开销；再做同负载对照 |
| profiler curl没输出 | -i看状态和退出码；空body可能成功，404查配置/端口，随后检查新trace |
| profiler目录不在预期位置 | 看运行进程实际参数、容器挂载/工作目录和各节点本机文件，不以脚本所在目录推断 |
| trace有Free/大通信占比就认为空闲或网络慢 | 先查字段口径、有效forward、跨流重叠、慢rank及调用机制；见[分析指南](profiling-analysis.md) |
| 停了父进程显存还在 | 核对同一服务残留worker，不能全局杀Python；驱动少量基线显存也不代表服务在运行 |

遇到不支持的硬件/模型/分布式组合，保留原始错误、版本和最小复现，说明缺少的适配。不能把诊断表变成每次部署都自动打补丁的脚本。
