# HallusionBench 数据、推理和计分

先读[多模态服务检查](multimodal.md)。本文保留数据准备、请求字段、SDK适配原理、分类指标和日志判读；完整执行入口见[并发测试与评分](hallusion-concurrency-api.md)。

## 文件组织与授权边界

建议将Hallusion运行所需文件集中在`$HALL`，例如`$WORK/Hallusionbench_test`：

```text
Hallusionbench_test/
  run_hallusionbench_hy4.py   # 从本技能scripts复制的客户端
  HallusionBench/            # 官方仓库、HallusionBench.json、hallusion_bench图片
  outputs/<run>/             # responses、模型答案、summary；evaluation在各run内
  logs/                     # tee推理日志
```

- 原客户端已支持全量：不传`--limit`或传0用全部题目；`--limit N`取前N条。不要为全量另造串行任务、status.json/inference.log或自动监控，除非用户要求。
- 客户端只推理，不加载模型权重、不运行OCR、不运行judge。技能客户端支持`--concurrency`（默认1），不接受batch_size；推理不自动断点恢复。新测试用新输出目录。按需使用[并发与通用API评分](hallusion-concurrency-api.md)中的校验器和评分入口。
- 串行/断点恢复任务仅在授权时增加：记录PID及启动时间、配置hash、已完成唯一ID；每题持久化后才能跳过。先确认旧进程和结果，避免重新发起全量。用户取消OCR不等于取消已独立启动的judge。
- 已启动的评分目录不要移动；只停vLLM时，不停止承载评分的容器或其他Python进程。

## Hallusion数据下载

