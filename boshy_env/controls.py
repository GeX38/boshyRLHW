"""Keep game buttons held across fixed-duration control steps."""

import time


class HeldControlsMixin:
    """Use a backend's key events and focus check without adding key presses.

    The backend supplies ``config``, ``pressed_keys``, ``key_down``, ``key_up``,
    ``release_all`` and ``_check_focus``. Left, right, jump, shoot and reload describe
    whether their buttons are held; a new press requires a release first.
    """

    def perform_action(self, left, right, jump, shoot, reload, duration):
        try:
            desired = set()
            for held, key in (
                (left, self.config.left_key),
                (right, self.config.right_key),
                (jump, self.config.jump_key),
                (shoot, self.config.shoot_key),
                (reload, self.config.load_save_key),
            ):
                if held:
                    desired.add(key)

            self._check_focus()
            # Release old buttons before pressing new ones. Both arrows may
            # intentionally be held together when both action bits are set.
            for key in sorted(self.pressed_keys - desired):
                self.key_up(key)
            for key in sorted(desired - self.pressed_keys):
                self.key_down(key)

            deadline = time.perf_counter() + duration
            while True:
                self._check_focus()
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    break
                time.sleep(min(0.005, remaining))
        except BaseException:
            self.release_all()
            raise
