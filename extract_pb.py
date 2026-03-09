import re, sys, os

filenames = [
    'cf59b0d8-e4e8-4451-bffe-17d4e32de8ed.pb', 
    '481b9497-caf1-4a32-aa00-7c385bd4c34e.pb', 
    '9baff5ff-6805-4a4d-81ea-fd8189064288.pb'
]

output_dir = 'C:/Users/kenda/OneDrive/Escritorio/filtros/planillas/recovered'
os.makedirs(output_dir, exist_ok=True)

for fname in filenames:
    path = f'c:/Users/kenda/.gemini/antigravity/conversations/{fname}'
    try:
        with open(path, 'rb') as f:
            data = f.read().decode('utf-8', errors='ignore')
            
            # Find all chunks that look like Python code starting with standard imports for planillas
            # It usually imports os, sqlite3, openpyxl, datetime
            matches = re.finditer(r'(import openpyxl.*?(?:def \w+\(|class \w+:).*?)(?=\\n",|"CodeContent"|`{3})', data, re.DOTALL)
            
            count = 0
            for m in matches:
                snippet = m.group(1)
                # Unescape standard JSON string escapes if it was in JSON
                snippet = snippet.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
                if len(snippet) > 2000:
                    outpath = os.path.join(output_dir, f'recovered_{fname.split("-")[0]}_{count}.py')
                    with open(outpath, 'w', encoding='utf-8') as out:
                        out.write(snippet)
                    print(f'Saved {len(snippet)} bytes to {outpath}')
                    count += 1
                    
            # Also search for app.py UI code (tkinter or flet or similar)
            matches_app = re.finditer(r'(import tkinter|import CTk|import flet).*?(?=\\n",|"CodeContent"|`{3})', data, re.DOTALL)
            for m in matches_app:
                snippet = m.group(0)
                snippet = snippet.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
                if len(snippet) > 1000:
                    outpath = os.path.join(output_dir, f'recovered_app_{fname.split("-")[0]}_{count}.py')
                    with open(outpath, 'w', encoding='utf-8') as out:
                        out.write(snippet)
                    print(f'Saved app.py candidate ({len(snippet)} bytes) to {outpath}')
                    count += 1
                    
    except Exception as e:
        print(f'Error reading {fname}: {e}')
