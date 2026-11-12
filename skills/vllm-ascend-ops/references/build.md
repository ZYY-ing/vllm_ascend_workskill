# 配套源码与安装

先从目标模型对应版本的教程、发布兼容矩阵或用户fork说明确定整套软件。容器内所有pip都用选定的同一个Python；不要先卸载可工作的vLLM。源码安装需要CANN/编译工具，现有镜像依赖可复用；普通服务验证不必强行从源码重编。

## 拉取配套源码

在用户工作目录设置变量：WORK为项目根、PYTHON为实际解释器、ASCEND_REPO/ASCEND_REF为所需仓库与分支/tag。例如官方仓库https://github.com/vllm-project/vllm-ascend.git；用户fork可覆盖，不固化历史HY4分支。

```bash
mkdir -p "$WORK/code" "$WORK/logs"
cd "$WORK/code"
git clone --branch "$ASCEND_REF" "$ASCEND_REPO" vllm-ascend
git clone https://github.com/vllm-project/vllm.git
```

已有目录直接进入，不重复clone。在需要代理时仅为git命令加-c http.proxy=...。先判断插件checkout属于哪类，再读取对应配套依据：

| 插件代码 | vLLM配套依据 |
|---|---|
| release tag或发布维护分支 | 该发布版本的说明/兼容矩阵，及分支中的.github/vllm-release-tag.commit（若使用） |
| main或main2main开发路线 | 该checkout的.github/vllm-main-verified.commit及CI安装方式；不能用滞后的release tag代替开发锚点 |
| 用户fork、自定义分支或PR | fork/PR说明与CI实际checkout；可能延续release，也可能跟随main，不凭分支名字猜测 |

按当前checkout选择需要的一条命令，不把两者都读出后任取一个：

```bash
# release路线，核对发布说明后读取
cat "$WORK/code/vllm-ascend/.github/vllm-release-tag.commit"
```

```bash
# main2main路线，核对CI后读取
cat "$WORK/code/vllm-ascend/.github/vllm-main-verified.commit"
```

将核实的tag/SHA赋给VLLM_REF，并记录配套依据、插件完整SHA和核心完整SHA。文件缺失或与CI矛盾时读取该版本文档/CI，不改成安装最新核心；文件内容是数据，不作为shell脚本执行。

```bash
git -C "$WORK/code/vllm" checkout "$VLLM_REF"
cd "$WORK/code/vllm"
VLLM_TARGET_DEVICE=empty "$PYTHON" -m pip install --no-build-isolation --no-deps -v -e .
cd "$WORK/code/vllm-ascend"
"$PYTHON" -m pip install --no-build-isolation --no-deps -v -e .
```

上述是已有配套依赖的开发安装路线，不负责从空系统装CANN。核心empty避免构建CUDA；是否需额外构建选项以目标版本说明为准。缺setuptools-rust等构建包按首个error补齐；装了Python构建包不等于系统Rust编译器存在。原生算子构建的SOC_VERSION、COMPILE_CUSTOM_KERNELS和并行度只按实际硬件/分支需要设置，不能将950DT值用于A2/A3。

--no-deps避免安装时自动替换已验证的torch栈，但也不会补缺包；先核实依赖，再针对性安装。缺少匹配依赖则使用官方完整安装路线，不无故升级所有包。CANN环境未初始化时source实际set_env.sh，不能写死作者的Python或OPP路径。

使用--no-build-isolation前，读该checkout的pyproject.toml/build-system及构建说明，核对setuptools、setuptools-scm、setuptools-rust和工具链。按实际要求补齐，不将某分支的setuptools最低版本或VLLM_VERSION_OVERRIDE写成所有版本默认值。常规源码编译主要使用CPU/内存/磁盘，不以NPU空闲为前提；构建后若运行NPU测试或拉服务，再核对设备授权和占用。

安装包前使用当前网络可达、可信的索引。索引页可访问不等于大wheel下载正常；停在Downloading时结合下载文件增长、网络和落盘状态判断，限制探测时间后更换可信源。优先本次命令-i或venv级配置，不自动改用户全局pip源，不默认加trusted-host或关闭TLS。

rsync/scp同步后遇到dubious ownership或metadata失败，先对照容器内id、仓库stat/owner和Git报错。仅在用户拥有且允许更改的源码目录修正属主；不递归chown整个/home、权重目录或他人文件，不自动全局safe.directory=*。同步时明确是否包含.git，按任务排除不需要的构建产物/venv/权重，不默认rsync --delete，不把ZIP覆盖称为git更新。

长构建将实际命令写build.sh，用set -o pipefail和tee保存完整回显、真实退出码。clone尚在下载时检查其PID、目录增长/网络错误；不要再起另一份clone。两机分别核对完整SHA，不能只看分支同名。

## 更新已有分支

```bash
cd "$WORK/code/vllm-ascend"
git status --short
git fetch origin "$ASCEND_REF"
git merge --ff-only "origin/$ASCEND_REF"
git rev-parse HEAD
```

此例ASCEND_REF为分支。远端最新是本次fetch结果，不是技能写死的SHA。仅FETCH_HEAD变化不证明HEAD更新；需要时显式refspec更新remote-tracking ref。工作树有改动先看diff；用户明确放弃跟踪文件修改时，成功fetch后可reset --hard对应远端，不附带git clean。没获得放弃授权则保留修改，不擅自覆盖。

只有Python源码变化且editable导入正确时，通常重启服务即可；原生算子/CMake/ABI变化需要重编。配套核心要求变化时再更新核心，不每次卸载两套软件。

## 验证实际导入

```bash
"$PYTHON" - <<'PY'
import sys
import importlib.metadata as m
import vllm, vllm_ascend, torch_npu
print(sys.executable, vllm.__file__, vllm_ascend.__file__, sep='\n')
for name in ('vllm', 'vllm-ascend', 'torch', 'torch-npu', 'transformers'):
    print(name, m.version(name))
PY
command -v vllm
vllm serve --help > "$WORK/logs/serve-help.txt"
```

确认vllm shebang也指选定Python；不能pip装在系统环境却从旧venv启动。按该分支实际原生模块路径检查.so可导入；版本号相同不代表editable源码相同。保存完整HEAD、导入路径和必要依赖版本；Transformers会参与模型配置读取，也是兼容组合的一部分。编译与导入成功后才进入服务验证。

import与serve --help可能不触发全部插件补丁；按[服务验收](serve.md)实际拉起并请求一次，才能暴露核心API与插件补丁不兼容。不要仅凭import成功就报告版本组合已验证。
