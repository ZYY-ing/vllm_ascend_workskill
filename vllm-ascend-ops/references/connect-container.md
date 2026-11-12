# 连接、代理与容器

先读取environment.local.md或任务资料。本文变量为示例，实际用户名、路径、设备和镜像应由资料及现场确定；不在新机器寻找原作者电脑的绝对路径。

## 连接

本地已有SSH配置时：

```bash
ssh -F /path/to/ssh_config ascend-node0
```

默认~/.ssh/config已配置别名则直接ssh ascend-node0。首次主机指纹需用用户可信来源核对；认证失败请用户在本机完成，不能猜密码、提取Cookie或把Token写进命令。Windows PowerShell多行远端命令使用单引号here-string，避免本地展开Bash变量；传文件用scp，脚本UTF-8无BOM/LF。

进入宿主后只读检查：

```bash
hostname
npu-smi info
docker ps -a
ip -br addr
```

多机再检查ip route get 对端通信IP，区分SSH管理网与HCCL通信网。先复用用户指定容器；运行中docker exec，停止状态按请求docker start，不直接删除。

同一轮连接尽量批量读取独立信息，减少重复SSH握手。支持连接复用的OpenSSH客户端可按需使用ControlMaster/ControlPersist；先验证本机客户端能力，不将Linux/macOS的socket配置强加到Windows。Windows或不支持复用的环境使用ServerAliveInterval/ServerAliveCountMax保活及单连接批量命令。网络断开后先查远端PID与日志，再判断是否重试；不能把编译、拉服务、压测当作可无条件重发的只读命令。

## 可选：本地代理转发到远端

在本地终端保持此SSH连接：

```bash
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -R 127.0.0.1:17890:127.0.0.1:7897 ascend-node0
```

本地7897为代理示例，远端17890为监听端口；第二台再开一个隧道可复用同一端口号。远端验证后仅对所需Git命令指定代理：

```bash
ss -lntp 'sport = :17890'
curl --proxy http://127.0.0.1:17890 --noproxy '' -I --max-time 15 https://github.com
git -c http.proxy=http://127.0.0.1:17890 ls-remote https://github.com/vllm-project/vllm-ascend.git HEAD
```

remote port forwarding failed先查目标宿主端口占用；已有可用隧道复用，不杀未知进程，否则换空闲端口并同步代理地址。无占用再查sshd转发限制。代理连通与仓库认证是两层问题。host网络容器共享宿主回环，bridge容器不能照抄127.0.0.1。不默认改全局Git代理或关闭TLS。

## 创建容器

按[安装指南](https://docs.vllm.ai/projects/ascend/zh-cn/latest/getting_started/installation.html)选与硬件、驱动、CANN和目标发布版本匹配的镜像。不要仅为“最新”换nightly。下例是独占、可信实验宿主的精简写法；共享服务器应按官方对应硬件示例显式映射获授权设备，不使用privileged暴露全部NPU。

在宿主设置IMAGE为已选定的完整镜像tag。WORK示例需改为用户允许写入目录，MODEL_ROOT需已存在：

```bash
WORK=/srv/ascend-work
MODEL_ROOT=/mnt/models
mkdir -p "$WORK"
docker pull "$IMAGE"
docker run -d --name model-node0 --network host --ipc host --privileged \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver:ro \
  -v /usr/local/dcmi:/usr/local/dcmi:ro \
  -v /usr/local/bin/npu-smi:/usr/local/bin/npu-smi:ro \
  -v "$WORK:$WORK" -v "$MODEL_ROOT:$MODEL_ROOT:ro" \
  "$IMAGE" sleep infinity
docker exec -it model-node0 bash
```

该例不使用--rm，后续可start；Docker写正常镜像存储。挂载前检查宿主源路径存在，按硬件配方补必要通信配置/工具挂载，不将整套宿主/usr/lib64覆盖进镜像。新节点复制对应短命令改容器名。privileged环境仍通过ASCEND_RT_VISIBLE_DEVICES限制服务使用设备，但这不是安全隔离。

容器内确认npu-smi、Python、模型目录、config.json、索引及权重分片可读。打印sys.executable、torch/torch_npu版本与CANN环境。镜像自带兼容的软件时直接复用；只有需要目标分支或模型适配才继续源码安装。记录镜像digest与挂载，不把“容器Up”当服务就绪。

## 挂载与下载的常见陷阱

HF权重下载、磁盘容量核对、Windows认证代理及多SSH隧道测速见[权重下载与加速](weight-download.md)。已有普通代理可用时直接复用，不默认部署额外转发服务。

- 单文件bind mount前用test -f确认宿主源为文件。传统-v在源不存在时可能造出同名目录；需要让缺失源明确报错时可用--mount type=bind。容器内读取异常先核对源/目标类型及docker inspect，不先改应用代码。
- 直接bind某个文件时，宿主通过rename/某些编辑器的原子替换产生新inode，运行中容器可能仍看到旧文件。核对宿主/容器文件内容、挂载和inode；不能笼统认定所有cp都更换inode。正确修复可选择维护窗口内重建挂载或受控原位写入；后者需避免应用读到半写内容，也不保证应用自动reload。
- 不直接编辑Docker overlay2/UpperDir作为通用修复。是否重启/重建容器及改宿主配置必须在任务授权范围内，不能为修一个挂载停掉其他服务。
- 下载模型时记录来源、revision及目标文件大小/校验信息。下载慢先区分网络与本地/NFS写入；需要暂存本地时先核对容量和允许写入范围，完整校验后再复制至用户指定模型目录，不覆盖已有权重、不强制移动其他人的文件。
- HTTPS证书链异常优先使用组织认可的CA及代理配置，不能套用其他网络环境的verify=False、curl -k或GIT_SSL_NO_VERIFY。镜像源也应保留完整硬件/系统tag，替换仓库前缀不能悄悄换成另一代镜像。

设备归属与通信检查见[设备和跨机网络](hardware-network.md)。设备检查在宿主与目标容器分别核对，不把某个容器内的有限视图当整机空闲证明。
