import re
with open("frontend/index.html", "r", encoding="utf-8") as f:
    html = f.read()

def repl(m):
    id_val = m.group(1)
    if id_val in ["clean_pm_tanques_Sáb", "clean_am_tanques_Dom", "clean_pm_tanques_Dom"]:
        return m.group(0) # don't add checked
    if " checked" in m.group(0):
        return m.group(0) # already checked
    return f'<input type="checkbox" id="{id_val}" class="toggle-checkbox" checked onchange="updateConfig()">'

new_html = re.sub(r'<input type="checkbox" id="(clean_[^"]+)" class="toggle-checkbox" onchange="updateConfig\(\)">', repl, html)

with open("frontend/index.html", "w", encoding="utf-8") as f:
    f.write(new_html)
print("patched")
