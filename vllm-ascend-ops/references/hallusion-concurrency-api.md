# HallusionBench：并发推理与通用API评分

适用于用户要求提高测试速度、限制题数、使用外部API裁判或恢复中断评分。沿用[多模态测试](multimodal.md)的数据/图片准备和官方计分规则；不绑定机器、容器、厂商或某次成绩。

## 先识别实际代码版本

- 技能`../scripts/run_hallusionbench_hy4.py`支持`--concurrency`，默认1；部分项目的`run_full.sh`可能默认4。现场读取`--help`和config.json，不混用不同副本的默认。
- 本技能图片恢复入口是`download_hallusion_images.sh`（内嵌Python），不是已移除的独立下载py。选择实际存在的Python，确认pyarrow/Pillow，传官方仓库目录；已有完整图片则复用。
- 用户要求复用镜像、原脚本或不更新代码时，只读检查实际导入路径即可；挂载目录和PYTHONPATH可能覆盖镜像内同名源码。不要借检查升级、同步源码。

## 并发推理的边界

1. `--limit 0`全量，正数取官方前N题。预检/完整性校验都应读取同一limit，报告full或first_n_subset；小样本不能宣称全量精度。
2. `--concurrency N`限制在途请求。使用有界线程池，完成后补位；请求体、采样、图片编码和答案提取规则不因并发改变。默认保守，按用户目标和服务容量选择；并发不保证答案逐字一致，也不保证线性提速。
3. 工作线程只请求，主线程独占写入。responses.jsonl按完成顺序写、含原始index；partial/final按原题序写。原子替换JSON避免读到半写文件，按category/subcategory/set_id/figure_id/question_id验证唯一ID和映射，不能按返回先后拼错题。
4. 失败停止补位、处理已在途请求、保留原始成功响应和failure.json、非零退出，不发布缺题final，不自动重跑可能已执行的请求。推理恢复与评分恢复是不同能力。
5. 整数输出预算直接写102400或Shell算式求值；请求超时是socket操作超时，不是总耗时上限。标准答案不得发送给待测模型。

可选预检和完成校验（SKILL、PYTHON、DATA、ROOT、API、MODEL、RUN按现场设置）：

```bash
"$PYTHON" "$SKILL/scripts/preflight.py" \
  --data "$DATA" --root "$ROOT" --api "$API" --model "$MODEL" --limit 0
"$PYTHON" "$SKILL/scripts/check_results.py" --data "$DATA" --run "$RUN"
```

校验器核对完整题数/唯一ID/原题内容/原始响应与最终答案，并生成integrity_report.json。发布最终精度前额外检查空答案、finish_reason、思考标记和异常字符。中外文OCR引用、数学符号、中文专名不是乱码；乱码候选需给JSON index和题组ID。length单列，不等于乱码或答错。模型先验覆盖改图、数值推理失误、参考答案与问题不一致也应分开分析，不自动改标签或归因于并发/MTP/量化。

## 通用API裁判：配置而非固定厂商

使用`../scripts/run_judge_api.sh`，兼容OpenAI Chat Completions协议；原生Responses、Anthropic等其他协议需单独适配，不能只改URL就宣称兼容。

先确认：服务的Base URL（是否含/v1或/api/v3）、准确模型名/endpoint ID、Key作用域、模型权限、余额、RPM/TPM及是否能返回非空message.content。示例模型仅用于说明；执行时核对服务官方文档和用户控制台，不自动换成其他型号。

| 服务 | Base URL示例 | 模型配置 |
|---|---|---|
| OpenAI兼容自建／网关 | 用户指定的完整API前缀 | 网关实际暴露的ID |
| OpenAI | https://api.openai.com/v1 | 用户指定且已开通的模型 |
| DeepSeek | https://api.deepseek.com | 用户指定且当前可用的型号 |
| 火山方舟 | https://ark.cn-beijing.volces.com/api/v3 | 用户指定型号或endpoint ID |

在能访问结果、官方脚本和依赖的同一Python环境执行，容器场景先进入容器：

```bash
export HALLUSION_HOME=/path/to/Hallusionbench_test
export HALLUSION_JUDGE_BASE_URL=https://api.example.com/v1
export HALLUSION_JUDGE_MODEL=your-enabled-judge-model
export HALLUSION_JUDGE_CONCURRENCY=4
export PYTHON=/path/to/python
RUN="$HALLUSION_HOME/outputs/your-completed-run"

# 第一次默认RUN/evaluation；切换裁判时明确指定新的独立目录。
export HALLUSION_EVAL_DIR="$RUN/evaluation-your-judge"
bash "$SKILL/scripts/run_judge_api.sh" "$RUN"
```

