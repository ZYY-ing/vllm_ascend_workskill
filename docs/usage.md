# 技能使用与交付说明

供agent执行的昇腾模型部署与测试技能。覆盖SSH → 容器 → 配套源码 → vllm serve → 文本/多模态精度与性能 → profiling。包含HallusionBench推理与独立judge、OCRBench V2数据与AISBench测试。支持的模型和硬件以所选版本的官方教程及实际验证为准。

## 交给agent

将选定的整个 skill 目录交给agent，要求先读取 各技能目录中的 `SKILL.md`，再给它一份环境资料。只有SKILL.md而缺少references与scripts，不是完整交付。

支持技能目录的工具可将本目录放入其skills目录；例如使用用户工具的本地 skills 目录。其他agent直接读取SKILL.md和相对引用文件即可，不需要Codex专用工具。

将 [environment.example.md](../skills/vllm-ascend-ops/assets/environment.example.md) 复制为environment.local.md，填写SSH配置位置、服务器、容器、工作目录和权重路径；或者直接把这些信息写在任务中。认证引用本机凭据，技能不携带登录密钥。

已有Blue Server Toolkit配置的用户可让agent只读复用~/.blue_server_toolkit/config.json中的服务器清单。以本轮指定和environment.local.md优先，不要求额外安装Blue插件或把其docs复制到固定全局目录；SSH认证仍由agent实际执行机器提供。

示例任务：

> 使用vllm-ascend-ops和我的environment.local.md，在node0部署指定模型。先核对官方配方和镜像；需要源码时安装配套版本。使用4张空闲NPU，保留原始权重目录。服务验证后，运行32条16K/1K、4并发性能测试，再执行我指定的精度数据集。保存精简脚本、实际配置和完整日志。profiling另行采集20秒。

模型、服务器、测试指标可以分别替换；不会默认套用HY4量化/MTP参数。

## 上传GitHub

单个 skill 目录可以单独分发；多技能仓库统一放在 `skills/<name>/`。保留所选 skill 的相对结构，发布前按根 CONTRIBUTING.md 检查。

仓库只提交通用技能与environment.example.md。environment.local.md、私钥、密码、Token、私有日志和模型文件不上传；网页手动上传时.gitignore不会替你过滤已选文件，需要自己不选择本地配置。交付使用独立文件夹，不包含本次运行目录、数据集或压缩包。

部署不依赖一键脚本；agent按实际环境生成简短的单机/node0/node1脚本。Python辅助脚本用于token校准、指标计算以及没有现成框架适配时的独立Hallusion推理。
