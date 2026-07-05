"""YAML 规则加载。规则文件是版本化的配置即代码，启动时加载并缓存。"""
from functools import lru_cache
from pathlib import Path

import yaml

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"


@lru_cache(maxsize=None)
def load_rules(relpath: str) -> dict:
    """加载规则文件，如 load_rules("hole/machinability.yaml")。文件缺失/语法错误直接抛出（fail fast）。"""
    path = RULES_DIR / relpath
    if not path.exists():
        raise FileNotFoundError(f"规则文件不存在: {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"规则文件格式错误（顶层应为 mapping）: {path}")
    return data
