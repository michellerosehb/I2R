import json
from pathlib import Path

p = Path('notebooks/updated_notebooks/updated_line_generator.ipynb')
nb = json.loads(p.read_text(encoding='utf-8'))

for cell in nb['cells']:
    src = ''.join(cell.get('source', []))
    if 'Respond in this exact format:' in src:
        src = src.replace('Respond in this exact format:\n"\n            "TITLE: <title here>\\n"\n', 'Respond in this exact format:\\n"\n            "TITLE: <title here>\\\\n"\n')
        src = src.replace('Respond in this exact format:\n"\n            "TITLE: <title here>\\n"\n', 'Respond in this exact format:\\n"\n            "TITLE: <title here>\\\\n"\n')
        cell['source'] = src.splitlines(keepends=True)

p.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding='utf-8')
print('Fixed', p)
