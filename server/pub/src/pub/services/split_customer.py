import re
import os

with open("customer_service.py", "r") as f:
    content = f.read()

# find all imports (everything before the first class definition)
first_class_idx = content.find("class RegionService:")
imports = content[:first_class_idx]

# Split by class
classes = re.split(r'\n(?=class )', content[first_class_idx:])

file_mapping = {
    "RegionService": "region_service.py",
    "TenantService": "tenant_service.py",
    "TenantSensorService": "tenant_sensor_service.py",
    "SupplierService": "supplier_service.py",
    "ContactService": "contact_service.py",
    "AccountService": "account_service.py",
    "AreaService": "area_service.py",
    "LocationService": "location_service.py",
    "AuthService": "auth_service.py",
    "HealthCheckFreqService": "health_check_freq_service.py",
    "IsoStandardService": "iso_standard_service.py"
}

for cls_text in classes:
    match = re.match(r'class (\w+):', cls_text)
    if match:
        cls_name = match.group(1)
        if cls_name in file_mapping:
            with open(f"customer/{file_mapping[cls_name]}", "w") as f:
                f.write(imports.strip() + "\n\n" + cls_text.strip() + "\n")
