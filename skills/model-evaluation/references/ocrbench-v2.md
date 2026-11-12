# OCRBench V2

## OCRBench V2：AISBench

先读当前[AISBench数据集说明](https://github.com/AISBench/benchmark/blob/master/ais_bench/benchmark/configs/datasets/ocrbench_v2/README.md)。本次核实版本的TSV为10000条、10000唯一index，每条image和question非空，即10000图片题、0纯文字题；图片文件数不是内容去重数。字段包括index、image、question、answer、category、eval、bbox、content。其他版本重新核对。

- 图片可嵌入TSV Base64，也可能由loader缓存到磁盘；以实际loader和模板生成的请求为准。核对TSV真实位置，不因复制图片目录就认为TSV也存在。
- 用户明确要求复制图片目录时按源/目标校验文件数及相对路径；不默认迁移或替换共享数据。
- 数据配置`ocrbench_v2_gen_0_shot_chat_share.py`通常包含OCRBenchV2Dataset、MMPromptTemplate、GenInferencer和OCRBenchV2Evaluator；模型配置使用VLLMCustomAPIChat。前者负责数据、提示词和评分，后者负责API与采样。
- 先vim对应数据path和模型配置，再执行。模型API示例见[文本配置](aisbench.md)，使用正确模型/processor和服务名；多模态后处理须识别真实思考结束标记。

```bash
cd "$WORK/benchmark"
set -o pipefail
ais_bench --models model_mm_accuracy \
  --datasets ocrbench_v2_gen_0_shot_chat_share \
  --mode all --dump-eval-details --debug \
  2>&1 | tee "$WORK/logs/ocrbench-v2-$(date +%Y%m%d_%H%M%S).log"
```

创建logs目录，模型名替换为实际配置。完整测试不传num-prompts，smoke按用户范围加8。OCR本地Evaluator与Hallusion外部judge不同，不给OCR无故配置DeepSeek Key。最终验证10000唯一ID、success/failed及results/summary中的实际评分分母。失败不能默认为错误回答或静默排除。

AISBench强制停止前可能只有`predictions/<abbr>/tmp/tmp_*.jsonl`，没有合并的最终jsonl；可统计已成功请求的output_tokens，但要标明部分样本、顺序偏差和未完成状态，不能报告全量分数。不要改名冒充完整结果。
