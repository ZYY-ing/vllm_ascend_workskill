# 权重下载、PC代理转发与测速

适用于用户要求将HF权重下载到服务器指定路径，或定位下载慢、证书和认证问题。普通直连／现有代理满足要求时直接使用；Windows认证中继、多SSH隧道仅在对比测速有收益时增加。以下地址、端口和仓库均为示例，不保存真实服务器、账号、Token、企业域名或运行日志。

## 先选路线，再增加并发

按顺序推进：容量与仓库权限 → 官方站/镜像站及真实CDN连通性 → 同一分片的持续吞吐 → 下载器和连接数。首页能访问不代表权重CDN可访问；镜像站可能仍跳到同一个CDN。服务器已经经过PC代理时，再套SSH不会自动换一个更快出口。

| 实测情况 | 使用方式 |
|---|---|
| 直连稳定、速度达到目标 | `hf download` + 固定revision，避免额外代理 |
| HF/Xet稳定但未吃满链路 | 支持的Xet高性能选项，逐步调文件并发 |
| 只有PC能通，普通代理速度受限 | 合法可用的PC上游 + 回环SSH转发；企业认证场景再考虑SSPI中继 |
| 单SSH连接瓶颈，多连接测试确有提升 | 4条独立连接起步，再测8条；不是同一SSH进程里堆多个`-R` |
| Xet反复断流、缓冲不落盘，而HTTPS Range稳定 | 先测禁用Xet的HTTP下载；仍不足再采用下文aria2分片方案 |

在一次大仓库案例中，8文件并发、每文件最多16连接和8条独立SSH连接，持续吞吐约35～38 MB/s；这只是该出口的实测，不能承诺其他机器同速或2小时完成。更多连接可能只增加重试。保留每轮采样的字节差、时间窗、失败数和磁盘状态，选持续有效速度更高的一组。

## 1. 确认完整大小与真实可用空间

在实际执行下载的宿主或容器内检查；目录名含share不代表独立共享盘。

```bash
export REPO_ID='organization/model'
export REVISION='main'
export LOCAL_DIR='/home/weight/model'
export HF_ENDPOINT='https://huggingface.co'

df -h /home/weight
findmnt -T /home/weight -o TARGET,SOURCE,FSTYPE
```

换目录前比较两个路径的挂载来源；同一分区共享可用空间，改路径不会增加容量。索引中的tensor总量、下载初期的`incomplete total`和当前在传的几个分片，不代表整个仓库大小。认证和网络配置好后读取全部文件元数据：

```bash
python - <<'PY'
import os
from huggingface_hub import HfApi

info = HfApi().model_info(
    os.environ['REPO_ID'], revision=os.environ['REVISION'], files_metadata=True,
)
if any(f.size is None for f in info.siblings):
    raise SystemExit('部分文件缺少大小，不能将其当作0计算')
total = sum(f.size for f in info.siblings)
print('revision:', info.sha)
print('files:', len(info.siblings))
print('bytes:', total, 'GB:', round(total / 1e9, 2), 'GiB:', round(total / 2**30, 2))
PY
```

要续传、切换下载器或离线校验时，先保存固定commit的完整清单。脚本只保存文件路径、大小和校验值，不保存Token或签名URL：

```bash
mkdir -p "$LOCAL_DIR/.download-monitor"
python scripts/hf_weight_manifest.py capture --repo "$REPO_ID" --revision "$REVISION" \
  --output "$LOCAL_DIR/.download-monitor/manifest.json"
export REVISION="$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["revision"])' \
  "$LOCAL_DIR/.download-monitor/manifest.json")"
```

以上及后文的`scripts/`路径均相对技能目录；上传到服务器后使用实际脚本路径。不要在下载中途重新解析`main`并混入不同commit的分片。

全仓库下载需容纳全部文件，并给缓存、日志、其他任务留余量。只下载部分文件时明确过滤规则，并据同一文件集合计算容量及完成条件。空间不足先只读列目录：

```bash
ionice -c3 nice -n 19 du -x -h --max-depth=1 /mnt /home
```

继续细分大目录；父子占用不能相加，硬链接去重会让独立扫描与整树扫描的归属不同。区分模型、安装归档、缓存和容器存储；“容器停止”“镜像dangling”或没有打开文件，均不等于可直接删除。只按本轮授权清理明确的路径，不直接删除containerd/overlay2内部文件。

