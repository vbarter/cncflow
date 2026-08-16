"""识别器插件位。本轮 hole 现网可用，slot/face 只留位。"""
from . import FEATURE_SCHEMA

PLUGINS = (
    {"id": "hole", "status": "active", "version": FEATURE_SCHEMA},
    {"id": "slot", "status": "stub", "version": None},
    {"id": "face", "status": "stub", "version": None},
)


def list_plugins():
    return [dict(item) for item in PLUGINS]


def run_slot(_path):
    return []


def run_face(_path):
    return []
