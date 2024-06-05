import json
from datetime import datetime

with open('Pipfile.lock','r') as f:
    lock_data = json.load(f)

date = datetime.now().strftime("%Y-%m-%d")

packages = lock_data.get('default',{})
dev_packages = lock_data.get('develop',{})

output = ['# Packages and versions as of {}\n'.format(date)]

output.append("# Default Packages:\n")
for package,details in packages.items():
    output.append(f"{package}{details['version']}")

output.append("\n # Development Packages:\n")
for package,details in dev_packages.items():
    output.append(f"{package}{details['version']}")

output_file = 'requirements.txt'
with open(output_file, 'w') as f:
    f.write("\n".join(output))

print(f"Package versions written to {output_file}")