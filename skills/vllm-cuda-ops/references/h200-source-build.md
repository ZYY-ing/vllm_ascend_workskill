# H200 在容器中编译指定 vLLM 源码并启动服务

这份学习文档从已有 NVIDIA 镜像出发，说明如何保留宿主机原始源码，在容器内编译你选定的 vLLM fork，保存镜像，再启动 OpenAI 兼容 API 并用 curl 验证。主体流程适用于 NVIDIA CUDA；HY4 的依赖、量化和 MTP 参数作为独立示例。所有服务器、路径和名称均为占位示例，不包含个人账号、网络地址、Token 或私有实验结果。

## 1. 先理解四个对象

| 对象 | 在本例中的位置 | 作用 |
|---|---|---|
| 基础镜像 | `vllm/vllm-openai:v0.30.0` | 提供 Linux、Python、CUDA/PyTorch 等环境，里面的 vLLM 不自动等于你选的 fork |
| 开发容器 | `model-h200` | 编译和运行发生的地方；容器可写层中的修改只有保存为镜像才方便复用 |
| 原始源码 | 宿主机 `$SOURCE_DIR`，挂到容器 `/input/vllm` | 只读输入，不在这里安装或修改依赖文件 |
| 运行源码与 Python | `/opt/vllm/src`、`/opt/vllm/.venv` | 在副本中编译；服务明确调用这个 Python 环境里的 vLLM |

**挂载源码或设置 `PYTHONPATH` 只改变 Python 查找路径，不会重新编译 C++、CUDA、Rust 扩展。** 一个能运行旧版本 vLLM 的镜像，也不保证能直接运行新 fork。要同时核对源码、扩展、Torch、CUDA、Python ABI 和模型实现。

## 2. 在宿主机确认条件

```bash
nvidia-smi
docker version
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
docker image inspect vllm/vllm-openai:v0.30.0 --format '{{.Id}} {{.Size}}'
df -h /srv
ss -lntp | grep ':8000 ' || true
```

H200 属于 Hopper、计算能力为 9.0。`nvidia-smi` 显示的 CUDA Version 是驱动支持上限，不是容器里的 nvcc 版本。还要在容器内检查 `nvcc --version`、`torch.version.cuda` 和实际 NCCL。

检查 GPU 占用的 PID、所属容器和命令；只创建容器并不意味着已获准停止现有服务。选定空闲 GPU/端口，或按用户明确授权定向停止冲突的推理服务。不要全局 `pkill python`、`pkill vllm`。

