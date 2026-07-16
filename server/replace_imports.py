import os
import re

server_dir = "/Users/tju/Workspace/LHT/Sentinel/Codes/Platform/server"
pattern = re.compile(r'^(\s*)from pub\.services\.[a-z0-9_]+ import', re.MULTILINE)

for root, _, files in os.walk(server_dir):
    for f in files:
        if f.endswith('.py') and '__pycache__' not in root:
            path = os.path.join(root, f)
            try:
                with open(path, 'r', encoding='utf-8') as file:
                    content = file.read()
                
                new_content, num_subs = pattern.subn(r'\1from pub.services import', content)
                
                if num_subs > 0:
                    with open(path, 'w', encoding='utf-8') as file:
                        file.write(new_content)
                    print(f"Updated {path}")
            except Exception as e:
                print(f"Skipping {path}: {e}")
