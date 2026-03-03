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
    npc_speed_min_tiles_per_sec: int = 1
    npc_speed_default_tiles_per_sec: int = 2
    npc_speed_max_tiles_per_sec: int = 4
    oxygen_safe_min_percent: float = 15.0
    suffocation_damage_per_tick_at_zero_o2: float = 8.0


SETTINGS = Settings()
