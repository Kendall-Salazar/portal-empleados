import re
import os

conversations = [
    'cf59b0d8-e4e8-4451-bffe-17d4e32de8ed.pb',
    '481b9497-caf1-4a32-aa00-7c385bd4c34e.pb',
    '89d3754b-0a7d-4dc6-ac40-ac306a56bbca.pb'
]

pattern = re.compile(rb'\{"TargetFile":\s*"[^"]*planilla\.py".*?(?=\{"Target|`{3}|\n\n)', re.DOTALL)

for conv in conversations:
    path = f'c:/Users/kenda/.gemini/antigravity/conversations/{conv}'
    if not os.path.exists(path): continue
    
    with open(path, 'rb') as f:
        data = f.read()
        
    for i, match in enumerate(pattern.finditer(data)):
        m_str = match.group(0).decode('utf-8', errors='ignore')
        print(f"[{conv}] Match {i}: {len(m_str)} chars")
        out_path = f'c:/Users/kenda/OneDrive/Escritorio/filtros/planillas/pb_match_{conv.split("-")[0]}_{i}.txt'
        with open(out_path, 'w', encoding='utf-8') as out:
            out.write(m_str)

# Also let's try to extract ANY huge python blocks that might be raw code
py_pattern = re.compile(rb'import openpyxl.*?def crear_hoja_semanal.*?(?=\\n",|`{3})', re.DOTALL)
for conv in conversations:
    path = f'c:/Users/kenda/.gemini/antigravity/conversations/{conv}'
    with open(path, 'rb') as f:
        data = f.read()
    for i, match in enumerate(py_pattern.finditer(data)):
        m_str = match.group(0).decode('utf-8', errors='ignore')
        # if it's JSON encoded string, we unescape it
        m_str = m_str.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
        if len(m_str) > 1000:
            out_path = f'c:/Users/kenda/OneDrive/Escritorio/filtros/planillas/raw_{conv.split("-")[0]}_{i}.py'
            with open(out_path, 'w', encoding='utf-8') as out:
                out.write(m_str)
            print(f"Extracted raw python {len(m_str)} chars from {conv}")