## 2. 代理、证书与仓库权限分开验证

只在下载进程的环境里配置代理，不为下载更改全局Git/pip设置：

```bash
export http_proxy='http://127.0.0.1:17890'
export https_proxy="$http_proxy"
export HTTP_PROXY="$http_proxy"
export HTTPS_PROXY="$http_proxy"
export no_proxy='127.0.0.1,localhost'
export NO_PROXY="$no_proxy"

curl --proxy "$https_proxy" --noproxy '' -I --connect-timeout 10 \
  "$HF_ENDPOINT/api/models/$REPO_ID"
```

需要Token时交互输入，或复用用户已有登录；不要将Token写进脚本、Git、命令参数或公开日志：

```bash
read -rsp 'HF Token: ' HF_TOKEN
export HF_TOKEN
echo
hf auth whoami
```

| 现象 | 下一步 |
|---|---|
| `Temporary failure in name resolution` | 查当前进程的代理环境与实际失败主机；经HTTP CONNECT代理时目标域名通常由代理解析，不能只看本机DNS |
| `200 Connection established` | 只表示代理隧道建立，继续看后面的站点HTTP状态 |
| `CERTIFICATE_VERIFY_FAILED` | 比较curl与Python使用的CA；使用组织认可的证书链 |
| 镜像308跳转官方站，调试从`authenticated: True`变成`False` | 将HF_ENDPOINT直接设为官方站后重新验证；跨域跳转不能假定保留Authorization |
| `401`、`403`或`Repository Not Found` | 先whoami，再核对仓库名、账号访问权限与细粒度Token范围，不能仅凭未认证响应认定仓库不存在 |
| `.gitignore.lock`短时等待但随后有进度 | 先观察，不删活跃锁，不启动第二份同目录下载 |

Ubuntu上curl能验证而Python不能时，可先使用系统CA：

```bash
export SSL_CERT_FILE='/etc/ssl/certs/ca-certificates.crt'
export REQUESTS_CA_BUNDLE="$SSL_CERT_FILE"
```

系统也不信任企业CA时，获取组织认可的PEM证书，按目标系统流程加入信任库后重试。Git的`sslVerify=false`、pip的`trusted-host`不解决HF证书配置；不将关闭TLS验证作为下载方案。`HF_DEBUG=1`仅用于定位，分享前遮掉认证信息和签名URL。`hf-cli`技能安装提示不是下载失败原因。

## 3. 基础下载与进程管理

先确认安装版本，已有可用环境不默认升级：

```bash
python -c 'import importlib.metadata as m; print("huggingface_hub", m.version("huggingface_hub")); print("hf_xet", m.version("hf_xet"))'
mkdir -p "$LOCAL_DIR"
hf download "$REPO_ID" --revision "$REVISION" --local-dir "$LOCAL_DIR"
```

本地路径必须是准确的绝对路径，末尾不要多出`~`。需要后台运行时将辅助文件统一放入目标目录的`.download-monitor/`，避免用户误认为模型文件散落在外面：

```bash
mkdir -p "$LOCAL_DIR/.download-monitor"
export MAX_WORKERS=8
nohup bash -c '
  hf download "$REPO_ID" --revision "$REVISION" --local-dir "$LOCAL_DIR" --max-workers "$MAX_WORKERS"
  rc=$?
  printf "%s\n" "$rc" > "$LOCAL_DIR/.download-monitor/exit-code"
  exit "$rc"
' > "$LOCAL_DIR/.download-monitor/download.log" 2>&1 < /dev/null &
printf '%s\n' "$!" > "$LOCAL_DIR/.download-monitor/launcher.pid"
```

PID是启动Shell，检查其子进程确定真正下载PID；不因SSH断开重复启动。重新尝试时先确认上轮已退出，将旧退出码归档，防止误读为本轮成功。保留模型目录及`.cache/huggingface`；已完成文件通常可复用，但不承诺Xet内存缓冲或每个未完成分片都能无损续传。

换目标路径时先停止对应下载。默认移动并复用已有内容；只有用户明确要求删除重下，才在停止后校验旧目录realpath、符号链接及目录范围再删除。先SIGINT并等待；需要进一步停止时只处理已核对的PID，不全局pkill，不删除仍在使用的锁。

