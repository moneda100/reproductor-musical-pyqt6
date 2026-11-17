path = r".kilo/plans/1792616945290-ux-and-device-sync-roadmap.md"
with open(path, encoding="utf-8") as f:
    content = f.read()
lines = content.splitlines()
for i,l in enumerate(lines,1):
    if "- [ ]" in l:
        print(f"{i}: {l}")
