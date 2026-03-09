import glob, re, os

for pb in glob.glob('c:/Users/kenda/.gemini/antigravity/conversations/*.pb'):
    with open(pb, 'rb') as f:
        data = f.read()
    
    # search for run_app.py
    if b'run_app.py' in data:
        print(f"File: {os.path.basename(pb)}")
        idx = data.find(b'def run_server')
        if idx != -1:
            print(data[idx:idx+500].decode('utf-8', errors='ignore'))
        
        idx2 = data.find(b'webview.create_window')
        if idx2 != -1:
            start = max(0, idx2 - 500)
            print("webview api context:")
            print(data[start:idx2+500].decode('utf-8', errors='ignore'))
