"""Preserve server-owned referential context in the actual V18 planner seam."""
import ast
import hashlib
from pathlib import Path
from build_qa_routing_v16_candidate import replace_one

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = 'c8b2c1afebf921715d5b588540a0b727c69ce983ae0870dee2c3d5551a9711f0'


def build(text):
    text = replace_one(text,
        '"它", "该变量", "这个变量", "上述变量", "刚才的", "前面的",',
        '"它", "它们", "该变量", "这个", "那个", "这些", "上述变量", "刚才", "上面", "前面的",')
    ast.parse(text)
    return text


if __name__ == '__main__':
    source = ROOT / '.codex_runtime/qa-routing-v18/candidate/ollama_proxy_server.py'
    if hashlib.sha256(source.read_bytes()).hexdigest() != BASE_SHA:
        raise ValueError('accepted proxy baseline changed')
    output = ROOT / '.codex_runtime/qa-routing-v20/candidate'
    output.mkdir(parents=True, exist_ok=False)
    (output / 'ollama_proxy_server.py').write_text(build(source.read_text(encoding='utf-8')), encoding='utf-8', newline='\n')
    print('V20 single planner-seam candidate built')
