# 本次重构的内容保留与行为边界

基线为 `1b1efd0b8fcc661c6e9a2d2940535f3db4031955` 的35个文件，逐项路径与原始文本SHA256见 [migration-map.json](migration-map.json)。该清单记录原文件如何迁移，不表示每个拆分后文件仍与原文件整体哈希相同。

## 文件与段落去向

| 原内容 | 保留方式 |
|---|---|
| 根README、技能README的能力和文件索引 | 合并到根README与各技能入口；删除重复的第二份README和重复清单 |
| 技能README中使用、分发、环境与授权说明 | docs/usage.md；参考来源与保留原则在SOURCES.md |
| 原SKILL.md的完整执行流程、脚本风格和验收正文 | docs/workflow.md，更新所有迁移链接；frontmatter和入口描述按四项能力重新划分 |
| agents/openai.yaml | 跟随Ascend技能，简介收窄至部署/设备/profiling；评测能力由model-evaluation承接 |
| environment.example.md | Ascend技能的assets/；字段内容保留 |
| .gitignore | 提升到仓库根，忽略规则保留，覆盖新增技能目录 |
| 权重下载文档及3个下载/网络脚本 | weight-download技能，原文和原运行行为保留 |
| Ascend编译、连接、服务、硬件及两份profiling文档 | Ascend技能references/，详细内容保留 |
| 原排障表 | 服务/设备条目在Ascend；纯评测条目与多模态judge段落在评测技能的troubleshooting.md |
| H200学习文档 | CUDA技能；第13节思考标记/GPQA提取内容移入评测answer-extraction.md，其余内容保留 |
| AISBench和定长数据文档 | 评测技能，原文与例子保留 |
| 原multimodal.md | 服务检查→multimodal.md；Hallusion主体→hallusionbench.md；OCR→ocrbench-v2.md；预算和采样→generation-settings.md；来源→SOURCES.md |
| 原Hallusion并发和API文档 | 评测技能中保留，扩充完整入口、鉴权、四阶段与产物说明 |
| 所有原运行脚本 | 归入所属技能scripts/，不改变请求、采样、答案提取、调度和评分公式 |
| 两个verify脚本 | 移入评测tests/，调整导入/工具定位；推理验证报告改为可选输出路径，默认只打印，不在安装目录写产物 |

## Hallusion新增部分

- `run_full.sh`复用现有预检、推理和完整性校验器；显式指定项目/API/模型/Python，CLI覆盖环境变量；默认保留原客户端并发1、预算4096和温度0.6。参考案例的C4、102400、0.8在文档中显式传入。
- `check_judge_auth.py`是可选真实API小请求工具；URL和模型来自用户配置，不固定厂商，不输出Key或响应body，不覆写采样和思考参数。
- 保留通用`run_judge_api.sh`及其完成标记身份核对能力，不用上游串行run_judge.sh替换，不重复引入一套豆包专用调度代码。
- `verify_entrypoints.py`使用本地模拟HTTP/SDK验证入口行为，不代表已实际运行全量HallusionBench或裁判。

没有复制官方图片、题目数据集、模型、依赖目录、真实服务器配置或实验成绩；没有改动服务器服务。技能选择验收清单是供后续真实会话验证的用例，不能把静态检查当已完成路由测试。
