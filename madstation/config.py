from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    tick_rate_hz: int = 1
    action_cooldown_sec: int = 10
    power_priority_tiers: tuple[tuple[str, int], ...] = (
        ("OxygenGenerator", 1),
        ("Heater", 3),
        ("Light", 7),
    )


SETTINGS = Settings()
