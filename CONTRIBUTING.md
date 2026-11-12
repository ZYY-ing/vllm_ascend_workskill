# 新增技能与维护规则

## 能力放在哪里

独立任务有明确输入、过程和结果时，新增 `skills/<name>/SKILL.md`；现有任务的参数、模型案例或故障说明放在所属技能的 `references/`。可重复的数据处理才增加脚本，不为每个参考文档创建一个技能，不创建没有用途的空目录。

技能目录使用小写字母、数字和连字符。frontmatter 的 `name` 与目录一致；`description` 说明何时使用，与已有技能的边界明确。技能内部使用相对引用，运行工具和依赖说明随技能分发；不要依赖另一个技能里的 Python 模块或用户全局安装目录。需要组合任务时声明可选的其他技能名称，不让单个技能必须先读全部全局规则。

## 文档职责与去重

- 根 README：仓库用途、技能索引和简短使用方法。
- SKILL.md：适用范围、输入、步骤导航、关键约束和验收。
- references：命令、版本前提、参数、故障与指标解释。
- scripts：执行工具；tests：离线验证；assets：输出模板。
- docs/workflow.md：综合任务的阶段衔接；SOURCES.md：内容归属和来源。

同一专题只维护一个主要实现和详细说明，其他地方链接引用。只有独立的人类教程或分发需求才新增技能级README。拆分现有文件时逐段记录去向；不以“去重”为由丢失命令选项、异常处理、指标定义或授权边界。

移动脚本必须检查同目录导入、`__file__`、Shell路径、文档示例和离线测试。重构保留业务行为；新增参数和默认值变化明确说明。脚本和文档都以运行目录为输出位置，不往已安装技能目录写入数据或凭据。

## 本地检查

```bash
python tools/check_repository.py
python -B skills/model-evaluation/tests/verify_concurrency.py
python -B skills/model-evaluation/tests/verify_judge_concurrency.py /path/to/official/HallusionBench
python -B skills/model-evaluation/tests/verify_entrypoints.py
```

第一项检查结构、链接、迁移目的文件、AST和敏感信息模式；有Bash时检查Shell和文档内Bash语法。第二项是本地模拟HTTP的乱序、失败与样本范围验证；第三项从用户已有的官方utils.py/evaluation.py读取提示词，以模拟裁判验证串并行一致、缓存恢复及错误处理；第四项验证推理执行入口与模拟SDK鉴权检查。都不请求真实模型或付费裁判。

需要 PyYAML 时可另运行 skill-creator 提供的 quick_validate.py 检查各技能；仓库基础检查仅依赖标准库。静态检查不能证明模型支持，也不能代替真实任务的[技能选择验收](docs/routing-acceptance.md)。新增技能或改description后复核相邻技能边界，记录实际结果，不把静态关键词匹配称为已完成agent路由测试。

## 信息安全与发布

不提交密码、Token、私钥、认证URL、代理凭据、实际服务器/个人路径、原始实验结果、数据集、模型或依赖目录。环境模板使用示例地址，Key隐藏输入或私有环境传递；检查报错只打印路径和问题种类，不回显命中的凭据。`.gitignore`不会过滤已经追踪或网页手选上传的文件，提交前仍需检查diff。

镜像/工具/模型版本是案例或执行时核对结果，不写永久“最新”。升级兼容性和修复记录具体前提；公共参考来自官方资料或已注明的项目。引用第三方代码时保留其许可和来源；本仓库未擅自给原有代码变更许可。

发布使用 GitHub noreply 邮箱，检查暂存文件白名单，正常追加提交，不为结构重构重写历史或强推。不要将其他本地工作副本、私有资料、真实日志和运行中的环境一起提交。
