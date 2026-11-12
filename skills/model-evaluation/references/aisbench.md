# AISBench：安装、先vim再执行

AISBench客户端只需在能访问服务API的一台机器运行；不要求服务双机都装。以下用于OpenAI兼容文本生成API，其他任务选择对应AISBench adapter与数据集。

HallusionBench、OCRBench V2及视觉权重/图片路径问题先读[多模态测试](multimodal.md)。独立Hallusion客户端不是AISBench数据集配置，不能通过给它增加batch_size自动获得并发。

## 安装一次，复用环境

容器内或独立客户端设置WORK/PYTHON为实际项目和解释器。已有源码/venv先检查，不覆盖：

```bash
cd "$WORK"
git clone https://github.com/AISBench/benchmark.git
"$PYTHON" -m venv "$WORK/aisbench-venv"
source "$WORK/aisbench-venv/bin/activate"
cd "$WORK/benchmark"
python -m pip install -e . -r requirements/api.txt
ais_bench -h
```

按本版本和所用数据集补requirements/extra.txt或确实缺少的依赖；[官方安装入口](https://docs.vllm.ai/projects/ascend/zh-cn/latest/developer_guide/evaluation/using_ais_bench.html)可核对当前命令。AISBench使用独立环境，不升级服务的torch/Transformers。API测试如需torch，使用符合其依赖约束的CPU版本，避免误装CUDA大包。记录AISBench完整commit，新增配置放独立文件，避免覆盖默认配置后难追溯。

```bash
export NO_PROXY=127.0.0.1,localhost,192.0.2.10,192.0.2.11
export no_proxy=$NO_PROXY
export TORCH_DEVICE_BACKEND_AUTOLOAD=0
```

IP替换为真实服务地址；该变量用于避免装有torch_npu的测试环境自动加载设备后端。若bare ais_bench被alias/function拦截，使用$WORK/aisbench-venv/bin/ais_bench。

## 精度：先修改配置

在WORK/benchmark内：

```bash
vim ais_bench/benchmark/configs/models/vllm_api/model_accuracy.py
```

示例内容，替换模型路径、服务名、地址和输出预算。temperature0.6是示例实验设置，不是所有模型默认值；用户指定的采样/思考模式优先。

```python
from ais_bench.benchmark.models import VLLMCustomAPIChat
from ais_bench.benchmark.utils.postprocess.model_postprocessors import extract_non_reasoning_content

models = [dict(
    attr='service', type=VLLMCustomAPIChat, abbr='model-accuracy',
    path='/mnt/models/model', model='model',
    host_ip='192.0.2.10', host_port=8000,
    stream=False, request_rate=0, retry=2,
    max_out_len=4096, batch_size=4,
    generation_kwargs=dict(temperature=0.6, ignore_eos=False),
    pred_postprocessor=dict(type=extract_non_reasoning_content),
)]
```

核对当前版本后处理导入路径以及目标模型的思考标签；不支持时按模型/数据集要求调整，不偷偷改生成文本。自定义代码模型只有确有需要且来源可信时加trust_remote_code=True。模型path用于tokenizer，与服务权重保持一致；客户端model是served-model-name，两者含义不同。

## 精度：再执行

GPQA仅示范一种文本精度数据集。先按当前数据集配置及合法来源准备数据，确认文件不是HTML错误页、列名/条数正确；也可选MMLU、GSM8K或用户指定集，不固定所有模型都用GPQA。

```bash
RUN="$WORK/experiments/accuracy_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RUN"
set -o pipefail
ais_bench \
  --models model_accuracy \
  --datasets gpqa_gen_0_shot_str \
  --mode all --dump-eval-details --debug \
  --work-dir "$RUN" \
  2>&1 | tee "$RUN/console.log"
rc=${PIPESTATUS[0]}
printf '%s\n' "$rc" > "$RUN/exitcode"
```

可先按用户范围用--num-prompts 8做smoke，再跑完整；不把smoke分数当全量。若封装set -e脚本，要显式处理失败管道后保存退出码，防止提前退出漏记录。

## 性能：独立配置

复制精度配置为model_perf.py，编辑：abbr='model-perf'，stream=True，max_out_len=1024，batch_size=4，generation_kwargs=dict(temperature=0,ignore_eos=True)，去掉精度后处理。正式性能的思考模板选项须与数据生成一致；不把HY4的no_think选项套给其他模型。数据配置见[定长数据](datasets.md)。

```bash
RUN="$WORK/experiments/perf_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RUN"
set -o pipefail
ais_bench \
  --models model_perf --datasets data_16k \
  --mode perf --summarizer default_perf \
  --num-warmups 0 --batch-size 4 --num-prompts 32 \
  --debug --work-dir "$RUN" \
  2>&1 | tee "$RUN/console.log"
rc=${PIPESTATUS[0]}
printf '%s\n' "$rc" > "$RUN/exitcode"
```

request_rate=0代表不限发送速率，C4限制在途请求数。stream=True用于分析TTFT/TPOT；ignore_eos=True用于固定输出性能，必须确认本adapter传递且服务接受，最终看实际usage。精度通常ignore_eos=False。数据集指定max_out_len在部分版本优先于模型设置，改预算时两者核对。

## 默认值、回显和结果

CLI默认值以当前ais_bench -h及源码为准：历史版本num-prompts=None用全量、batch-size=None用模型配置、num-warmups=1。generation_kwargs至少保留{}，部分版本任务直接索引该键；省略采样项还受模型generation_config及服务端配置影响，不宣称统一默认温度。

官方成绩复现优先使用模型/benchmark指定采样。缺少规范时，temperature=0可作工程贪心对照，不能称作所有模型的最优精度配置。固定长度性能与实际业务性能分开测；MTP接受率也可能随采样变化。公开Hy4-preview推荐temperature=0.9、top_p=1.0，但不能直接据此断言某份内部多模态权重或某项参考分数的评测设置。

每个续行反斜杠后不能有空格或注释，--datasets后漏反斜杠会使--mode成为另一条命令。tee路径不在开头多写$，目录先建。--work-dir省略仍有默认输出，但不能自动保存所有终端回显；WORK未赋值可能意外写/experiments。以日志Current exp folder为真实结果根，可能在RUN下再有时间戳。

精度与性能串行执行，profiler另轮记录，不混负载。交付run.sh、实际配置及原件备份/diff、console.log、退出码、完整结果目录、代码/模型/参数信息。exitcode0或进度100%不能单独证明成功。

## 精度答案与“未回答完”

| 文件（以本轮实际结构为准） | 关注内容 |
|---|---|
| predictions/模型abbr/数据集.jsonl | 逐条生成结果、题ID、原始prediction、成功状态、输入输出token数 |
| results/模型abbr/数据集.json | 评分汇总及details，可能含origin_prediction、提取答案、参考答案和correct |
| summary、performances及failed文件 | 分数/性能汇总、逐条详情和失败原因 |

JSONL通常每行一个请求；JSON通常整体评分对象，两者都可能含完整回答。按题ID关联，不假定行序相同。success=True不是correct=True。

完整性优先看原始finish_reason=length（若保存），再结合实际output_tokens是否触顶、文本结尾和是否给最终答案；触顶是线索，不独立证明未完成。已回答完但correct=False属于答错；截断文本也可能被评分器碰巧提取到正确选项，需单独标注。模型思考结束标签不同，先验证后处理。乱码、控制字符、异常重复、语义错误与长度截断分别统计，不凭长回答就归因为长序列算子bug。

## 性能验收

报告成功/失败与唯一请求数、实际输入/输出tokens范围、并发、条数、预热和缓存条件、输出吞吐、TTFT/TPOT分位数。GPQA输入自然变化，用GPQA跑perf不能称16K/1K。进度条s/case、单请求token/s与服务聚合吞吐不能直接比较。

慢请求先查服务health、token计数是否推进、running/waiting与worker日志；POST4/RECV0可能4个请求仍在prefill，尾部几题可能长推理。不因静默重复启动同一测试。监控后串行测试应保存status/PID，恢复前确认未执行第二遍；用户取消监控就停止后续自动测试。
