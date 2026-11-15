from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "assets"


@dataclass
class BoshyConfig:
    window_title: str = "I Wanna Be The Boshy"
    game_exe: Path = ASSETS_DIR / "game" / "I Wanna Be The Boshy.exe"
    game_pid: int | None = None

    # Check these against the game's Options before the first run.
    left_key: str = "left"
    right_key: str = "right"
    jump_key: str = "z"
    shoot_key: str = "x"
    load_save_key: str = "r"

    action_duration: float = 0.05
    reset_timeout: float = 5.0
    max_episode_steps: int = 1000
    goal_room: int = 3  # World 1; explicit target, not any room change.
    reward_step: float = -0.001
    reward_death: float = -10.0
    reward_finish: float = 100.0
