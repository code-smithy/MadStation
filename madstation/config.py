from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    tick_rate_hz: int = 1
    action_cooldown_sec: int = 10


SETTINGS = Settings()
