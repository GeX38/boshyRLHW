"""Небольшие проверки среды без запуска игры."""
import unittest
from dataclasses import replace

import gymnasium as gym
from gymnasium.error import ResetNeeded
from gymnasium.utils.env_checker import check_env

from boshy_env import BoshyConfig
from boshy_env.controls import HeldControlsMixin
from boshy_env.memory import BoshySnapshot, MemoryReadError


class FakeGame(HeldControlsMixin):
    def __init__(self):
        self.config = BoshyConfig(action_duration=0)
        self.pressed_keys = set()
        self.events = []

    def _check_focus(self):
        pass

    def key_down(self, key):
        self.events.append(('down', key))
        self.pressed_keys.add(key)

    def key_up(self, key):
        self.events.append(('up', key))
        self.pressed_keys.remove(key)

    def release_all(self):
        for key in sorted(self.pressed_keys):
            self.key_up(key)

    def close(self):
        self.release_all()


class FakeTelemetry:
    def __init__(self):
        self.snapshot = BoshySnapshot(36, 60, 280, False)
        self.tick = 0
        self.error = None

    def read(self):
        if self.error:
            raise self.error
        self.tick += 1
        return replace(self.snapshot, frame=self.tick)

    def close(self):
        pass


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.game, self.telemetry = FakeGame(), FakeTelemetry()
        self.env = gym.make('BoshyTutorial-v0', config=self.game.config,
                            game=self.game, telemetry=self.telemetry).unwrapped
        self.addCleanup(self.env.close)

    def test_gymnasium_api(self):
        obs, _ = self.env.reset(seed=42)
        self.assertEqual(obs.tolist(), [60, 280, 36, 1])
        self.assertTrue(self.env.observation_space.contains(obs))
        check_env(self.env, skip_render_check=True)

    def test_death(self):
        self.env.reset()
        self.telemetry.snapshot = BoshySnapshot(36, None, None, True)
        obs, reward, terminated, truncated, info = self.env.step([0] * 5)
        self.assertEqual(obs.tolist(), [0, 0, 36, 0])
        self.assertAlmostEqual(reward, -10.001)
        self.assertEqual((terminated, truncated, info['is_success']), (True, False, False))

    def test_tutorial_exit(self):
        self.env.reset()
        self.telemetry.snapshot = BoshySnapshot(3, None, None, False)
        _, reward, terminated, truncated, info = self.env.step([0] * 5)
        self.assertAlmostEqual(reward, 99.999)
        self.assertEqual((terminated, truncated, info['is_success']), (True, False, True))

    def test_scene_initialization_before_exit(self):
        self.env.reset()
        snapshots = iter([
            BoshySnapshot(36, None, None, True, frame=0),
            BoshySnapshot(3, None, None, False, frame=1),
        ])
        self.telemetry.read = lambda: next(snapshots)
        obs, reward, terminated, truncated, info = self.env.step([0] * 5)
        self.assertEqual(obs.tolist(), [0, 0, 3, 0])
        self.assertAlmostEqual(reward, 99.999)
        self.assertEqual((terminated, truncated, info['is_success']), (True, False, True))

    def test_time_limit_and_other_room(self):
        self.env.config.max_episode_steps = 1
        self.env.reset()
        self.assertEqual(self.env.step([0] * 5)[2:4], (False, True))
        with self.assertRaises(ResetNeeded):
            self.env.step([0] * 5)
        self.env.reset()
        self.telemetry.snapshot = BoshySnapshot(2, None, None, False)
        _, _, terminated, truncated, info = self.env.step([0] * 5)
        self.assertEqual((terminated, truncated, info['is_success']), (False, True, False))
        self.assertTrue(info['out_of_scope'])

    def test_hold_and_repress_jump(self):
        for jump in (1, 1, 0, 1):
            self.game.perform_action(0, 0, jump, 0, 0, duration=0)
        self.assertEqual(self.game.events, [('down', 'z'), ('up', 'z'), ('down', 'z')])
        self.game.perform_action(1, 1, 0, 0, 0, duration=0)
        self.assertEqual(self.game.pressed_keys, {'left', 'right'})

    def test_read_error_releases_buttons(self):
        self.env.reset()
        self.telemetry.error = MemoryReadError('process disappeared')
        with self.assertRaises(MemoryReadError):
            self.env.step([0, 1, 1, 0, 0])
        self.assertEqual(self.game.pressed_keys, set())
        with self.assertRaises(ResetNeeded):
            self.env.step([0] * 5)


if __name__ == '__main__':
    unittest.main()
