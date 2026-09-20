import os
import shutil
import zipfile

desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
src_dir = os.path.dirname(os.path.abspath(__file__))
staging_dir = os.path.join(desktop, "slayd_bot_fayllari")
zip_path = os.path.join(desktop, "slide_bot_deploy.zip")

exclude = {
    ".venv",
    "__pycache__",
    ".git",
    ".env",
    "bot.log",
    "bot_database.db",
    "generated_slides",
    "image_cache",
    "test_output",
    "test_speech.txt",
    "check_status.bat",
    "install_autostart.bat",
    "uninstall_autostart.bat",
    "start_background.vbs",
    "start_bot.bat",
    "stop_bot.bat",
    "run_24_7.bat",
    "run_24_7.ps1",
    "test_generator.py",
}

os.makedirs(staging_dir, exist_ok=True)

print("Fayllar tekshirilmoqda va nusxalanmoqda...")
for item in os.listdir(src_dir):
    if item in exclude or item.endswith(".log") or item.endswith(".pyc"):
        continue
    s_item = os.path.join(src_dir, item)
    d_item = os.path.join(staging_dir, item)
    if os.path.isdir(s_item):
        if os.path.exists(d_item):
            shutil.rmtree(d_item)
        shutil.copytree(s_item, d_item)
    else:
        shutil.copy2(s_item, d_item)

print("ZIP arxiv yaratilmoqda...")
if os.path.exists(zip_path):
    os.remove(zip_path)

with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(staging_dir):
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, staging_dir)
            zf.write(full_path, rel_path)

print(f"[OK] slide_bot_deploy.zip muvaffaqiyatli yaratildi: {os.path.getsize(zip_path)} bayt.")
