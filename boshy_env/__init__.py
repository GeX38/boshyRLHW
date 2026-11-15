from gymnasium.envs.registration import register

from .env import BoshyEnv
from .config import BoshyConfig

register(
    id="BoshyTutorial-v0",
    entry_point="boshy_env:BoshyEnv",
    nondeterministic=True,  # A real-time external game, not a seeded emulator.
)

__all__ = ["BoshyEnv", "BoshyConfig"]
