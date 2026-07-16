import re
import os

with open("diagnosis_service.py", "r") as f:
    content = f.read()

first_class_idx = content.find("class DiagnosisRecordService:")
imports = content[:first_class_idx]

classes = re.split(r'\n(?=class )', content[first_class_idx:])

file_mapping = {
    "DiagnosisRecordService": "diagnosis/diagnosis_record_service.py",
    "DiagnosisResultService": "diagnosis/diagnosis_result_service.py",
    "PatrolDiagnosisRecordService": "diagnosis/patrol_diagnosis_record_service.py"
}

for cls_text in classes:
    match = re.match(r'class (\w+):', cls_text)
    if match:
        cls_name = match.group(1)
        if cls_name in file_mapping:
            with open(file_mapping[cls_name], "w") as f:
                f.write(imports.strip() + "\n\n" + cls_text.strip() + "\n")
