# 环境资料示例

复制为environment.local.md并填写，或者在任务中提供等价资料。此文件供agent阅读，不需要额外配置解析程序；项目的实际值写入服务器RUNBOOK.md。以下IP为文档示例，不能直接连接。

## 连接

| 项目 | node0 | node1（可选） |
|---|---|---|
| SSH别名 | ascend-node0 | ascend-node1 |
| 管理IP | 192.0.2.10 | 192.0.2.11 |
| SSH用户/端口 | ops / 22 | ops / 22 |
| 容器名 | model-node0 | model-node1 |
| 通信IP/网卡 | 现场检查后填写 | 现场检查后填写 |

- 本地SSH配置：填写本机可访问的绝对路径，或说明使用默认~/.ssh/config。
- 认证：引用本机已有密钥/SSH Agent；不在此放私钥、密码或Token。
- 代理：不需要时写无；需要时说明本地代理端口与远端转发端口。
- 容器创建权限及允许使用的NPU：填写用户授权的设备，不能假定整机空闲。
- 硬件型号、物理卡与逻辑chip映射：现场核对，记录服务实际visible devices及对应宿主设备；不按其他机型推算。
- 节点角色：单机、DP rank、TP/PP分片、Prefill或Decode；角色和API地址分别填写。

## 项目

- 宿主与容器内工作目录：/srv/ascend-work（示例，两边同路径挂载）。
- 模型目录：/mnt/models/model；模型权重只读，需两节点都可见。
- 镜像：按NPU代际和目标版本填写完整tag，安装后记录digest。
- 必要挂载：分别记录宿主源、容器目标、文件/目录类型与只读属性；尤其是设备通信身份文件。
- vLLM Ascend仓库/分支：默认官方仓库，用户fork在此覆盖。
- Python：容器内command -v python的核实结果。
- API：http://192.0.2.10:8000；served-model-name=model。

## 本轮目标

模型名称/权重格式、单机或多机、TP/DP/PP、是否MTP/异步/图模式、精度数据集与输出预算、性能输入/输出长度/并发/条数、缓存条件、是否采集profiling。未指定项由模型配方与资源决定，不继承其他模型的特殊配置。

## 可选：已有Blue Toolkit配置

只在用户已使用该工具集且文件存在时读取~/.blue_server_toolkit/config.json。根据servers[].alias选择目标，映射host/user/port/container；default_server仅作为未指定目标时的候选。SSH配置路径及密钥机制仍从用户当前机器核对，不能认为别名自动等于~/.ssh/config中的Host条目。

workspaces中的code_root、weights_root、task_root是候选路径，不自行创建或迁移，也不能覆盖用户指定的唯一工作目录。模型/硬件、获授权设备、通信IP/网卡、Python、镜像和API通常仍需现场补齐。notes仅按当前任务读取，不批量加载个人历史。

不写回Blue配置，不自动导入其命令字符串或限制列表作为可执行代码。若用户另有明确的本地操作规则，应读取并遵循；已有授权不因此被重复询问。此可选入口仅为复用服务器清单，完整技能仍可独立分发。
