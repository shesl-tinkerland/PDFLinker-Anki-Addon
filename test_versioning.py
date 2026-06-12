import re
with open('__init__.py', 'r') as f:
    content = f.read()

new_setup = """
def setup_dependencies() -> None:
    \"\"\"Downloads the PDF viewer in the background so it doesn't freeze Anki.\"\"\"
    version_file = os.path.join(PDFJS_DIR, "pdfjs_version.txt")
    expected_version = "6.0.227-legacy"
    
    needs_download = True
    if os.path.exists(VIEWER_HTML_PATH) and os.path.exists(version_file):
        try:
            with open(version_file, "r") as vf:
                if vf.read().strip() == expected_version:
                    needs_download = False
        except Exception:
            pass

    if not needs_download:
        return

    # Clear old pdfjs directory if it exists to avoid conflicts
    if os.path.exists(PDFJS_DIR):
        import shutil
        try:
            shutil.rmtree(PDFJS_DIR)
        except Exception as e:
            logger.error(f"Failed to clear old PDF.js directory: {e}")

    os.makedirs(PDFJS_DIR, exist_ok=True)
    zip_path = os.path.join(PDFJS_DIR, "pdfjs.zip")
    
    def download_pdfjs() -> None:
        try:
            urllib.request.urlretrieve(PDFJS_RELEASE_URL, zip_path)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(PDFJS_DIR)
            with open(version_file, "w") as vf:
                vf.write(expected_version)
        finally:
            if os.path.exists(zip_path):
                os.remove(zip_path)
"""

old_setup_regex = re.compile(r'def setup_dependencies\(\) -> None:.*?os\.remove\(zip_path\)', re.DOTALL)
content = old_setup_regex.sub(new_setup.strip(), content)

content = content.replace("v6.0.227/pdfjs-6.0.227-dist.zip", "v6.0.227/pdfjs-6.0.227-legacy-dist.zip")

with open('__init__.py', 'w') as f:
    f.write(content)