## 4. 服务器使用本地PC代理

先查PC代理监听地址、进程与系统代理设置。服务器原代理若已是这台PC，增加SSH只改变传输通道，未必改变出口速度。先比较同一权重或同一有界Range请求的直连、现有代理和可用上游；不关闭TLS，不输出Token或签名URL，不用首页HEAD延迟推断大文件吞吐。不同文件/CDN的结果只能作为线索。

PC已有HTTP CONNECT代理时，在PC保持以下SSH连接：

```bash
ssh -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -R 127.0.0.1:17890:127.0.0.1:17889 ascend-node0
```

PC的17889是实际代理端口，服务器只监听回环17890。不要改GatewayPorts或暴露到0.0.0.0。服务器验证该端口后，下载代理设为`http://127.0.0.1:17890`。bridge容器的回环并不是宿主回环；先确定下载位置与可达性。

### Windows企业上游使用当前用户Negotiate认证

仅当当前Windows登录身份确有上游代理权限，且普通代理实测更慢时使用。需要PowerShell 7.4+；不读取、复制CNTLM密码或NTLM哈希，也不导出浏览器凭据。先在PC终端运行：

```powershell
pwsh -NoProfile -File ./scripts/windows_sspi_proxy.ps1 `
  -UpstreamProxyHost proxy.example.com -UpstreamProxyPort 8080 -ListenPort 17889
```

该脚本使用Windows默认凭据向指定上游进行Negotiate认证，支持HTTPS CONNECT到443，仅监听127.0.0.1；TLS仍由下载客户端验证。它不存权重或Token，不是支持所有企业认证协议的通用代理。407、认证响应分块编码或SSPI失败时停止，检查目标代理是否适用，不改成匿名／关闭验证重试。

测试可先对HF首页做连通性验证，再对已授权的大文件做限定Range测速；Windows若仅证书吊销查询不可达，应按组织证书策略处理，不把`-k`写入常用命令。让PC代理前台运行，或使用有日志且可定位PID的隐藏后台进程；后台启动不能意味着自动拥有其他账户的代理权限。

## 5. Xet并发与多SSH通道

先启用受当前版本支持的高性能模式，比较60～120秒平均速度和失败率：

```bash
export HF_XET_HIGH_PERFORMANCE=1
```

仍需调节时，查当前`hf_xet`版本文档；较新版本支持`HF_XET_FIXED_DOWNLOAD_CONCURRENCY`，与`hf download --max-workers`的文件并发不同。按现场情况逐步测试16、32、64，不将64作为所有机器的默认值。并发过大可能导致每个分块都超时，并丢失内存中尚未落盘的数据；升并发后必须看实际权重速度与错误，不只看连接数。新版下载为自适应并发，旧的`HF_XET_NUM_CONCURRENT_RANGE_GETS`不能未经版本核对照抄。

内存不足时同时检查容器限制和Xet缓冲配置；`HIGH_PERFORMANCE`会改变并发及缓冲预算。不要为下载影响其他服务，参数变化通常只在新进程生效，停止已有下载后再重启，不开多个下载进程争用同一目录。

单条SSH实测限制吞吐时，再增加独立SSH连接。PC分别保持以下连接（不是把四个-R放进同一SSH进程）：

```bash
ssh -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -R 127.0.0.1:17890:127.0.0.1:17889 ascend-node0
ssh -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -R 127.0.0.1:17891:127.0.0.1:17889 ascend-node0
ssh -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -R 127.0.0.1:17892:127.0.0.1:17889 ascend-node0
ssh -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -R 127.0.0.1:17893:127.0.0.1:17889 ascend-node0
```

逐条验证远端代理口，再将`tcp_proxy_pool.py`传至服务器的本次工作目录，启动回环分流器：

```bash
python tcp_proxy_pool.py --listen-port 17894 --upstream-ports 17890 17891 17892 17893 \
  --status-file "$LOCAL_DIR/.download-monitor/proxy.json"
```

下载进程的http/https大小写代理变量均改为`http://127.0.0.1:17894`后重启。分流器只分配TCP连接、不解密TLS、不缓存模型；只会跳过TCP连接失败的上游，不保证识别已建立但失效的SSH或代理认证错误。保持PC、认证转发、SSH隧道和服务器分流器运行，PC休眠/断网会影响下载。若多通道无实测收益，退回最简单且可靠的链路；不承诺代理出口、账号配额或物理带宽能靠加连接突破。

