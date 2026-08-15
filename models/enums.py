"""
Domain Enums for Bambu Lab 3D printers and farm management.
"""

from enum import Enum


class AMSSlot(str, Enum):
    A1 = "0"
    A2 = "1"
    A3 = "2"
    A4 = "3"
    EXTERNAL = "255"


class GCodeState(str, Enum):
    RUNNING = "RUNNING"
    PAUSE = "PAUSE"
    FINISH = "FINISH"
    IDLE = "IDLE"
    PREPARE = "PREPARE"
    UNKNOWN = "UNKNOWN"
