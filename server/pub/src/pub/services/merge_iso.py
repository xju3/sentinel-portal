with open("customer/iso_standard_service.py", "r") as f:
    customer_iso = f.read()

with open("device/iso_standard_service.py", "r") as f:
    device_iso = f.read()

# Extract methods from device_iso
import re
methods = re.findall(r'(    @staticmethod\n    async def \w+\(.*?\)\s*(?:->.*?)?:\n(?:        .*?\n|^\s*$\n)*)', device_iso, re.MULTILINE | re.DOTALL)

# Append to customer_iso class
class_end = len(customer_iso)
new_content = customer_iso + "\n" + "\n".join(methods)

with open("customer/iso_standard_service.py", "w") as f:
    f.write(new_content)

import os
os.remove("device/iso_standard_service.py")
