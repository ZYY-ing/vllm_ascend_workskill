# vLLM Ascend Ops

供agent执行的昇腾模型部署与测试技能。覆盖SSH → 容器 → 配套源码 → vllm serve → 文本/多模态精度与性能 → profiling。包含HallusionBench推理与独立judge、OCRBench V2数据与AISBench测试。支持的模型和硬件以所选版本的官方教程及实际验证为准。

## 交给agent

将整个目录交给agent，要求先读取 [SKILL.md](SKILL.md)，再给它一份环境资料。只有SKILL.md而缺少references与scripts，不是完整交付。

支持技能目录的工具可将本目录放入其skills目录；例如Codex为~/.codex/skills/vllm-ascend-ops。其他agent直接读取SKILL.md和相对引用文件即可，不需要Codex专用工具。

将 [environment.example.md](environment.example.md) 复制为environment.local.md，填写SSH配置位置、服务器、容器、工作目录和权重路径；或者直接把这些信息写在任务中。认证引用本机凭据，技能不携带登录密钥。

已有Blue Server Toolkit配置的用户可让agent只读复用~/.blue_server_toolkit/config.json中的服务器清单。以本轮指定和environment.local.md优先，不要求额外安装Blue插件或把其docs复制到固定全局目录；SSH认证仍由agent实际执行机器提供。

示例任务：

> 使用vllm-ascend-ops和我的environment.local.md，在node0部署指定模型。先核对官方配方和镜像；需要源码时安装配套版本。使用4张空闲NPU，保留原始权重目录。服务验证后，运行32条16K/1K、4并发性能测试，再执行我指定的精度数据集。保存精简脚本、实际配置和完整日志。profiling另行采集20秒。

模型、服务器、测试指标可以分别替换；不会默认套用HY4量化/MTP参数。

## 上传GitHub

本目录内容可以直接作为仓库根目录上传，SKILL.md位于根目录；也可放到多技能仓库的skills/vllm-ascend-ops目录。保留文件相对结构。

仓库只提交通用技能与environment.example.md。environment.local.md、私钥、密码、Token、私有日志和模型文件不上传；网页手动上传时.gitignore不会替你过滤已选文件，需要自己不选择本地配置。交付使用独立文件夹，不包含本次运行目录、数据集或压缩包。

## 文件

- SKILL.md：agent入口与执行原则。
- references/：各阶段的短命令、参数选择和故障定位。
- references/weight-download.md：HF权重下载、容量检查、DNS/证书/认证排障、本地PC转发、多SSH隧道与实测估时。
- references/h200-source-build.md：H200/CUDA环境的指定vLLM源码编译、依赖排障、镜像保存、服务脚本、curl验证及思考标记评分适配学习文档。
- scripts/hf_weight_manifest.py：固定HF仓库commit和文件清单，离线校验本地LFS SHA256及Git blob SHA1；大小检查与checksum验收分开报告。
- scripts/windows_sspi_proxy.ps1：Windows当前用户的Negotiate认证转发，仅在企业上游代理需要该认证时使用。
- scripts/tcp_proxy_pool.py：将服务器回环代理连接分配到多条独立SSH隧道，可输出吞吐状态；不下载或缓存权重。
- references/hardware-network.md：宿主PID/容器归属、卡与chip映射、HCCL/fabric分层诊断。
- references/profiling-analysis.md：实验来源记录、逐forward/逐算子分析和对比口径。
- references/multimodal.md：视觉权重检查、HallusionBench下载/推理/独立评分、OCRBench V2配置、指标解释及采样预算。
- scripts/run_hallusionbench_hy4.py：Hallusion单独推理客户端；支持全量/limit、top-k/top-p/重复惩罚/特殊token/推理强度，保存原始响应及输入输出token均值，不运行OCR或judge。
- scripts/summarize_hallusion_scores.py：从完整裁判缓存离线生成overall、VS/VD和子类别aAcc的JSON/CSV；不调用API，校验样本与回答对应。
- scripts/download_hallusion_images.sh：在服务器下载镜像Parquet、恢复图片并打包ZIP；不是下载一个现成的镜像ZIP。
- scripts/make_chat_data.py：定长聊天输入及公共前缀数据生成/复核，按需使用。
- scripts/cache_delta.py：两次服务metrics的prefix cache差值，按需使用。

部署不依赖一键脚本；agent按实际环境生成简短的单机/node0/node1脚本。Python辅助脚本用于token校准、指标计算以及没有现成框架适配时的独立Hallusion推理。

文档基于2026-10-23可读取的[官方模型教程](https://docs.vllm.ai/projects/ascend/zh-cn/latest/tutorials/models/)、[安装指南](https://docs.vllm.ai/projects/ascend/zh-cn/latest/getting_started/installation.html)、[AISBench指南](https://docs.vllm.ai/projects/ascend/zh-cn/latest/developer_guide/evaluation/using_ais_bench.html)和[profiling指南](https://docs.vllm.ai/projects/ascend/zh-cn/latest/developer_guide/performance_and_debug/service_profiling_guide.html)整理。latest、镜像标签和main分支可变化，执行时核实目标版本，不把文档不同页的版本混搭。

多模态流程于2026-10-29补充请求参数、豆包独立judge、自动分类评分及token统计口径，来源见[多模态测试](references/multimodal.md)。未将个人服务器地址、私有实验成绩或API凭据作为技能默认配置。

## 融合来源与保留原则

参考[Blue Server Toolkit](https://github.com/xuchi-0808/blue-server-toolkit)的本地服务器配置、PID归属、挂载陷阱、开发版本配套、跨机诊断和trace分析经验，按本技能目标独立整理；来源在相关章节注明。未复制其脚本、七skill插件布局或全局运行时契约，也不依赖它安装后才能执行。

仍保留个人使用的核心：官方教程式短脚本、按模型与硬件选择参数、原始权重路径、先vim再AISBench、真实token与缓存验收、精度截断判读、完整日志交付。未引入默认全局pip改源、关闭TLS验证、强杀进程、固定采集时长或为了analyse自动停服的规则。需要裸机装机、改宿主网络或完整PD系统时按当前授权及对应官方教程另行处理，不扩大普通模型测试任务。
