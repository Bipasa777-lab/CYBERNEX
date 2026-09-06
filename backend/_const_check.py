import io

with open(".venv/Lib/site-packages/paddleocr/_constants.py", "r", encoding="utf-8", errors="ignore") as f:
    content = f.read()

out = io.StringIO()
for name in ("DEFAULT_CPU_THREADS", "DEFAULT_MKLDNN_CACHE_CAPACITY", "DEFAULT_ENABLE_MKLDNN", "DEFAULT_DEVICE"):
    for line in content.splitlines():
        if line.strip().startswith(name):
            out.write(line.strip() + "\n")
with open("_constants_out.txt", "w", encoding="utf-8") as f:
    f.write(out.getvalue())
print("done")