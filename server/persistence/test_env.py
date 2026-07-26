from app.config import settings
import os
print("OS MYSQL:", os.environ.get("MYSQL_URL"))
print("SETTINGS MYSQL:", settings.mysql_url)
