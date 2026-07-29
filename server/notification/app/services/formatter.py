from dataclasses import dataclass
from datetime import datetime


LEVEL_LABELS = {
    1: "关注",
    2: "异常",
    3: "告警",
    4: "严重",
}


@dataclass(slots=True)
class NotificationTemplateContext:
    device_code: str
    device_name: str
    diagnosed_at: datetime
    fault_description: str
    level_label: str


def _trim(value: str, limit: int) -> str:
    compact = " ".join(value.split())
    return compact[:limit]


def build_template_data(context: NotificationTemplateContext) -> dict[str, dict[str, str]]:
    return {
        "character_string11": {
            "value": _trim(context.device_code or "-", 32),
        },
        "thing2": {
            "value": _trim(context.device_name or "未知设备", 20),
        },
        "time3": {
            "value": context.diagnosed_at.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "thing18": {
            "value": _trim(context.fault_description or "诊断异常", 20),
        },
        "phrase20": {
            "value": _trim(context.level_label or "异常", 5),
        },
    }