权重先按[下载与验收](https://github.com/ZYY-ing/vllm_ascend_workskill/blob/main/skills/weight-download/references/weight-download.md)完成固定 revision 的清单和 checksum 检查。名字里有 share 不等于另一个分区，Docker 镜像、编译缓存和权重也可能争用同一磁盘。

## 3. 创建一个只等待命令的开发容器

以下命令在宿主机执行；把三个目录替换为你的实际路径。跟npu启动容器脚本相比更简洁，因为昇腾必须逐个 device 文件挂，因为 Ascend 驱动不走 nvidia-container-runtime 那套插件机制。昇腾容器没有像 NVIDIA 那样的 runtime 插件自动注入驱动库 ，所以必须手工把驱动、工具链、诊断二进制全挂进去，不然容器里`npu-smi` 、`torch_npu` 都找不到。

```bash
export BASE_IMAGE='vllm/vllm-openai:v0.30.0'
export CONTAINER='model-h200'
export WORK_DIR='/srv/work/model-h200'
export SOURCE_DIR='/srv/source/vllm-custom'
export MODEL_DIR='/srv/models/model'

test -f "$SOURCE_DIR/pyproject.toml"
test -d "$MODEL_DIR"
mkdir -p "$WORK_DIR/logs"
export BASE_ID="$(docker image inspect "$BASE_IMAGE" --format '{{.Id}}')"

docker run -d --init --pull=never \ # `-d --init` ：后台 + 启一个 PID 1 init 进程（处理僵尸）;`--pull=never` ： 从不自动拉 ，依赖本地已有镜像
  --name "$CONTAINER" \
  --gpus all \ # NVIDIA 全卡透传
  --network host \ # 容器和宿主机共享网络栈（直接绑定宿主机端口）
  --shm-size=32g \
  --ulimit memlock=-1 --ulimit stack=67108864 \
  --mount "type=bind,source=$SOURCE_DIR,target=/input/vllm,readonly" \ # 代码/脚本目录只读 挂进去
  --mount "type=bind,source=$MODEL_DIR,target=/models/model,readonly" \
  --mount "type=bind,source=$WORK_DIR,target=/workspace,readonly" \
  --mount "type=bind,source=$WORK_DIR/logs,target=/var/log/model" \ # 日志目录读写 挂到容器`/var/log/hy4` （唯一可写路径）
  --entrypoint /bin/bash \
  "$BASE_ID" -lc 'exec sleep infinity' # 容器启动后只 sleep 永远不退出 ， 不自动起任何服务
```

`--entrypoint` 覆盖镜像默认的服务入口，所以这里只创建容器，不启动模型。`--network host` 下容器和宿主机共享端口；不能再把 `-p 8000:8000` 当成端口隔离。同名容器已存在时先检查，不删旧容器强行重建。

本例权重始终在 `/models/model`，日志写回宿主机；这两个 bind mount 的内容不会被 `docker commit` 打包进镜像。

## 4. 在容器内复制源码并确认基础依赖

```bash
docker exec -it "$CONTAINER" bash
```

下面直到“保存镜像”前的命令在容器内执行：

```bash
mkdir -p /opt/vllm
test ! -e /opt/vllm/src
cp -a /input/vllm /opt/vllm/src
cd /opt/vllm/src

/usr/bin/python3 --version
nvcc --version
/usr/bin/python3 -c 'import torch; print(torch.__version__, torch.version.cuda); print(torch.cuda.nccl.version())'
git rev-parse HEAD 2>/dev/null || true
```

记录源码 commit；ZIP 没有 Git 元数据时记录原始 ZIP 的 SHA256、解压来源和构建版本标记。不能把人为设置的 `0.0.0+local` 当成上游发行版本。

核对 fork 的 `pyproject.toml`、`requirements/build/cuda.txt`、`requirements/cuda.txt` 和 README。某个新 fork 需要的 Torch/FlashInfer/Rust 可能比基础镜像更晚；先解决版本组合，不用旧二进制强行冒充新代码。

在一个已验证的 HY4 fork 组合中使用过 Python 3.12、Torch 2.13.0+cu130、CUDA 13.0、NCCL 2.29.7、FlashInfer 0.7.0.post1。这个组合是案例，不是所有 fork 的统一版本要求。

## 5. 建立专用 Python 环境并安装构建依赖

如果基础镜像的 Torch 已确认兼容，可复用其安装，减少重复下载。`--system-site-packages` 也会继承旧包，必须检查后文的 FlashInfer/NCCL 冲突；如果需要完全不同的 Torch，建立独立环境并按 fork 安装匹配的 CUDA wheel。

```bash
uv venv --python /usr/bin/python3 --system-site-packages /opt/vllm/.venv
export PATH="/opt/vllm/.venv/bin:$PATH"
python -c 'import sys,torch; print(sys.executable); print(torch.__version__, torch.version.cuda)'

apt-get update
apt-get install -y git pkg-config libdw-dev libelf-dev ccache
```

这些 apt 操作只发生在独立容器。需要代理或企业 CA 时只给本次构建进程配置可信 CA 和代理；不关闭 TLS，也不把企业证书、认证信息或代理口令复制进公共构建上下文。

在支持该工具的 fork 中，[官方的复用 Torch 安装方法](https://docs.vllm.ai/en/latest/getting_started/installation/gpu/#use-an-existing-pytorch-installation)是先调整运行副本的构建依赖，再关闭构建隔离。只在确认该 Torch 与 fork 兼容后使用：

```bash
cd /opt/vllm/src
python tools/use_existing_torch.py
uv pip install --python /opt/vllm/.venv/bin/python -r requirements/build/cuda.txt
uv pip install --python /opt/vllm/.venv/bin/python -r requirements/cuda.txt
```

如果 fork 没有这个工具，按该分支自己的安装说明执行，不手工把 Torch 版本约束全部删掉。Rust 扩展需要匹配的 `rustc`/`cargo`；检查 `rust-toolchain.toml` 和 `Cargo.lock`，必要时通过 Rust 官方 rustup 安装所需工具链，再确认 `rustc --version`、`cargo --version`。下载 Rust crates 也需要正确的代理和 CA。

### NCCL 与镜像里的 uv override

有些镜像设置了 `UV_OVERRIDE`，会覆盖你请求的依赖版本。先看设置与内容，再核对 Torch 的真实要求：

```bash
printf 'UV_OVERRIDE=%s\n' "${UV_OVERRIDE:-}"
python - <<'PY'
from importlib.metadata import requires
print('\n'.join(x for x in requires('torch') or [] if 'nccl' in x.lower()))
PY
```

例如，某个 Torch 明确要求 `nvidia-nccl-cu13==2.29.7`，而镜像 override 固定了其他版本，才针对该组合使用：

```bash
env -u UV_OVERRIDE uv pip install --python /opt/vllm/.venv/bin/python 'nvidia-nccl-cu13==2.29.7'
printf '%s\n' 'nvidia-nccl-cu13==2.29.7' > /opt/vllm/uv-overrides.txt
export UV_OVERRIDE=/opt/vllm/uv-overrides.txt
```

不要把这个 NCCL 版本无条件套给别的 Torch。安装后同时检查包元数据与 `torch.cuda.nccl.version()`。

## 6. 完整编译和安装你自己的 wheel

为 H200 构建时设置目标架构。并发按 CPU、内存和磁盘调整，先从 8～16 开始；64 是资源充足的大机器上的案例值。

```bash
cd /opt/vllm/src
export TORCH_CUDA_ARCH_LIST='9.0'
export MAX_JOBS=16
export NVCC_THREADS=1
export CARGO_BUILD_JOBS=8
ccache --max-size 8G

# ZIP缺少版本信息、且该fork支持此变量时，使用明确的本地构建标签。
export VLLM_VERSION_OVERRIDE='0.0.0+local'
mkdir -p /opt/vllm/dist
uv build --python /opt/vllm/.venv/bin/python --wheel --no-build-isolation \
  --out-dir /opt/vllm/dist . > /var/log/model/build.log 2>&1
```

读取日志时另开终端 `tail -F "$WORK_DIR/logs/build.log"`。编译命令的真实退出码必须为0；看到几个 `.so` 文件、日志末尾没有 ERROR，或 `tail` 自己退出0，都不能代替构建成功。

先确认 dist 中只有本次目标 wheel，再安装；不要混用旧编译产物：

```bash
mapfile -t WHEELS < <(find /opt/vllm/dist -maxdepth 1 -type f -name 'vllm-*.whl')
test "${#WHEELS[@]}" -eq 1
uv pip install --python /opt/vllm/.venv/bin/python "${WHEELS[0]}"
uv pip check --python /opt/vllm/.venv/bin/python
```

本例后面的服务会从 `/opt/vllm/src` 加载代码，因此在安装 wheel 后，接着使用该 HY4 fork 支持的 editable 安装，复用**刚刚自己编译的同一份 wheel**，让运行源码也能找到本轮原生扩展：

```bash
VLLM_USE_PRECOMPILED=1 VLLM_PRECOMPILED_WHEEL_LOCATION="${WHEELS[0]}" \
  uv pip install --python /opt/vllm/.venv/bin/python --no-build-isolation -e .
```

这与从旧发行包直接借一个二进制不同。wheel 必须与当前源码、Python、Torch、CUDA和目标架构对应；改 C++/CUDA/Rust 后仍要重编译。纯 Python 编辑也要在服务重启后才会被已运行的进程加载。

换其他 fork 时先确认它支持这些变量。若只安装普通 wheel、不做 editable 安装，就让服务从venv的site-packages加载，**删去后文脚本和镜像中的 `PYTHONPATH=/opt/vllm/src`**；不要用没有原生扩展的源码目录遮住已安装的wheel。

## 7. HY4 案例中的 CUDA 和 FlashInfer 修复

只在出现相应错误时应用，不把本节当成所有环境的必装补丁。

| 报错 | 原因与处理 |
|---|---|
| `flashinfer-jit-cache ... does not match flashinfer` | 专用venv继承了基础镜像的旧可选AOT缓存。先比较 python/cubin/jit-cache 版本；安装匹配缓存，或移除本容器内那份不匹配的可选缓存并允许JIT。不要关闭版本检查掩盖冲突 |
| `nvrtc.h: No such file` | 编译器找不到已安装NVRTC头文件，补充选择性的头文件目录 |
| `cannot find -lnvrtc` | 链接器找不到 `libnvrtc.so` 链接名，可能只有 `.so.13`。创建私有链接目录并设置 `LIBRARY_PATH` |
| 运行时找不到 `libnvrtc.so.13` | 在服务进程设置匹配的 `LD_LIBRARY_PATH`；不要把CUDA驱动stub目录放入运行时路径 |
| CUDA launch/CRT 声明冲突 | nvcc与另一个CUDA包的CRT头被混用。保留 `/usr/local/cuda` 自己的CRT，只引入缺少的库头文件 |

先查实际包路径。以下例子仅对应 Python 3.12、`nvidia/cu13` 包布局：

```bash
export CUDA_PKG='/opt/vllm/.venv/lib/python3.12/site-packages/nvidia/cu13'
test -f "$CUDA_PKG/include/nvrtc.h"
test -f "$CUDA_PKG/lib/libnvrtc.so.13"
mkdir -p /opt/vllm/cuda-library-headers /opt/vllm/cuda-library-libs
ln -sfn "$CUDA_PKG/include/nvrtc.h" /opt/vllm/cuda-library-headers/nvrtc.h
ln -sfn "$CUDA_PKG/lib/libnvrtc.so.13" /opt/vllm/cuda-library-libs/libnvrtc.so
ln -sfn "$CUDA_PKG/lib/libnvrtc.so.13" /opt/vllm/cuda-library-libs/libnvrtc.so.13
export CPATH="/opt/vllm/cuda-library-headers${CPATH:+:$CPATH}"
export LIBRARY_PATH="/opt/vllm/cuda-library-libs${LIBRARY_PATH:+:$LIBRARY_PATH}"
export LD_LIBRARY_PATH="/opt/vllm/cuda-library-libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
```

缺其他库头文件时按错误逐个确认并引入。**不要把整个 `nvidia/cu13/include` 直接置于全局 CPATH 前面**，否则它的CRT可能抢先于nvcc配套头文件。CMake单独找不到NVRTC库时，此案例还使用过：

```bash
export CMAKE_ARGS="-DCUDA_nvrtc_LIBRARY=$CUDA_PKG/lib/libnvrtc.so.13"
```

如需移除继承的旧可选缓存，只在自己的开发容器里执行，先确认它来自全局Python且版本确实不匹配：

```bash
python -m pip show flashinfer-python flashinfer-cubin flashinfer-jit-cache
uv pip uninstall --python /usr/bin/python3 flashinfer-jit-cache
```

优先单独编译失败的JIT目标，确认编译/链接成功后再重新加载数百GB权重。JIT动态库依赖Torch/TVM FFI时，直接 `ctypes.CDLL` 前没有加载相应运行库也会出现未定义符号，不能据此就判定算子损坏。

## 8. 验证真正安装了哪份代码

```bash
export PYTHONPATH=/opt/vllm/src
/opt/vllm/.venv/bin/python - <<'PY'
import sys, torch, vllm
print('python:', sys.executable)
print('vllm:', vllm.__file__)
print('torch:', torch.__version__, 'cuda:', torch.version.cuda)
print('nccl:', torch.cuda.nccl.version())
PY
/opt/vllm/.venv/bin/vllm serve --help > /var/log/model/serve-help.txt
```

再按本次构建产物导入原生扩展。例如部分新分支使用 `vllm._C_stable_libtorch`、`vllm._moe_C_stable_libtorch`、`vllm._flashmla_C`；旧分支可能用 `_C`。不要只因旧扩展名导入失败就重装；以该分支安装产物为准。

CPU导入和参数解析通过，仍不等于权重、GPU算子、长上下文、MTP和CUDA图组合能推理成功，后面必须经过真实服务请求。

## 9. 从现有容器保存镜像

**可以基于已有 `vllm/vllm-openai:v0.30.0` 容器创建镜像。** 完成编译后、模型还没启动时，退出容器Shell，在宿主机保存：

```bash
docker commit \
  --change 'ENV PATH=/opt/vllm/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' \
  --change 'ENV PYTHONPATH=/opt/vllm/src' \
  model-h200 local/vllm-custom:h200-build1
docker image inspect local/vllm-custom:h200-build1 --format '{{.Id}} {{.Size}}'
```

`docker exec` 中临时 `export` 的变量不自动成为新镜像的ENV；UV override、CUDA路径等要在启动脚本或Dockerfile中明确设置。镜像内可能同时保留旧全局vLLM和新venv，启动时始终明确使用 `/opt/vllm/.venv/bin/vllm`。

默认commit会暂停目标容器，避免对正在服务的容器临时这样操作。权重、只读原始源码和挂载日志不会进入镜像；但容器可写层中的编译缓存、下载凭据、构建日志会进入，保存前检查，长期交付优先用固定基础镜像digest和Dockerfile复现。大构建缓存会让镜像非常大。

Dockerfile使用 `FROM local/...` 时，某些独立BuildKit builder看不到宿主机本地镜像，会尝试向registry查询。选择能访问该基础镜像的builder或发布到获授权的registry；只针对自己的构建切换，不为此重启Docker或改全局daemon。

新建容器时仍要提供模型、日志和脚本挂载，并按第3节覆盖entrypoint创建idle容器。`docker save`导出镜像不会导出权重。

## 10. 保存并运行服务启动脚本

以下保存为宿主机 `$WORK_DIR/start_server.sh`，经只读挂载后在容器内是 `/workspace/start_server.sh`。这是**8张H200上的HY4案例参数**，其他模型按其源码与权重配方修改。

```bash
#!/usr/bin/env bash
set -euo pipefail
export PATH=/opt/vllm/.venv/bin:$PATH
export PYTHONPATH=/opt/vllm/src
export CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
export VLLM_WORKER_MULTIPROC_METHOD=spawn
export PYTORCH_ALLOC_CONF=expandable_segments:True
export HF_HUB_OFFLINE=1
# 仅在第7节确实建立过这些目录时保留：
export CPATH="/opt/vllm/cuda-library-headers${CPATH:+:$CPATH}"
export LIBRARY_PATH="/opt/vllm/cuda-library-libs${LIBRARY_PATH:+:$LIBRARY_PATH}"
export LD_LIBRARY_PATH="/opt/vllm/cuda-library-libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

exec /opt/vllm/.venv/bin/vllm serve /models/model \
  --host 0.0.0.0 --port 8000 --served-model-name hy4 \
  --data-parallel-size 1 --tensor-parallel-size 8 \
  --enable-expert-parallel --distributed-executor-backend mp \
  --dtype bfloat16 --limit-mm-per-prompt '{"image":1,"video":0}' \
  --max-num-seqs 256 --max-model-len 147456 \
  --max-num-batched-tokens 8192 --gpu-memory-utilization 0.85 \
  --enable-prefix-caching --async-scheduling --seed 0 \
  --compilation-config '{"cudagraph_mode":"FULL_DECODE_ONLY"}' \
  --speculative-config '{"method":"mtp","num_speculative_tokens":3,"draft_load_config":{}}'
```

CUDA环境不传 `--quantization ascend`、HCCL、NPU分配器或Ascend专属additional-config。这个案例由权重配置识别FP8线性层和MXFP4专家；`dtype=bfloat16`不等于把整份FP4权重都按BF16存放。

先 `bash -n "$WORK_DIR/start_server.sh"`，检查显存、端口及该fork的`serve --help`，再启动；不要覆盖已有运行。宿主机执行：

```bash
docker exec -d model-h200 bash -c \
  'echo $$ > /var/log/model/server.pid; exec bash /workspace/start_server.sh > /var/log/model/server.log 2>&1'
tail -F "$WORK_DIR/logs/server.log"
```

PID文件里的值是**容器PID**，不能直接在宿主机kill这个数字。进程可能退出或PID被重用，停止前再次核对容器、命令和启动时间。独立容器只运行本服务时也可对该容器做有针对性的优雅停止。

首次启动可能依次经历：8卡通信初始化 → 权重与MTP加载 → 显存分析 → JIT编译 → autotune → CUDA Graph捕获 → API就绪。`No available shared memory broadcast block ...60 seconds`可能是等待编译；结合编译器CPU活动、日志进展和最终异常判断，不凭这一行杀服务。

## 11. 用 curl 分层验证

在服务器本机执行。远端访问把127.0.0.1换为获准访问的服务地址；如启用了API key，使用私有环境变量传入，不写进文档或Git。

```bash
# 1. 进程是否已开放健康接口
curl --noproxy '*' --fail --connect-timeout 5 http://127.0.0.1:8000/health
# 2. 模型名是否为启动时的served-model-name
curl --noproxy '*' --fail http://127.0.0.1:8000/v1/models
# 3. 非流式请求，模型名必须与上一步一致；省略temperature以使用服务默认值
curl --noproxy '*' --fail --max-time 300 http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"hy4","messages":[{"role":"user","content":"Reply with OK."}],"max_tokens":512,"ignore_eos":false,"stream":false}' \
  -o /tmp/model-smoke-response.json

python - <<'PY'
import json
r=json.load(open('/tmp/model-smoke-response.json'))
c=r['choices'][0]
print('content:', c['message'].get('content'))
print('reasoning:', c['message'].get('reasoning_content',c['message'].get('reasoning')))
print('finish_reason:', c['finish_reason'])
print('usage:', r.get('usage'))
PY
```

检查`choices`、真实`usage`和最终答案。HTTP200只能说明请求被接受；思考模型若`finish_reason=length`且只有思考，没有最终答案，需提高烟测输出预算后复验，不能当完成回答。

流式请求用于观察首token和持续输出，`curl -N`避免本地缓冲；`stream_options`请求最后的usage：

```bash
curl --noproxy '*' -N --fail --max-time 300 http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"hy4","messages":[{"role":"user","content":"Reply with OK."}],"max_tokens":512,"ignore_eos":false,"stream":true,"stream_options":{"include_usage":true}}'
curl --noproxy '*' --fail http://127.0.0.1:8000/metrics -o /tmp/model-metrics.txt
```

不要在正式性能测试中夹杂额外请求。测试前的短请求只验证服务，不对正式样本预热；长负载完成后再核对该负载的成功数、token和指标。

## 12. 显存配置和测试并发的关系

`max-num-seqs=256`是调度上限，不承诺能同时放下256条最大上下文。还要看模型本体、激活、CUDA图和KV cache。在一个8卡H200、0.85利用率的HY4案例中，每卡模型约60.56 GiB，最终KV容量约51.06 GiB、583744 tokens；日志给出的147456长度驻留并发约3.96。

所以客户端并发16的128K测试可能包含排队和调度影响，不能描述成16条满长同时驻留。报告整体吞吐、TTFT、TPOT以及缓存条件；单条只有1个输出token时TPOT不适用。MTP会批量接受多个token，流式分块到达间隔也不必等于逐token解码间隔。

## 13. 思考标记与评分

GPQA答案提取属于模型评测任务，已迁到 `model-evaluation` skill 的 `references/answer-extraction.md`。编译和服务健康不能代替评分链路验收。

## 14. 每次交付保存什么

保存基础镜像digest、新镜像ID、源码commit/ZIP hash、构建日志与退出码、依赖版本、原生扩展导入位置、启动脚本、实际日志、curl响应、权重revision和清单。测试另存AISBench源码commit、模型/数据集配置、请求审计与原始评分文件；离线修正评分时保留旧结果并标明提取规则变化。

先分清“容器创建成功”“源码编译成功”“服务启动成功”“指定测试通过”。后一次换源码或换依赖后，要从受影响的阶段重新验证，不能复用旧版本的健康结论。

官方参考：[vLLM GPU源码安装](https://docs.vllm.ai/en/latest/getting_started/installation/gpu/)、[vLLM Docker部署](https://docs.vllm.ai/en/latest/deployment/docker/)、[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)。具体fork以该commit自带说明、依赖和实测为准。
