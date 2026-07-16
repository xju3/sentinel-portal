import re
import os

with open("sensor_service.py", "r") as f:
    content = f.read()

first_class_idx = content.find("class SensorTypeService:")
imports = content[:first_class_idx]

classes = re.split(r'\n(?=class )', content[first_class_idx:])

file_mapping = {
    "SensorTypeService": "sensor/sensor_type_service.py",
    "SensorDbService": "sensor/sensor_db_service.py",
    "SimCardService": "sensor/sim_card_service.py",
    "SensorBatchService": "sensor/sensor_batch_service.py",
    "SensorThresholdService": "sensor/sensor_threshold_service.py",
    "SensorService": "sensor/sensor_service.py",
    "SensorConfigService": "sensor/sensor_config_service.py",
}

for cls_text in classes:
    match = re.match(r'class (\w+):', cls_text)
    if match:
        cls_name = match.group(1)
        if cls_name in file_mapping:
            with open(file_mapping[cls_name], "w") as f:
                f.write(imports.strip() + "\n\n" + cls_text.strip() + "\n")
