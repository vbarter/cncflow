"""识别器插件位。hole / slot / face / thread 现网可用。"""
from . import FACE_SCHEMA, FEATURE_SCHEMA, SLOT_SCHEMA, THREAD_SCHEMA

PLUGINS = (
    {"id": "hole", "status": "active", "version": FEATURE_SCHEMA},
    {"id": "slot", "status": "active", "version": SLOT_SCHEMA},
    {"id": "face", "status": "active", "version": FACE_SCHEMA},
    {"id": "thread", "status": "active", "version": THREAD_SCHEMA},
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


def run_face(path):
    try:
        from .face import detect_faces
        return detect_faces(path)
    except FileNotFoundError:
        return []
    except Exception:
        return []


def run_thread(path):
    try:
        from .thread import detect_threads
        return detect_threads(path)
    except FileNotFoundError:
        return []
    except Exception:
        return []
