import re
with open('__init__.py', 'r') as f:
    content = f.read()

patch_code = """
            # Patch viewer.mjs to disable OffscreenCanvas which is broken in many QtWebEngine versions
            viewer_mjs = os.path.join(PDFJS_DIR, "web", "viewer.mjs")
            if os.path.exists(viewer_mjs):
                with open(viewer_mjs, "r", encoding="utf-8") as vm:
                    vm_data = vm.read()
                vm_data = vm_data.replace('isOffscreenCanvasSupported: {\\n    value: true,', 'isOffscreenCanvasSupported: {\\n    value: false,')
                with open(viewer_mjs, "w", encoding="utf-8") as vm:
                    vm.write(vm_data)
"""

content = content.replace('vf.write(expected_version)', f'vf.write(expected_version)\n{patch_code}')

with open('__init__.py', 'w') as f:
    f.write(content)