### Xet不稳定时使用HTTPS分段续传

先对新启动的HF进程试用`HF_HUB_DISABLE_XET=1`，其余保持相同，比较实际吞吐、重试和落盘。若普通HTTP仍慢，而同一分片的Range请求稳定，可换aria2；不要同时让HF和aria2写同一文件。

aria2方案需要一个**固定清单、逐文件刷新地址、有限重试、完成校验**的调度器，不能把首次拿到的一整仓库签名URL当作永不过期的任务列表。可从4～8个文件、每文件4～8连接起测，再比较8文件×16连接；后者最多约128条数据连接，不是默认最优值。

单个LFS大文件的下载示例，展示认证、URL和断点的边界；它不是自动下载全仓库的脚本。先停止同文件的旧下载，并在固定manifest中确认该文件的大小和SHA256：

```bash
export FILE='model-00001-of-00002.safetensors'
export PARTS_DIR="$LOCAL_DIR/.download-monitor/aria2-parts"
mkdir -p "$PARTS_DIR"
umask 077
export ARIA_INPUT="$(mktemp "$LOCAL_DIR/.download-monitor/aria-input.XXXXXX")"
touch "$LOCAL_DIR/.download-monitor/aria2-private.log"
chmod 600 "$LOCAL_DIR/.download-monitor/aria2-private.log"

python - <<'PY'
import os
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from huggingface_hub import hf_hub_url, get_hf_file_metadata

endpoint = os.environ['HF_ENDPOINT']
resolve = hf_hub_url(os.environ['REPO_ID'], os.environ['FILE'],
                     revision=os.environ['REVISION'], endpoint=endpoint)
meta = get_hf_file_metadata(resolve, token=True)
# token=True使用已有HF登录；也可由HF_TOKEN提供。只把已签名CDN地址交给aria2。
target = urlparse(meta.location)
if target.scheme != 'https' or target.netloc == urlparse(endpoint).netloc:
    raise SystemExit('未取得独立HTTPS CDN地址；此文件改用hf download，不向未知主机转发Token')
rel = PurePosixPath(os.environ['FILE'])
if rel.is_absolute() or '..' in rel.parts:
    raise SystemExit('文件名不在预期仓库目录范围')
part_dir = Path(os.environ['PARTS_DIR']) / rel.parent
part_dir.mkdir(parents=True, exist_ok=True)
with open(os.environ['ARIA_INPUT'], 'w', encoding='utf-8') as f:
    f.write(meta.location + '\n')
    f.write(' dir=' + str(part_dir) + '\n')
    f.write(' out=' + rel.name + '.part\n')
PY

rc=0
aria2c --no-conf --input-file="$ARIA_INPUT" --continue=true \
  --split=16 --max-connection-per-server=16 --min-split-size=16M \
  --file-allocation=none --auto-file-renaming=false --allow-overwrite=false \
  --check-certificate=true --connect-timeout=15 --timeout=60 \
  --max-tries=5 --retry-wait=5 --summary-interval=10 \
  > "$LOCAL_DIR/.download-monitor/aria2-private.log" 2>&1 || rc=$?
# 退出后删除本次mktemp地址文件；日志可能含签名URL，保持私有并脱敏后分享。
rm -- "$ARIA_INPUT"
test "$rc" -eq 0
```

这里的CDN可达性和证书仍要单独验证。`HF_TOKEN`不出现在aria2命令行，也不作为通用Authorization头发给CDN。若返回401/403或地址过期，调度器应重新用固定revision解析该文件地址，再使用**原来的part文件及`.aria2`控制文件**继续；重启进程后记得复用HF登录，不能只依赖已经退出进程中的临时Token。

全仓库调度需要同时满足：

