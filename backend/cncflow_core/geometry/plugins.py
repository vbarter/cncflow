"""识别器插件。hole 走现网 hole-v3 parse_step；slot/face 本轮空桩，不验收。"""
from . import FEATURE_SCHEMA

HOLE_PLUGIN_VERSION = FEATURE_SCHEMA


def recognize_holes(path: str) -> dict:
    """Existing hole-v3 parser — call parse_step, do not copy it."""
    from ..ingestion.step_parser import parse_step
    return parse_step(path)


def recognize_slots(_path: str) -> list:
    """Empty stub this round; slot features are not accepted."""
    return []


def recognize_faces(_path: str) -> list:
    """Empty stub this round; face features are not accepted."""
    return []


run_slot = recognize_slots
run_face = recognize_faces

PLUGINS = (
    {
        "id": "hole",
        "name": "hole",
        "status": "active",
        "accepted": True,
        "version": HOLE_PLUGIN_VERSION,
        "recognize": recognize_holes,
    },
    {
        "id": "slot",
        "name": "slot",
        "status": "stub",
        "accepted": False,
        "version": "stub",
        "recognize": recognize_slots,
    },
    {
        "id": "face",
        "name": "face",
        "status": "stub",
        "accepted": False,
        "version": "stub",
        "recognize": recognize_faces,
    },
)


def plugin_names():
    return [plugin["name"] for plugin in PLUGINS]


def list_plugins():
    return [
        {"id": plugin["id"], "status": plugin["status"], "version": plugin["version"] if plugin["status"] == "active" else None}
        for plugin in PLUGINS
    ]


def plugin_summaries():
    return [
        {
            "id": plugin["id"],
            "name": plugin["name"],
            "status": plugin["status"],
            "accepted": plugin["accepted"],
            "version": plugin["version"],
        }
        for plugin in PLUGINS
    ]