先读[官方仓库](https://github.com/tianyi-lab/HallusionBench#evaluation)。Git clone取得代码与题目，不等于已取得图片。

```bash
HALL="$WORK/Hallusionbench_test"
mkdir -p "$HALL"
cd "$HALL"
git clone https://github.com/tianyi-lab/HallusionBench.git
```

已有仓库直接复用，不再次clone覆盖。记录仓库commit与题目JSON的hash。

官方图片ZIP入口为Google Drive；当前gdown支持直接传ID，先看`python -m gdown --help`，不能无条件沿用旧版`--fuzzy`：

```bash
cd "$HALL/HallusionBench"
"$PYTHON" -m gdown '1eeO1i0G9BSZTE1yd5XeFwmrbe1hwyf_0' -O hallusion_bench.zip
"$PYTHON" -m zipfile -t hallusion_bench.zip && unzip -n hallusion_bench.zip
```

gdown仅在客户端缺少时安装；网络、公开权限或下载额度失败不代表ZIP已存在，不能跳过校验。不要复用聊天泄露的凭据或浏览器Cookie。

官方Drive不可取时，可使用[镜像图片Parquet](https://huggingface.co/datasets/lmms-lab-encoder/HallusionBench/blob/main/data/image-00000-of-00001.parquet)。该文件含图片bytes，不是ZIP；必须解码恢复图片后在服务器打包。需pyarrow和Pillow，依赖安装在客户端环境：

```bash
PYTHON="$WORK/aisbench-venv/bin/python" \
  bash /path/to/skill/scripts/download_hallusion_images.sh "$HALL/HallusionBench"
```

这是简短Shell脚本，图片提取通过内嵌Python完成，不要求用户维护独立下载Python项目。它校验固定镜像hash、官方题目与镜像记录匹配、路径和图片解码、同名内容一致、ZIP CRC；不修改官方JSON。镜像更新导致hash/记录不一致时停止并核对版本，不能删除校验后继续。

本镜像版本对应1129题：178题无图片，951题需图片（visual_input=1有447题，=2有504题），346张不同图片。镜像951条是视觉问题记录数，不是951张不同图片。其他版本按真实JSON重新统计，不把这些数量当永久约束。

## Hallusion推理

`HallusionBench.json`含question、filename、visual_input、标准答案及题组ID；标准答案只用于后续评分，不传给待测模型。纯文本题`visual_input=0`不读filename；1和2都必须发送图片。路径可能为`./VS/...`，也可能含`hallusion_bench/`前缀，以JSON与实际目录拼接检查；Hallusion和OCR的图片目录不能混用。

先将技能脚本复制到项目Hallusion目录；已有同名脚本先比较，只作必要最小修改。改完共享盘副本不代表机器原目录也更新，执行前确认实际脚本路径与hash。以下是显式配置示例，不是模型官方最优参数或内部VL成绩保证：

```bash
STAMP=$(date +%Y%m%d_%H%M%S)
RUN="$HALL/outputs/hallusionbench-$STAMP"
mkdir -p "$HALL/logs"
set -o pipefail
"$PYTHON" -u "$HALL/run_hallusionbench_hy4.py" \
  --data "$HALL/HallusionBench/HallusionBench.json" \
  --root "$HALL/HallusionBench/hallusion_bench" \
  --api http://192.0.2.10:8000/v1 --model hy4 \
  --max-tokens 102400 --temperature 0.8 \
  --top-k 15 --top-p 0.95 --repetition-penalty 1.0 \
  --no-skip-special-tokens --reasoning-effort high --output "$RUN" \
  2>&1 | tee "$HALL/logs/hallusionbench-$STAMP.log"
```

全量不传limit或用`--limit 0`，8题smoke加`--limit 8`。输出预算按下文分位数和复现目标决定。命令行整数用`122880`或`$((120*1024))`，不能传字面字符串`120*1024`。大输出时原客户端1200秒超时可能先触发，按实测时长最小修改，不未经请求重写框架。

### 请求字段与模板参数

公开客户端为兼容旧调用，保留`max_tokens=4096`、`temperature=0.6`默认值；下列新增选项未指定时不发送，让服务沿用原有默认值。现场脚本可能有不同默认，读取实际`--help`、config.json和请求构造，不混用不同副本。

| 客户端选项 | 实际JSON请求字段 | 说明 |
|---|---|---|
| `--top-k 15` | `top_k: 15` | `-1`关闭top-k筛选；对方框架的topk要映射为top_k |
| `--top-p 0.95` | `top_p: 0.95` | 对方框架的topp要映射为top_p |
| `--repetition-penalty 1.0` | `repetition_penalty: 1.0` | 1不额外施加重复惩罚 |
| `--no-skip-special-tokens` | `skip_special_tokens: false` | 保留原始特殊token；反向选项为`--skip-special-tokens` |
| `--reasoning-effort high` | `chat_template_kwargs: {"reasoning_effort":"high"}` | HY4模板参数，客户端支持high/max/no_think；其他模型先核对模板 |

`chat_template_kwargs`不是采样参数字典，vLLM将其交给模板。检查实际权重目录的chat_template.jinja或tokenizer_config.json：本次检查的HY4模板默认high，不传不等于关闭思考。其未使用`is_reasoning_end`，仅发送该变量不能声称有效，也不能将其等同于no_think。vLLM内部同名`is_reasoning_end(...)`是解析器状态判断方法，与外部模板参数不是同一接口。

`pass_parallel`、`openai_infer`不是该客户端/vLLM标准生成字段：后者已由现有OpenAI兼容HTTP接口实现；前者通常属于外部框架执行配置，须看实现，不能直接当作batch_size数值。客户端并发使用`--concurrency`，不发送成模型生成参数。并发时明确在途请求数、结果ID对应、失败策略和日志顺序；客户端并发、批大小与服务端动态batch/max-num-seqs分别记录。

`skip_special_tokens=false`影响解码后的返回文本，不会因此把API的completion_tokens变成最终答案token数。原始响应保留；评分前检查真实思考结束标记、最终答案和其他结构token，不能只靠字符串长度判断思考开关。

| 输出 | 用途 |
|---|---|
| config.json | 参数、数据/API/模型和输出目录 |
| responses.jsonl | 每题原样响应与usage、finish_reason，含推理内容；并发按完成顺序写，使用0基index对应题目；不是自动恢复机制 |
| partial_results.json | 当前累计的最终答案 |
| HallusionBench_result.json | 题目记录加model_prediction，完整推理后生成，供judge读取 |
| summary.json | 样本数、prompt/completion usage覆盖、avg_prompt_token、avg_completion_token、length截断数量 |
| failure.json | 失败索引与错误；先读HTTP body定位400等，不盲改图片根目录 |
| tee指定日志 | `N/total completion_tokens=... finish_reason=...`及异常 |

均值分别为有效usage的prompt_tokens/completion_tokens之和除以样本数；覆盖不完整时本客户端输出null，不把缺失算0。平均输入含模板与服务记录的视觉token，不能只重分词题目；平均输出包含服务计入usage的所有生成token，不能用去掉思考后的答案长度替代。`stop`不代表答对，`length`表示达到限制；不得将触顶直接称乱码。

交付时先指向少数主要文件：推理看`HallusionBench_result.json`的`model_prediction`、`summary.json`及校验器生成的`integrity_report.json`；评分看`scores.csv/json`、评分日志末尾的官方aAcc/qAcc/fAcc，错题查VD/VS逐题缓存。人工分析与另算指标文件不当作主脚本默认输出。

比较平均输出时同时报告中位数、长尾、截断数、输出上限和统计范围。少量触顶样本可能显著拉高均值；可另算非截断均值用于解释，但保留全样本统计，不能悄悄排除。参考均值不是目标输出长度，增加max_tokens不强制每题写满；不能仅凭短答案或缺少可见think标记判定关闭了思考。

## Hallusion独立评分

厂商无关的配置、并发评分、同目录缓存恢复与错误分类见[Hallusion并发和通用API评分](hallusion-concurrency-api.md)。下文保留官方适配原理与具体服务示例；不要把豆包型号、某次代理或已完成成绩作为通用默认。

用户只要求推理时不调用judge。评分需要将问题、参考答案和model_prediction发给独立文本judge API，通常不重新发图片，也不依赖HY4 vLLM。保存的回答完整时，停待测模型服务不会中断外部judge；评分进程、容器与网络仍须存活。

1. 在`$RUN/evaluation/`放官方evaluation.py、utils.py和本轮HallusionBench_result.json；不要复用8题smoke的评分缓存。备份脚本再做SDK兼容适配，不改judge提示词和计分公式。
2. 旧utils使用`openai.ChatCompletion.create`，可能与新版SDK不兼容，且`while True`吞错会造成假卡住。按已安装SDK改为`openai.OpenAI(...).chat.completions.create(...)`，设置请求超时和有限重试；401/402等明确报错，不无限重试。保留原始异常及恢复所需数据。
3. Key通过环境变量/终端隐藏输入，不写apikey.txt、不发聊天、不保存env转储。base_url、模型名、SDK版本、judge提示词hash单独记录，但不保存Key。
4. 请求配置示例：`OpenAI(api_key=os.environ['HALLUSION_JUDGE_API_KEY'], base_url=os.environ['HALLUSION_JUDGE_BASE_URL'], timeout=60, max_retries=2)`；模型来自`HALLUSION_JUDGE_MODEL`。官方OpenAI地址为`https://api.openai.com/v1`；DeepSeek为`https://api.deepseek.com`，模型名以执行时官方文档核实，不把旧别名当永久可用。
5. 在评估目录运行`"$PYTHON" -u evaluation.py 2>&1 | tee evaluation-judge-<timestamp>.log`。完整新跑顺序为VD正确性、VD一致性、VS正确性、VS一致性；该1129题版本约2258次调用，单轮100%不代表整套结束。

```bash
read -rsp 'Judge API Key: ' HALLUSION_JUDGE_API_KEY
echo
export HALLUSION_JUDGE_API_KEY
# 分别显式设置本轮HALLUSION_JUDGE_BASE_URL、HALLUSION_JUDGE_MODEL。
# 这些变量只有完成上述SDK/环境变量适配的utils才会读取。
```

断点评分只在相同结果、judge模型、提示词与计分配置下复用原VD/VS缓存；换judge时新建评估目录。正确性判断为1=correct、0=incorrect、2=unclear；VS无图基准条件的unclear按官方规则可计正确，不自行统一判错。same表示与题组基准回答有无冲突，不等于回答正确。

检查`hallusion_output_vd_model.json`、`hallusion_output_vs_model.json`的记录数、唯一题ID及正确性/same字段完整性；不是仅看进程退出或进度100%。结果表行名`GPT Eval`是原脚本固定文字，不证明实际用了GPT-4。

### 豆包裁判与独立缓存

已有完成上述环境变量/SDK适配的evaluation.py和utils.py时，可直接切换judge配置，不修改待测模型。直连火山方舟使用数据面Base URL `https://ark.cn-beijing.volces.com/api/v3`；模型示例`doubao-seed-2-0-lite-260215`或用户控制台给出的Endpoint ID，执行时核对开通状态和当前可用型号。`api_doubao_...`可能是评测框架别名，不自动原样作为官方model。若用公司网关，采用该网关的URL/Key/模型名映射；不能把官方Key配到第三方URL。

```bash
# EVAL_TEMPLATE为已适配环境变量的评分脚本目录，SKILL为本技能目录。
# RUN必须是本轮已经完成推理的目录。
EVAL="$RUN/evaluation-doubao-$(date +%Y%m%d_%H%M%S)"
mkdir "$EVAL"
cp "$EVAL_TEMPLATE/evaluation.py" "$EVAL_TEMPLATE/utils.py" "$EVAL/"
cp "$RUN/HallusionBench_result.json" "$EVAL/"
export HALLUSION_JUDGE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
export HALLUSION_JUDGE_MODEL=doubao-seed-2-0-lite-260215
read -rsp 'Judge API Key: ' HALLUSION_JUDGE_API_KEY; echo
export HALLUSION_JUDGE_API_KEY
cd "$EVAL"
set -o pipefail
"$PYTHON" -u evaluation.py 2>&1 | tee evaluation-judge-doubao.log && \
  "$PYTHON" "$SKILL/scripts/summarize_hallusion_scores.py" --evaluation-dir "$EVAL"
unset HALLUSION_JUDGE_API_KEY
```

`$PYTHON`需能导入openai、numpy、prettytable和tqdm；依赖检查与安装使用用户选定的评分环境，不假定容器或迁移后的venv可直接用。容器执行时确认EVAL在容器内可见，用`docker exec -e HALLUSION_JUDGE_API_KEY -e HALLUSION_JUDGE_BASE_URL -e HALLUSION_JUDGE_MODEL ...`按名字传入宿主已导出的变量，不把Key拼进命令文字。

此命令不复制旧judge缓存，原DeepSeek结果保留；新的豆包评分会产生实际API费用。切换裁判不会改变已有模型回答及其推理参数。若要复现别人的分数，还须对齐judge提示词、判定规则、数据范围和答案处理，不能仅换model名字就称同口径复现。

### 自动生成overall及分类分数

官方evaluation.py一般打印aAcc/qAcc/fAcc，但未必保存分类表。以上命令在评分成功后自动调用本技能的离线汇总器；现场已集成相同汇总逻辑时可复用，不重复改写评分框架。已有缓存时单独执行：

```bash
"$PYTHON" "$SKILL/scripts/summarize_hallusion_scores.py" --evaluation-dir "$EVAL"
cat "$EVAL/scores.json"
```

汇总器只依赖Python标准库，无Key、不导入API客户端、不发请求。目录中需有本轮HallusionBench_result.json及两个hallusion_output_*_model.json裁判缓存；校验唯一题ID、样本集、回答内容和0/1/2标签。缺题、重复或不同回答的旧缓存会报错，不能把未评分题默认判错/跳过；完整性相对于本轮输入，8题smoke只代表8题。

| 文件 | 内容 |
|---|---|
| scores.json | overall、VS、VD、实际出现的VS_map/VS_table/VS_ocr/VS_chart、VD_math/VD_figure/VD_video/VD_illusion/VD_ocr；百分比保留两位 |
| scores.csv | split、正确数、总题数、aAcc百分比 |
| scores_details.json | 总题数、无图题数、分类计数和更高精度分数；judge身份需由本轮配置另外记录 |

这里overall**明确定义为aAcc**：全部正确题数/全部题数×100，按题数加权，不是类别均值，也不是(aAcc+qAcc+fAcc)/3。别的排行榜可能把overall定义为三项均值，必须读公式，不能只看字段名。VS是Visual Supplement、VD是Visual Dependent；后缀表示地图/表格/文字/图表/数学/图形/视频相关/错觉等子类别。

对完整1129题版本，本工具包含178无图基准题和951图片题；只取951图片题要另标口径，不与1129分数混用。严格沿用官方assign_correctness：标签1计正确，VS的figure_id=0基准题标签2也计正确，其余2计错误。不能直接统计标签1数量代替官方aAcc。

## Hallusion指标与日志判读

评分日志末尾搜索`Question Stats`、`Figure Stats`、`Leaderboard Stats`。按实际脚本和记录计算分母，先报告aAcc/qAcc/fAcc，不把所有指标统称acc：

| 关键词 | 分母及定义 |
|---|---|
| aAcc / Acc per question | 单题正确数/题数；包含纯文本基准题，按官方assign_correctness规则 |
| qAcc / Acc per question pair | 全部答对的相关题组数/题组数；由category、subcategory、set_id、question_id分组，不一定恰好两题 |
| fAcc / Acc per figure | 同一图片全部题答对的图片数/图片数；VS无图figure_id=0排除 |
| easy aAcc / hard aAcc | 本次官方代码按Easy/Hard子集的题组全部通过率计算，名称不能当作原始单题准确率；核对版本 |
| Consistency Test correct | 图片内全部题正确，与fAcc同值 |
| Consistency Test inconsistent | 图片内部分正确、部分错误；不直接证明语言逻辑矛盾 |
| Consistency Test wrong | 图片内所有题都错；三类图片占比合计100% |
| Yes/No Bias Pct Diff | 代码根据correct和gt_answer推算的Yes比例减标准Yes比例；0.037是+3.7个百分点，不是0.037% |
| Yes/No Bias FP Ratio | 当前代码为错误题中gt_answer=No的比例，不是传统FP/(FP+TN)；不以越低越好评价 |
| LH / VI / Mixed | 根据参考正确性、视觉条件和same规则归因的语言/视觉/混合错误占比；分母为分类错误记录，属于启发式诊断，不是已证明内部根因 |

主要精度越高越好；错误构成占比必须结合总错误数，不能单独判断优劣。若另报纯图片题准确率、原图/修改图分项，注明是额外统计，与日志Easy/Hard分组指标不同。比较参考acc前先确认它是哪种指标、哪个judge、数据版本、提示词、采样和输出预算。
