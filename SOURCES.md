# 参考来源与内容归属

## 本次结构与Hallusion扩充参考

- [Blue Server Toolkit](https://github.com/xuchi-0808/blue-server-toolkit/tree/5707a86922713f830f1f5fea2bedbb0a0a1cdc3a)：参考按任务拆分、技能选择验收及仓库检查思路；没有复制其插件清单、固定全局目录、全局pip改源或整段运行契约。
- [HY4并发测试与评分说明](https://github.com/ZYY-ing/Hy4-preview-deployment-guide/blob/14975be2c67e92c35abff48be6754a1b83dae982/HY4_%E5%8F%8C%E6%9C%BA/%E5%A4%9A%E6%A8%A1%E6%80%81%E6%B5%8B%E8%AF%95/HallusionBench_%E5%B9%B6%E5%8F%91%E6%B5%8B%E8%AF%95%E4%B8%8E%E8%AF%84%E5%88%86%E8%AF%B4%E6%98%8E.md)与[工具代码](https://github.com/ZYY-ing/Hy4-preview-deployment-guide/tree/14975be2c67e92c35abff48be6754a1b83dae982/HY4_%E5%8F%8C%E6%9C%BA/%E5%A4%9A%E6%A8%A1%E6%80%81%E6%B5%8B%E8%AF%95/Hallusionbench)：共用核心脚本保留；run_full的调用流程和可选鉴权检查按可移植配置扩充，保留通用并发裁判而非复制厂商专用实现。不复制图片、数据集、依赖包或运行结果。
- 官方HallusionBench代码由用户在运行项目中按其许可取得，离线测试仅读取已存在的官方源码。原有来源和指标说明保留如下。

## 原有来源与保留原则

文档基于2026-10-23可读取的[官方模型教程](https://docs.vllm.ai/projects/ascend/zh-cn/latest/tutorials/models/)、[安装指南](https://docs.vllm.ai/projects/ascend/zh-cn/latest/getting_started/installation.html)、[AISBench指南](https://docs.vllm.ai/projects/ascend/zh-cn/latest/developer_guide/evaluation/using_ais_bench.html)和[profiling指南](https://docs.vllm.ai/projects/ascend/zh-cn/latest/developer_guide/performance_and_debug/service_profiling_guide.html)整理。latest、镜像标签和main分支可变化，执行时核实目标版本，不把文档不同页的版本混搭。

多模态流程于2026-10-29补充请求参数、豆包独立judge、自动分类评分及token统计口径，来源见[多模态测试](skills/model-evaluation/references/multimodal.md)。未将个人服务器地址、私有实验成绩或API凭据作为技能默认配置。

## 融合来源与保留原则

参考[Blue Server Toolkit](https://github.com/xuchi-0808/blue-server-toolkit)的本地服务器配置、PID归属、挂载陷阱、开发版本配套、跨机诊断和trace分析经验，按本技能目标独立整理；来源在相关章节注明。未复制其脚本、七skill插件布局或全局运行时契约，也不依赖它安装后才能执行。

仍保留个人使用的核心：官方教程式短脚本、按模型与硬件选择参数、原始权重路径、先vim再AISBench、真实token与缓存验收、精度截断判读、完整日志交付。未引入默认全局pip改源、关闭TLS验证、强杀进程、固定采集时长或为了analyse自动停服的规则。需要裸机装机、改宿主网络或完整PD系统时按当前授权及对应官方教程另行处理，不扩大普通模型测试任务。

## 可公开来源

- [HallusionBench代码与指标](https://github.com/tianyi-lab/HallusionBench)
- [图片镜像与SHA256](https://huggingface.co/datasets/lmms-lab-encoder/HallusionBench/blob/main/data/image-00000-of-00001.parquet)
- [AISBench OCRBench V2](https://github.com/AISBench/benchmark/blob/master/ais_bench/benchmark/configs/datasets/ocrbench_v2/README.md)
- [DeepSeek API](https://api-docs.deepseek.com/)；[错误码](https://api-docs.deepseek.com/quick_start/error_codes/)
- [火山方舟鉴权与Base URL](https://console.volcengine.com/ark/region%3Acn-beijing/docs/base-url-and-authentication)；[深度思考与模型调用](https://docs.volcengine.com/docs/ark/deep-thinking?lang=zh)
- [vLLM HY4推理解析器](https://github.com/vllm-project/vllm/blob/main/vllm/reasoning/hy_v4_reasoning_parser.py)
- [vLLM采样参数](https://docs.vllm.ai/en/latest/api/vllm/sampling_params/)；[服务参数](https://docs.vllm.ai/en/latest/configuration/engine_args/)
