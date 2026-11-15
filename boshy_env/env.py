"""A small POMDP wrapper for the original Boshy tutorial, not a simulation."""
import time

import gymnasium as gym
from gymnasium.error import ResetNeeded
import numpy as np

from .config import BoshyConfig
from .game import GameInterface
from .memory import BoshyMemoryReader, MemoryReadError, TUTORIAL_ROOM


class BoshyEnv(gym.Env):
    metadata = {"render_modes": ["rgb_array"]}

    def __init__(self, config=None, *, game=None, telemetry=None, render_mode=None):
        super().__init__()
        self.config = config or BoshyConfig()
        self.render_mode = render_mode
        self.action_space = gym.spaces.MultiBinary(5)
        self.observation_space = gym.spaces.Box(
            low=np.array([-2**31, -2**31, 0, 0], dtype=np.float32),
            high=np.array([2**31, 2**31, 65535, 1], dtype=np.float32),
            dtype=np.float32,
        )
        self.game = None
        self.telemetry = None
        self._needs_reset = True
        self._closed = False
        self.current_step = 0
        self._frame = None
        try:
            self.telemetry = telemetry if telemetry is not None else BoshyMemoryReader(
                pid=self.config.game_pid, exe_path=self.config.game_exe,
            )
            self.game = game if game is not None else GameInterface(self.config)
        except BaseException:
            self.close()
            raise

    def _observe(self, snapshot):
        # Outside tutorial the player handle changes; coordinates are unknown.
        known = snapshot.x is not None and snapshot.y is not None and not snapshot.dead
        return np.array([
            snapshot.x if known else 0, snapshot.y if known else 0,
            snapshot.room, int(known),
        ], dtype=np.float32)

    def _info(self, snapshot):
        return dict(room=snapshot.room, x=snapshot.x, y=snapshot.y,
                    dead=bool(snapshot.dead), telemetry_source=snapshot.source,
                    game_frame=snapshot.frame, step=self.current_step)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if self._closed:
            raise RuntimeError("Среда закрыта")
        self._needs_reset = True
        self.current_step = 0
        self._frame = None
        try:
            self.game.release_all()
            before = self.telemetry.read()
            if before.room != TUTORIAL_ROOM:
                raise RuntimeError("Перед reset() вручную войди в туториал: R не открывает его из меню.")
            if before.frame is None:
                raise RuntimeError("В туториале недоступен счётчик игровых кадров.")
            if options and options.get("keep_position", False):
                self._capture_if_requested()
                self._needs_reset = False
                info = self._info(before)
                info.update(reset_type="current_position", is_success=False)
                return self._observe(before), info
            deadline = time.perf_counter() + self.config.reset_timeout
            while True:
                # Keep R held until the game actually processes a tick. A short
                # pulse can be missed between game ticks.
                self.game.perform_action(left=0, right=0, jump=0, shoot=0,
                                         reload=1, duration=min(.02, self.config.action_duration))
                try:
                    snapshot = self.telemetry.read()
                except MemoryReadError:
                    if time.perf_counter() >= deadline:
                        raise
                    continue  # Runtime pointers briefly disappear during R.
                if snapshot.room != TUTORIAL_ROOM:
                    raise RuntimeError("Сохранение ведёт за пределы туториала; выбери сохранение туториала.")
                if (snapshot.frame != before.frame and not snapshot.dead
                        and snapshot.x is not None and snapshot.y is not None):
                    break
                if time.perf_counter() >= deadline:
                    raise RuntimeError("После R не появился живой персонаж в новом игровом кадре. Проверь клавиши и FPS.")
            self.game.release_all()
            # Clickteam briefly exposes the editor spawn on the first frame
            # after R. Wait two further ticks for the checkpoint to be applied.
            last_frame, ticks = snapshot.frame, 0
            while ticks < 2:
                self.game.perform_action(left=0, right=0, jump=0, shoot=0,
                                         reload=0, duration=min(.02, self.config.action_duration))
                try:
                    snapshot = self.telemetry.read()
                except MemoryReadError:
                    if time.perf_counter() >= deadline:
                        raise
                    continue
                if snapshot.room != TUTORIAL_ROOM:
                    raise RuntimeError("Загрузка вышла за пределы туториала.")
                if snapshot.frame != last_frame:
                    ticks += 1
                    last_frame = snapshot.frame
                if time.perf_counter() >= deadline:
                    raise RuntimeError("Игра не завершила загрузку checkpoint вовремя.")
            if snapshot.dead or snapshot.x is None or snapshot.y is None:
                raise RuntimeError("После загрузки checkpoint персонаж не жив.")
            self._capture_if_requested()
        except BaseException:
            self.game.release_all()
            raise
        self._needs_reset = False
        info = self._info(snapshot)
        info.update(reset_type="current_checkpoint", reset_ack="game_tick", is_success=False)
        return self._observe(snapshot), info

    def step(self, action):
        if self._needs_reset or self._closed:
            raise ResetNeeded("Перед step() вызови reset().")
        started = time.perf_counter()
        try:
            if not self.action_space.contains(np.asarray(action)):
                raise ValueError("Действие — 5 бит: left, right, jump, shoot, reload")
            self.game.perform_action(*action, duration=self.config.action_duration)
            snapshot = self._read_state()
            self._capture_if_requested()
        except BaseException:
            self._needs_reset = True
            self.game.release_all()
            raise
        self.current_step += 1
        dead = bool(snapshot.dead)
        success = snapshot.room == self.config.goal_room and not dead
        outside = snapshot.room not in (TUTORIAL_ROOM, self.config.goal_room)
        terminated = dead or success
        truncated = not terminated and (outside or self.current_step >= self.config.max_episode_steps)
        reward = self.config.reward_step
        if dead:
            reward += self.config.reward_death
        elif success:
            reward += self.config.reward_finish
        self._needs_reset = terminated or truncated
        if self._needs_reset:
            self.game.release_all()
        info = self._info(snapshot)
        info.update(finished=success, is_success=success,
                    out_of_scope=outside, elapsed_seconds=time.perf_counter() - started)
        return self._observe(snapshot), float(reward), bool(terminated), bool(truncated), info

    def _read_state(self):
        # During a room change pointers disappear and frame 0 has no player yet.
        for _ in range(20):
            try:
                snapshot = self.telemetry.read()
                if snapshot.room != TUTORIAL_ROOM or snapshot.frame != 0:
                    return snapshot
            except MemoryReadError:
                pass
            time.sleep(.01)
        raise MemoryReadError("Игра не завершила инициализацию сцены.")

    def _capture_if_requested(self):
        if self.render_mode == "rgb_array":
            self._frame = self.game.screenshot()

    def render(self):
        return None if self._frame is None else self._frame.copy()

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            if self.game is not None:
                self.game.close()
        finally:
            if self.telemetry is not None:
                self.telemetry.close()
