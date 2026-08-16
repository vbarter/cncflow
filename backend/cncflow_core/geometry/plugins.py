"""识别器插件位。hole 与 slot 现网可用，face 只留位。"""
from . import FEATURE_SCHEMA, SLOT_SCHEMA

PLUGINS = (
    {"id": "hole", "status": "active", "version": FEATURE_SCHEMA},
    {"id": "slot", "status": "active", "version": SLOT_SCHEMA},
    {"id": "face", "status": "stub", "version": None},
)


def list_plugins():
    return [dict(item) for item in PLUGINS]


def plugin_names():
    return [item["id"] for item in PLUGINS]


def run_slot(path):
    try:
        from .slot import detect_slots
        return detect_slots(path)
    except FileNotFoundError:
        return []
    except Exception:
        return []


def run_face(_path):
    return []
