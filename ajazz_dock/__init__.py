"""Ajazz AKP153E dock — host driver, action dispatcher, JSONC config."""

from .device import DockDevice, KEYS
from .config import Config, load_jsonc
from . import actions

__all__ = ["DockDevice", "KEYS", "Config", "load_jsonc", "actions"]
