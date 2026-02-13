import re
ln=7929
with open('DBrun.py','r',encoding='utf-8') as f:
    lines=f.readlines()
for offset in range(-6,6):
    i=ln+offset-1
    if 0<=i<len(lines):
        l=lines[i]
        m=re.match(r'^(\s*)',l)
        print(f"{i+1:5} lead={len(m.group(1))} |{lines[i].rstrip()}|")