- 同一目标目录只有一个管理器，持有独占锁；凭据来自环境或HF登录缓存。
- 部分文件进入独立暂存区，避免推理服务误用未完成权重；原HF的`.incomplete`不直接伪装为aria2控制文件。
- 小配置文件可继续用`hf download`，大文件用aria2；两者分工明确，不能抢写相同路径。
- 一个文件完成后，先与manifest中的大小及LFS SHA256比对，通过后才同盘原子移动到最终路径；正常Git小文件使用Git blob SHA1规则，不能直接拿原始文件SHA1替代。
- 验证失败保留并标记问题文件，不能无限重新下载；有界重试耗尽则报告失败。完成后再次核对全清单与索引引用的分片。
- 队列开始前检查**尚需净新增的数据量 + 余量**；活动下载时检查磁盘低水位，空间不足暂停本次队列，不停止其他人的任务。旧缓存仅在明确授权并确认无占用后删除。

SSH自动重连只负责恢复通道；下载器自己的错误、过期URL、仓库授权和磁盘状态仍需检查。Windows守护脚本保存PID映射时使用字符串键，日志只记录端口/PID/重试，不保存登录口令。

## 6. 进度、估时与完成验收

先检查PID、日志、退出码及磁盘空间。`du`同时观察目标和`.cache`，但不能将预分配文件的逻辑大小当作已经收到的网络数据；Xet的内存缓冲也会使网络传输与落盘进度不同步。

分流器的`proxy.json`每10秒原子更新：`download_bytes`为从上游转发给客户端的累计字节，`MBps`为最近采样的十进制MB/s，`errors`只统计TCP中继错误，HTTP失败和重试需结合HF/Xet日志。估时使用60～120秒的累计差值，不使用单个峰值；未使用分流器时可对同一活跃SSH TCP套接字的累计接收字节采样。逐连接求和会因连接关闭而下降，不能直接当作总流量。

```text
平均字节/秒 = (累计字节B - 累计字节A) / 两次采样间隔
剩余小时 ≈ 剩余权重字节 / 平均字节每秒 / 3600
```

网络字节包含TLS/HTTP开销及重试，压缩和未落盘缓冲也会影响换算，只报告近似区间。举例：440 GB在2～3小时内完成，需持续约41～61 MB/s（约328～488 Mbps）；实测38 MB/s对应约3.2小时，不能描述成已满足2～3小时。未完整测量时说清样本窗口，不凭他人耗时保证本机结果。

aria2分段文件的逻辑大小可能预先等于完整分片。未注册到活动队列的保留断点也不一定为0：优先读取aria2的有效完成量；只有无法读取时才用实际分配块估计，并标为估算。不能把`stat().st_size`当已下载字节；实际分配块也可能含重复/未校验片段，不能作验收凭据。恢复或切换计数口径后重建速率基线，避免进度突然增减被解释为网速峰值或数据丢失。

对本地最终目录做离线验收：

```bash
# 快速大小检查；返回成功也不代表已经做过checksum。
python scripts/hf_weight_manifest.py verify \
  --manifest "$LOCAL_DIR/.download-monitor/manifest.json" --local-dir "$LOCAL_DIR" --sizes-only
# 正式验收：LFS SHA256 + 普通Git文件blob SHA1。
python scripts/hf_weight_manifest.py verify \
  --manifest "$LOCAL_DIR/.download-monitor/manifest.json" --local-dir "$LOCAL_DIR"
```

只有完整checksum模式的`completed=true`才是该脚本的完成结论；元数据没有checksum时明确报告缺口。较新HF CLI也提供`hf cache verify`，使用前先查本机`--help`确认`--local-dir`和缺失文件处理选项；不因默认只警告missing就宣称全量成功。

最终检查下载命令退出码、同一revision的预期文件清单和大小；有校验信息时按可用工具核对，必要时验证索引引用的全部分片。进程消失、目录大小接近预期或进度条不动都不是成功证明。交付实际目录、来源/commit、完成状态、实测速率和PC依赖；脱敏后再分享日志。只停止本次创建且不再被使用的转发和监控进程。

## 官方参考

- [HF CLI下载](https://huggingface.co/docs/huggingface_hub/guides/cli#hf-download)
- [HF环境变量、调试及高性能模式](https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables)
- [Xet并发、缓冲和版本相关变量](https://huggingface.co/docs/hub/xet/using-xet-storage)
- [HTTPX证书环境变量](https://www.python-httpx.org/environment_variables/#ssl_cert_file)
- [.NET NegotiateAuthentication](https://learn.microsoft.com/en-us/dotnet/api/system.net.security.negotiateauthentication)
- [aria2并发、续传与checksum参数](https://aria2.github.io/manual/en/html/aria2c.html)
