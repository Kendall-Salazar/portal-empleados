import glob
for pb in glob.glob('c:/Users/kenda/.gemini/antigravity/conversations/*.pb'):
    with open(pb, 'rb') as f:
        data = f.read().decode('utf-8', errors='ignore')
    
    # Try finding Python script block for run_app.py
    import re
    blocks = re.findall(r'```python\n(.*?)\n```', data, re.DOTALL)
    for block in blocks:
        if 'webview' in block and 'Api' in block:
            print(f"FOUND API IN {pb}")
            print(block[:200])
        if 'def crear_hoja_semanal' in block and 'run_app' in block:
            print(f"FOUND PLANILLA IN {pb}")
            print(block[:200])
