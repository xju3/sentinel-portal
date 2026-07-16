import re
import os

with open("device_service.py", "r") as f:
    content = f.read()

first_class_idx = content.find("class IsoStandardService:")
imports = content[:first_class_idx]

classes = re.split(r'\n(?=class |    class )', content[first_class_idx:])

# For StandardService which is inside another structure or stands alone?
# Wait, "class StandardService" was mentioned. Let's handle it.

file_mapping = {
    "IsoStandardService": "device/iso_standard_service.py",
    "DeviceCategoryService": "device/device_category_service.py",
    "DeviceSpecService": "device/device_spec_service.py",
    "DeviceInstService": "device/device_inst_service.py",
    "SensorMonitoringService": "sensor/sensor_monitoring_service.py",
    "StandardService": "common/crud_factory.py"
}

for cls_text in classes:
    match = re.search(r'class (\w+):', cls_text)
    if match:
        cls_name = match.group(1)
        if cls_name in file_mapping:
            with open(file_mapping[cls_name], "w") as f:
                f.write(imports.strip() + "\n\n" + cls_text.strip() + "\n")
