import re

with open("DBrun.py", "r", encoding="utf-8") as f:
    lines = f.readlines()
for i in range(7888, 8060):
    l = lines[i]
    m = re.match(r"^(\s*)", l)
    lead = len(m.group(1))
    print(f"{i + 1:5} lead={lead} [{lines[i].rstrip()}]")
