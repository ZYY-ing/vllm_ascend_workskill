# 定长性能数据与前缀缓存

max-model-len是容量，max_out_len是预算，两者都不能证明实际输入16K、输出1K。字符数也不等于token数。以服务实际tokenizer、chat template和请求参数精确生成，最终再以服务usage/性能逐条详情验收。

## 生成并保存

将本技能scripts复制到项目tools目录。make_chat_data.py需要与服务匹配的transformers/tokenizers及目标tokenizer依赖；在AISBench隔离环境安装，不更改服务依赖，也不盲装任意latest版本。它只生成文本，没有API请求，不会预先生成答案。示例在容器内执行：

```bash
python "$WORK/tools/make_chat_data.py" \
  --model /mnt/models/model --count 32 \
  --input-tokens 16384 --output-tokens 1024 \
  --seed 42 --out-dir "$WORK/data/16k_1k_32"
```

128K输入、90%公共前缀：

```bash
python "$WORK/tools/make_chat_data.py" \
  --model /mnt/models/model --count 32 \
  --input-tokens 131072 --output-tokens 1024 \
  --prefix-ratio 0.9 --seed 43 \
  --out-dir "$WORK/data/128k_1k_p90_32"
```

生成器拒绝覆盖现有目录。随机词组成独立尾部，完整user聊天模板计入长度；通过实际token IDs调整公共前缀和尾部，再重新读取保存的JSONL验证条数、唯一性、长度、sha和最长公共前缀。manifest.json记录tokenizer模板hash、参数和校验结果。

默认不设模型特有的思考选项。目标模型确需模板kwargs时，例如某些模型的enable_thinking=False，可传--chat-template-kwargs '{"enable_thinking":false}'；必须先确认该模型支持，同时让AISBench generation_kwargs中的chat_template_kwargs完全一致。不把示例选项泛化。需要可信自定义tokenizer时显式--trust-remote-code。模型无chat template或无法精确拟合时生成器会报错，不能报告已满足目标；按模型采用适配模板或completion数据路线并重新校验。

生成器自动验证只覆盖客户端分词；服务若添加system消息、不同思考前缀、多模态token或模板版本，实际usage仍可能不同。此工具仅面向文本chat性能，不能直接证明视觉/音频请求长度。

## 创建AISBench数据配置

在WORK/benchmark：

```bash
vim ais_bench/benchmark/configs/datasets/custom/data_16k.py
```

```python
from ais_bench.benchmark.datasets import CustomDataset
from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import AccEvaluator

custom_datasets = [dict(
    abbr='exact-16k', type=CustomDataset,
    path='/srv/ascend-work/data/16k_1k_32/data.jsonl',
    reader_cfg=dict(input_columns=['question', 'max_out_len'], output_column='answer'),
    infer_cfg=dict(
        prompt_template=dict(type=PromptTemplate, template='{question}'),
        retriever=dict(type=ZeroRetriever), inferencer=dict(type=GenInferencer)),
    eval_cfg=dict(evaluator=dict(type=AccEvaluator)),
)]
```

替换为真实项目绝对路径。data_128k.py复制此结构改abbr与128K路径；warmup_128k.py改为同目录warmup.jsonl。AccEvaluator是该配置结构的占位，合成文本没有正确答案，正式使用--mode perf，不报告合成文本精度。不同AISBench版本的loader/reader导入以当前源码为准，可用mmengine Config.fromfile预检；不要将不确定的--dry-run当无负载验证。

性能模型配置max_out_len1024、ignore_eosTrue、streamTrue、C4。数据集字段max_out_len正式1024，预热1，注意当前版本优先级。正式命令见[AISBench](aisbench.md)，32条用--num-prompts 32；传8就只测8条。

## 90%公共前缀与独立预热

131072×0.9向下取整为117964个公共token，剩余尾部不同；这约等于90%共享输入，不等于90%实际缓存命中。块对齐、KV分组、缓存逐出和路由均影响真实命中。

指定prefix-ratio时另生成8条warmup.jsonl，共享相同前缀、与正式数据不同尾部，每条输出1token；不计入32条正式测量。先预热后测量，整个流程可写一个短脚本顺序执行，但不要把退出码0作为唯一成功门槛：

```bash
ais_bench --models model_perf --datasets warmup_128k \
  --mode perf --summarizer default_perf --num-warmups 0 \
  --batch-size 4 --num-prompts 8 --debug --work-dir "$WORK/experiments/warmup_本轮唯一标识"
```

核对8条均成功，并确认每个参与DP实例均收到预热；8条增加路由覆盖机会，不保证一定均匀。确认后执行正式32条，--datasets data_128k并使用新的正式结果目录，仍--num-warmups 0。一般在一台客户端运行即可，“两机都预热”指各DP缓存均建立，并非必须两台都运行AISBench。

默认内置预热可能只有1条且取正式样本，不能保证所有DP rank都暖，还可能让某正式样本整条命中。不预热则冷启动请求拉低平均命中；反复测同一正式数据可能接近全prompt命中。复测90%条件需生成新seed、新前缀再预热；不擅自清其他服务缓存或重启。

## 缓存与token验收

只在正式测试前后采集服务/metrics，保证无其他请求混跑：

```bash
curl --noproxy '*' --fail-with-body "$API/metrics" > "$RUN/metrics.before"
# 执行正式测试
curl --noproxy '*' --fail-with-body "$API/metrics" > "$RUN/metrics.after"
python "$WORK/tools/cache_delta.py" "$RUN/metrics.before" "$RUN/metrics.after" "$RUN/cache.json" --model model
```

先确认本版本prefix_cache_hits_total/queries_total为token计数，并按engine标签可分DP。工具对匹配的vllm:指标计算差值比率，拒绝缺指标、engine变化及明显计数重置；不同名称/语义要适配，不能返回假90%。无标签时不能据总体推断每个DP均预热；未被检测的重启或并发流量也会使差值不可归属。

最终32条全部成功、实际输入每条16384或131072、输出每条1024。报告实际命中率与公共前缀比例两项，不把前者写成后者。128K/1K要求至少132096总长度容量；即使max-num-batched-tokens较小，chunked prefill支持时仍可分块处理长prompt。
