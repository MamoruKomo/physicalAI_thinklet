from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

class FirmwareTests(unittest.TestCase):
    def test_boot_limits_rate_watchdog_and_stop(self):
        root = Path(__file__).resolve().parents[1]
        compiler = shutil.which('c++')
        self.assertIsNotNone(compiler, 'A C++ compiler is required for firmware logic verification')
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory)/'firmware-test'
            subprocess.run([compiler, '-std=c++11', '-Wall', '-Wextra', '-I', str(root/'tests/firmware_stubs'),
                            str(root/'tests/firmware_harness.cpp'), '-o', str(binary)], check=True, capture_output=True)
            subprocess.run([str(binary)], check=True)

if __name__ == '__main__': unittest.main()
