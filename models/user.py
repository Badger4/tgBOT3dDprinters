"""
Lightweight dataclass domain models for User Profile & Context, optimized for Raspberry Pi Zero memory efficiency.
"""
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional

@dataclass
class UserNotificationSettings:
    start: bool = True
    finish: bool = True
    pause: bool = True
    min_time_to_end: int = 0
    min_filament: int = 0
    notified_filament: bool = False
    notified_time: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "UserNotificationSettings":
        if not data:
            return cls()
        return cls(
            start=bool(data.get("start", True)),
            finish=bool(data.get("finish", True)),
            pause=bool(data.get("pause", True)),
            min_time_to_end=int(data.get("min_time_to_end", 0)),
            min_filament=int(data.get("min_filament", 0)),
            notified_filament=bool(data.get("notified_filament", False)),
            notified_time=bool(data.get("notified_time", False)),
        )

@dataclass
class UserProfile:
    user_id: str
    is_approved: bool = False
    created_at: float = field(default_factory=time.time)
    access_admin: bool = False
    state: str = "idle"
    selected_printer_id: Optional[str] = None
    active_spool_id: Optional[str] = None
    notify: UserNotificationSettings = field(default_factory=UserNotificationSettings)
    context_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "is_approved": self.is_approved,
            "created_at": self.created_at,
            "admin": {"access_admin": self.access_admin},
            "personal": {},
            "notify": self.notify.to_dict(),
            "state": self.state,
            "context_data": {
                **self.context_data,
                "selected_printer_id": self.selected_printer_id,
                "active_spool_id": self.active_spool_id
            }
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserProfile":
        user_id = str(data.get("user_id", ""))
        is_approved = bool(data.get("is_approved", False))
        created_at = float(data.get("created_at", time.time()))
        admin_data = data.get("admin") or {}
        access_admin = bool(admin_data.get("access_admin", False))
        state = str(data.get("state", "idle"))
        ctx = data.get("context_data") or {}
        selected_pid = ctx.get("selected_printer_id")
        active_spool_id = ctx.get("active_spool_id")
        notify_obj = UserNotificationSettings.from_dict(data.get("notify"))

        return cls(
            user_id=user_id,
            is_approved=is_approved,
            created_at=created_at,
            access_admin=access_admin,
            state=state,
            selected_printer_id=selected_pid,
            active_spool_id=active_spool_id,
            notify=notify_obj,
            context_data=ctx
        )
