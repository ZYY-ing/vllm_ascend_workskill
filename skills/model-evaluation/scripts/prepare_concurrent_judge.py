"""Reuse official prompt/label ASTs, replacing only scheduling and cache writes."""
import ast
from prepare_evaluation import adapt_utils


def adapt_concurrent_utils(source):
    tree = ast.parse(adapt_utils(source))
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name == 'evaluate_by_chatgpt':
            loop = next(n for n in node.body if isinstance(n, ast.For))
            end = next(i for i, n in enumerate(loop.body)
                       if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                       and ast.unparse(n.value.func) == 'output.append')
            worker = ast.unparse(ast.Module(body=loop.body[:end], type_ignores=[]))
            prefix = ''
            field = 'correctness_entry'
            entry = 'correctness_entry'
        elif node.name == 'check_same_by_chatgpt':
            loops = [n for n in node.body if isinstance(n, ast.For)]
            inner = loops[-1].body[0]
            assert isinstance(inner, ast.If)
            assert isinstance(inner.body[-1], ast.With)
            worker = ast.unparse(ast.Module(body=inner.body[:-1], type_ignores=[]))
            prefix = ast.unparse(ast.Module(body=node.body[:node.body.index(loops[-1])], type_ignores=[]))
            field = "'same'"
            entry = "'gpt4v_output_gpt_check'"
        else:
            continue
        text = prefix + '\nfrom judge_concurrency import run_stage\n'
        text += 'def worker(sample):\n'
        text += '\n'.join('    ' + line for line in worker.splitlines())
        text += '\n    return sample\n'
        text += f'return run_stage(data, worker, {field}, save_json_path, load_json, {entry})\n'
        node.body = ast.parse(text).body
    return ast.unparse(ast.fix_missing_locations(tree)) + '\n'


def adapt_evaluation(source):
    tree = ast.parse(source)
    # Remove the official broad VS retry: bounded SDK retries already apply.
    class NoWholeStageRetry(ast.NodeTransformer):
        def visit_Try(self, node):
            if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id == 'evaluate_by_chatgpt' for n in ast.walk(node)):
                return node.body
            return self.generic_visit(node)
    return ast.unparse(ast.fix_missing_locations(NoWholeStageRetry().visit(tree))) + '\n'
