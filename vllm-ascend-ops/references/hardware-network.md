# NPU归属和跨机通信：只读检查优先

用于服务启动前的资源确认及设备/通信故障；不是每次源码编译都执行整机巡检。某个命令不存在时按驱动/机型工具确认替代方法，不安装或改写宿主网络来凑命令。

## 1. 从设备占用定位到目标服务

在宿主查看npu-smi info、ss -lntp和docker ps，记录持卡PID、实际端口及容器。HBM、设备进程、容器状态是不同证据：容器Up不代表占卡；容器内看不到进程名也不代表整机无占用；常用端口空闲不代表没有其他模型服务。

拿到宿主PID后，先只读查看：

```bash
PID=12345
ps -p "$PID" -o pid,ppid,lstart,args
cat "/proc/$PID/cgroup"
docker ps -a --no-trunc --format '{{.ID}} {{.Names}} {{.Status}}'
```

12345必须替换为当场查到的PID，不执行此示例值。cgroup常见/docker/<id>或docker-<id>.scope；将ID与Docker记录对应。无法解析时继续核对容器inspect、进程命名空间和父子树，不将“脚本没匹配到”解释为裸机进程。只需定位某PID时不遍历无关用户文件。

宿主PID与容器PID通常不同；宿主npu-smi提供的PID不能直接在容器里kill，容器ps的PID也不能放到宿主循环中kill。进程名大小写和Linux comm长度可能变化，不只grep小写vllm；以归属、启动时间和命令为准，防PID文件陈旧与PID重用。

需要停服时沿[服务停止流程](serve.md)：TERM已核实入口并等待，随后核查同一任务worker树；KILL只作必要的后续手段。不能保证杀一个worker会自动清掉全树，也不能保证docker stop后HBM立即归零。驱动回收可能异步，结合该硬件空闲基线和进程/端口复核，不固定等待分钟数。

不自动reset芯片、不关闭他人容器、不广播wall消息；共享机协调按用户明确要求进行。磁盘不足先报告容量与候选文件，不自动prune或删除未知日志/缓存。

## 2. 卡、chip与容器设备编号

读取npu-smi设备详情、宿主/dev/davinci*、容器暴露的设备及目标版本官方说明。部分A3系统存在物理卡与逻辑chip数量差异；不能将所有硬件都当作8个相同ID，也不能仅凭型号名推导/dev文件、驱动物理ID、visible device与rank一一对应。

将授权的物理设备、容器可见设备、ASCEND_RT_VISIBLE_DEVICES和TP/DP rank映射写入RUNBOOK。非连续设备、容器设备过滤、双芯产品尤其要现场验证。A5可能需要额外通信设备和身份配置挂载，按实际950DT镜像/驱动配方核对，不把A2/A3容器命令直接复制后删报错项。

## 3. 多机按网络层次定位

| 层次 | 要确认的证据 |
|---|---|
| 管理面 | SSH管理IP、API端口和客户端NO_PROXY；curl命中的确是目标模型 |
| 进程协调面 | DP/RPC或其他协调端口、节点地址、服务参数一致，无其他任务占用 |
| 通信接口 | ip route get对端地址、网卡存在/UP，HCCL/GLOO选择与目标网络一致 |
| NPU数据面 | 按机型使用匹配的hccn_tool、hccs_ping或URMA工具及官方通信测试 |
| 静态身份 | 当前机的rootinfo/endpoint、容器挂载和活网地址一致，不能复制另一台机器的专属身份 |

TCP通只证明该TCP路径，不能证明HCCL/RoCE/HCCS/UB链路可用。报错最早节点、原始错误码和通信后端决定下一步；不要将所有timeout或E19999都断定为同一个fabric故障。

950DT相关问题可先核对本机/etc/hccl_rootinfo.json、/etc/hixlep中的实际endpoint文件及可用的urma_admin show --brief。文件路径与消费方式以安装栈为准，某些版本通过ASCEND_LOCAL_COMM_RES传递资源信息。静态配置可能与活网变化不同步，须按本版本格式比较，不能仅搜字符串即判断一致。

生成或写入身份文件、改防火墙/路由、修改EID、重置设备均不是只读诊断。先提供证据与最小修复范围，在用户授权内执行；不自动安装非官方工具或用简化ASCEND_LOCAL_COMM_RES跳过身份校验。运行期热更新也需考虑单文件挂载和应用重载，见[挂载问题](connect-container.md)。

参考：[Blue Toolkit的PID归属](https://github.com/xuchi-0808/blue-server-toolkit/blob/main/scripts/who.sh)、[设备与进程经验](https://github.com/xuchi-0808/blue-server-toolkit/blob/main/docs/npu-process-cleanup.md)、[950DT通信诊断](https://github.com/xuchi-0808/blue-server-toolkit/blob/main/docs/a5-950dt-fabric-config.md)。这里采用分层诊断方法，不把其设备映射、清理时长或修复命令当所有版本的默认值。
