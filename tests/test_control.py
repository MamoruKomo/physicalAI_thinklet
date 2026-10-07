import json
from pathlib import Path
import tempfile
import unittest
from bridge.control import BrightnessControl
from bridge.server import Bridge, validate_settings

DEFAULT = dict(hardware_confirmed=False, servo_pin=9, lower_angle=70, upper_angle=110,
               home_angle=90, threshold=50, hysteresis=4, bright_raises=True)

class FakeArm:
    def __init__(self, _):
        self.commands = []
        self.state = dict(armed=False, commanded_angle=90, target_angle=90, servo_pin=9, min_angle=70, max_angle=110)
        self.closed = False
        self.fail = False
    def command(self, command):
        self.commands.append(command)
        if self.fail: raise RuntimeError('link lost')
        if command.startswith('ARM '): self.state['armed'] = True
        elif command == 'STOP': self.state['armed'] = False
        elif command.startswith('TARGET '): self.state['target_angle'] = int(command.split()[1])
        return dict(self.state)
    def close(self): self.closed = True

class ControlTests(unittest.TestCase):
    def test_noise_does_not_reverse_decision(self):
        control = BrightnessControl()
        self.assertEqual(control.update(70), 'up')
        for value in [49, 51]*25: self.assertEqual(control.update(value), 'up')
        for _ in range(12): control.update(20)
        self.assertEqual(control.decision, 'down')

    def test_initial_deadband_holds_and_invalid_values_rejected(self):
        control = BrightnessControl()
        self.assertEqual(control.update(50), 'hold')
        for value in [float('nan'), float('inf'), -1, 101]:
            with self.assertRaises(ValueError): control.update(value)

    def test_reverse_and_invalid_configuration(self):
        self.assertEqual(BrightnessControl(bright_raises=False).update(80), 'down')
        for changes in [dict(servo_pin=1), dict(home_angle=180), dict(lower_angle=110),
                        dict(upper_angle=181), dict(threshold=98), dict(hardware_confirmed='true')]:
            with self.assertRaises(ValueError): validate_settings({**DEFAULT, **changes})

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'arm.local.json'
        self.path.write_text(json.dumps(DEFAULT))
        self.bridge = Bridge({'arduino': {'serial_port': 'test-only'}}, self.path, FakeArm)
        self.bridge.ingest(dict(state='READY', frame_age_ms=0, frames=1, brightness=80))
        self.bridge.act('connect')
        self.arm = self.bridge.arm
    def tearDown(self):
        self.bridge.close(); self.temp.cleanup()
    def prepare(self):
        self.bridge.act('configure', {**DEFAULT, 'hardware_confirmed': True})
        self.bridge.ingest(dict(state='READY', frame_age_ms=0, frames=2, brightness=80))
        self.bridge.act('arm'); self.bridge.act('auto')

    def test_no_movement_without_hardware_confirmation_and_explicit_enable(self):
        with self.assertRaises(ValueError): self.bridge.act('arm')
        self.bridge.act('configure', {**DEFAULT, 'hardware_confirmed': True})
        with self.assertRaises(ValueError): self.bridge.act('auto')
        self.assertFalse(any(c.startswith(('ARM ', 'TARGET ')) for c in self.arm.commands))

    def test_brightness_drives_target_only_after_enable(self):
        self.prepare(); self.bridge.tick_arm()
        self.assertEqual(self.arm.commands[-1], 'TARGET 110')
        for frame in range(3, 20): self.bridge.ingest(dict(state='READY', frame_age_ms=0, frames=frame, brightness=10))
        self.bridge.tick_arm(); self.assertEqual(self.arm.commands[-1], 'TARGET 70')
        self.assertFalse(self.bridge.snapshot()['arm']['position_feedback'])

    def test_stale_camera_stops_and_recovery_does_not_restart(self):
        self.prepare()
        self.bridge.ingest(dict(state='READY', frame_age_ms=1500, frames=1, brightness=80))
        self.assertEqual(self.arm.commands[-1], 'STOP')
        self.assertEqual(self.bridge.mode, 'stopped')
        self.bridge.ingest(dict(state='READY', frame_age_ms=0, frames=2, brightness=80))
        count = len(self.arm.commands); self.bridge.tick_arm()
        self.assertEqual(len(self.arm.commands), count)

    def test_duplicate_frames_do_not_change_filter(self):
        before = self.bridge.control.smoothed
        self.bridge.ingest(dict(state='READY', frame_age_ms=100, frames=1, brightness=0))
        self.assertEqual(self.bridge.control.smoothed, before)

    def test_no_reconfiguration_during_motion(self):
        self.prepare()
        with self.assertRaises(ValueError): self.bridge.act('configure', DEFAULT)
        self.assertTrue(json.loads(self.path.read_text())['hardware_confirmed'])

    def test_manual_mode_and_loss_of_serial(self):
        self.prepare(); self.bridge.act('down')
        self.assertEqual(self.bridge.mode, 'manual')
        self.assertEqual(self.arm.commands[-1], 'TARGET 70')
        self.arm.fail = True; self.bridge.tick_arm()
        self.assertIsNone(self.bridge.arm); self.assertTrue(self.arm.closed)
        self.assertFalse(self.bridge.arm_state['armed'])

    def test_watchdog_disarm_is_visible(self):
        self.prepare(); self.arm.state['armed'] = False; self.bridge.mode = 'manual'
        self.bridge.tick_arm(); self.assertEqual(self.bridge.mode, 'stopped')

if __name__ == '__main__': unittest.main()
