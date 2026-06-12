import re
with open('__init__.py', 'r') as f:
    content = f.read()

content = content.replace(
    'full_url = f"{base_viewer_url}?file={encoded_file_url}#page={page}"',
    'full_url = f"{base_viewer_url}?file={encoded_file_url}&disableworker=true#page={page}"'
)

with open('__init__.py', 'w') as f:
    f.write(content)
