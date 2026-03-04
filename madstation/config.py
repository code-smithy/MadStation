from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    tick_rate_hz: int = 1
    action_cooldown_sec: int = 10
    power_priority_tiers: tuple[tuple[str, int], ...] = (
        ("OxygenGenerator", 1),
        ("Heater", 3),
        ("Cooler", 3),
        ("Light", 7),
    )
    npc_speed_min_tiles_per_sec: int = 1
    npc_speed_default_tiles_per_sec: int = 2
    npc_speed_max_tiles_per_sec: int = 4
    oxygen_safe_min_percent: float = 15.0
    suffocation_damage_per_tick_at_zero_o2: float = 8.0
    snapshot_cadence_ticks: int = 10
    snapshot_file_path: str = ".madstation_snapshot.json"
    snapshot_schema_version: int = 1
    command_replay_log_path: str = ".madstation_replay_log.jsonl"
    command_replay_max_entries: int = 5000
    thermal_default_temp_c: float = 21.0
    thermal_space_temp_c: float = -35.0
    thermal_vacuum_cooling_per_edge_c_per_tick: float = 1.0
    thermal_transfer_rate: float = 0.12
    thermal_max_transfer_delta_c_per_tick: float = 2.0
    thermal_heater_delta_c_per_tick: float = 1.6
    thermal_cooler_delta_c_per_tick: float = 1.6


SETTINGS = Settings()