脚本隐藏读取Key，不要求用户手动复制官方文件、执行unset或保存退出码。若事先在父终端export过Key，子脚本无法清除父终端变量，仍需父终端unset。确认实际Python可导入openai（现代OpenAI类）、numpy、prettytable、tqdm；不要为评分升级推理栈，缺少依赖时用用户选定的独立环境/目录。

## 评分入口实际做什么

```text
run_judge_api.sh
  → check_results.py + 依赖检查
  → 锁与已有完成状态检查、隐藏读取Key
  → 复制官方evaluation.py/utils.py和本轮HallusionBench_result.json
  → prepare_concurrent_judge.py
       → prepare_evaluation.adapt_utils：现代SDK、环境变量、timeout=60/max_retries=2
  → 适配后的evaluation.py/utils.py
       → judge_concurrency.run_stage：有界并发、按ID缓存恢复、原子写入
  → summarize_hallusion_scores.py（离线分类汇总）
  → .judge_completed + 打印真实退出码 + 清理脚本内Key
```

四阶段VD正确性→VD一致性→VS正确性→VS一致性保持顺序，阶段内并发。官方prompt、correct/incorrect/unclear解析、same规则及统计公式保持；不把四个进度条当作一次100%，全量该数据版本约2258次请求。保留SDK有限重试，移除吞错无限重试与VS整阶段重试。

main线程保存所有在途成功结果；阶段失败后同目录重启只补缺失标签。输入hash、Base URL、模型、官方prompt源码hash必须相同，缓存不能混入其他题/答案/重复ID；更换裁判开新目录。已有运行锁不重复启动；完成标记须与身份校验相符。SDK超时/断网无法保证服务端未计费，不能声称绝对exactly-once；已持久化成功标签不重复请求。

离线验证使用`verify_concurrency.py`和`verify_judge_concurrency.py`：模拟乱序、失败停止补位、缓存恢复、提示词/标签与串行一致，不调用收费API，也不能代替真实API限流/吞吐验证。后者参数为含官方utils.py/evaluation.py的目录。

## 网络与异常处理

- 先无Key检查DNS/TCP/TLS/代理连通性，再在用户授权范围内最小鉴权/模型请求；正式评分已成功时，不重复测试Key。若需要本地代理经SSH转发，只开放远端loopback、保留主机指纹和TLS校验，并记录转发生命周期；不把历史代理设为永久默认。
- Key仅隐藏输入/进程环境；按变量名docker exec -e传入，不放参数、脚本、文件或日志，不读取/proc环境。后台任务记录PID、开始时间、完整日志和真实退出码，不因连接中断重复启动。
- 明确无效凭据的401与余额不足、模型权限/403、429、网络/TLS、5xx分开。只在用户授权候选范围内切换Key；余额或权限不足不能靠遍历Key/改模型掩盖。临时网络/限流有限重试，持续失败停止并报告保留缓存，不能无限整轮重启。
- 不擅自关闭思考、设置温度或替换模型以提速。若调整参数，记录并分开比较裁判口径。只停HY4不等于停外部裁判；不要停承载评分的容器。

## 完成后主要交付哪些文件

推理：HallusionBench_result.json（model_prediction）、summary.json（耗时/token/截断）、integrity_report.json（完整性）。排查原始生成时再读responses.jsonl；失败先读failure.json。

评分：scores.csv/json（分类aAcc）、evaluation-judge-api-*.log末尾Leaderboard Stats（官方aAcc/qAcc/fAcc）、hallusion_output_vd_model.json与hallusion_output_vs_model.json（逐题标签、答案及same）。scores_details.json与judge_config.json供统计/身份追溯。主脚本不默认生成official_scores.json或人工分析报告。

确认退出0、完成标记和缓存标签完整后才交付。报告真实分母、无图/有图、截断和裁判精确ID。overall定义为aAcc；不平均各类别，也不平均aAcc/qAcc/fAcc。字段名gpt4v_output_gpt_check或表格GPT Eval是官方历史文字，不代表实际裁判是GPT。
