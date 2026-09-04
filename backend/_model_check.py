import io

with open(".venv/Lib/site-packages/paddlex/inference/models/text_detection/__init__.py", "r", encoding="utf-8", errors="ignore") as f:
    det = f.read()
with open(".venv/Lib/site-packages/paddlex/inference/models/text_recognition/__init__.py", "r", encoding="utf-8", errors="ignore") as f:
    rec = f.read()

out = io.StringIO()
for label, content in (("DET", det), ("REC", rec)):
    out.write(f"=== {label} ===\n")
    for line in content.splitlines():
        if "PP-" in line or "MODELS" in line or "=" in line:
            out.write(line.strip()[:200] + "\n")

with open("_model_names_out.txt", "w", encoding="utf-8") as f:
    f.write(out.getvalue())
print("done")