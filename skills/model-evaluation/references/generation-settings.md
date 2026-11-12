# 输出预算、采样与并发口径

## 输出预算、温度、并发与性能

- 从API usage统计均值、P50/P95/P99、最大值、超预算候选数量和finish_reason；不能按平均值直接设max_out_len。推理内容也消耗输出预算。固定参考均值不是目标长度。
- 增大预算不强迫所有回答变长；实际长尾会增加耗时/KV压力，未证明一定提高精度。旧回答超过新预算的比例只是风险估计，不是新实验实测截断率。
- `max_model_len >= 输入tokens(含图片和模板)+输出预算`。例如147456上下文配122880输出只余24576输入；服务可能拒绝或限制超范围请求。max-num-batched-tokens是每步调度预算，不是输出上限。
- 精度复现跟随模型/数据集官方设置。公开[Hy4-preview推荐](https://huggingface.co/tencent/Hy4-preview/blob/main/README.md#quickstart)为temperature=0.9、top_p=1.0，官方generation_config另有top_k=-1。它不证明内部VL测试权重、参考分数或其他模型用了同一配置。
- 温度省略需查完整链：独立Hallusion脚本默认0.6并主动发送；AISBench不传温度时可继承服务generation_config；vLLM的auto默认读模型配置，`--generation-config vllm`才跳过它。客户端显式值优先；不能笼统说不配就是0/1。
- 无官方规范时，temperature=0可作为部署/量化前后贪心对照，不保证最高精度或跨硬件位级一致。固定长度性能可选0+ignore_eos=True并验证实际输出长度；真实业务性能跟随真实采样，MTP接受率也可能变化。
- batch_size通常是AISBench客户端在途并发，max-num-seqs是服务调度上限。输出长度不能单独决定安全并发，还需真实图片输入、KV容量、健康和吞吐。先验证用户指定并发，再有依据扩展，不声称某次C4通过就证明C8/C16可用。
