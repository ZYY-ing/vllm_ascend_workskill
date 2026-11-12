# 思考模型的最终答案提取与评分

## HY4 思考标记与 GPQA 评分

先查**实际权重目录**，不要默认所有推理模型都是`<think>`：

```bash
grep -nE 'HYTK|think_begin_token|think_end_token' /models/model/chat_template.jinja
python - <<'PY'
import json
t=json.load(open('/models/model/tokenizer.json'))
for x in t.get('added_tokens',[]):
    if 'think' in x['content']:
        print(x['id'], x['content'], 'special=', x['special'])
PY
```

部分HY4权重的模板设`HYTK=':opensource'`，tokenizer将120029/120030定义为`<think:opensource>`和`</think:opensource>`。开始标记可能已在输入提示的末尾，因此生成文本只出现结束标记是正常的。`generation_config.json`中的temperature/eos不负责声明这对标签。

支持该权重的HY4 reasoning parser可从词表检测后缀；要在服务端分离思考时先确认本fork的注册名和`--reasoning-parser`支持，并检查返回字段。不要在比较测试中静默改变是否启用parser。

AISBench客户端若收到了完整思考文本，默认只认识`</think>`的`extract_non_reasoning_content`不会移除`</think:opensource>`之前的内容。然后对完整文本找第一个`Answer:`或候选字母，就可能误取思考里的讨论、示例或选项列表。**“用了AISBench源码”不代表模型适配配置已经正确。**

评分验收应先分出最终答案，再执行数据集侧的提取和评分。可在自己项目的工具模块中写严格适配，不修改vLLM：

```python
def hy4_final_only(text):
    marker = '</think:opensource>'
    if marker not in text:
        return ''  # 本实验确认API返回完整思考；无结束标记按未完成处理
    return text.rsplit(marker, 1)[1].strip()

# 模型配置：pred_postprocessor=dict(type=hy4_final_only)
# 数据集侧继续按该数据集的最终答案格式提取，再由GPQAEvaluator计分。
```

这个严格函数只用于已确认返回原始思考的接口；如果服务端已经分离reasoning，`content`可能只有最终答案，不能再无条件要求content中有结束标签。若提示要求末行`Answer: X`，就在分离后的最终内容中严格核对末行，不取思考里的第一个`Answer:`。

保存原始输出、references、提取选项、逐题对错、finish_reason和usage。逐题比较提取值与最终答案，尤其检查误判对、误判错和无最终答案；总分相同也可能是两种误判抵消。JSONL逐行读取使用`for line in file`，避免`str.splitlines()`把字符串内部的Unicode分隔符也拆开。
