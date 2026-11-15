"""Запуск домашней среды Boshy на настоящей игре."""
import argparse
import time

from boshy_env import BoshyConfig, BoshyEnv
from boshy_env.launch import game_session


# [left, right, jump, shoot, reload]
ACTIONS = (
    [0, 0, 0, 0, 0], [0, 1, 0, 0, 0], [0, 0, 0, 0, 0],
    [1, 0, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 1, 0, 0],
    [0, 0, 1, 0, 0], [0, 0, 0, 0, 0], [0, 0, 1, 0, 0],
    [0, 0, 0, 1, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 1],
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--steps', type=int, default=20)
    parser.add_argument('--random', action='store_true')
    args = parser.parse_args()
    if args.steps < 1:
        parser.error('--steps должен быть положительным')

    config = BoshyConfig()
    with game_session(config) as reader:
        input('Войди в туториал, вернись в терминал и нажми Enter: ')
        print('Переключись в игру. Начало через 5 секунд.', flush=True)
        time.sleep(5)
        with BoshyEnv(config, telemetry=reader) as env:
            obs, _ = env.reset()
            print('reset:', obs.tolist(), flush=True)
            for step in range(args.steps):
                action = env.action_space.sample() if args.random else ACTIONS[step % len(ACTIONS)]
                obs, reward, terminated, truncated, _ = env.step(action)
                print(step + 1, obs.tolist(), reward, terminated, truncated, flush=True)
                if terminated or truncated:
                    break


if __name__ == '__main__':
    main()
