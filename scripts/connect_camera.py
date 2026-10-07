#!/usr/bin/env python3
"""Install/start only the configured THINKLET and expose its loopback camera server."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    config = json.loads((ROOT / 'config/devices.local.json').read_text())
    serial = config['thinklet_cube']['adb_serial']
    def adb(*parts):
        return subprocess.run(['adb', '-s', serial, *parts], check=True, capture_output=True, text=True)
    if args.install:
        print(adb('install', '-r', '-g', str(ROOT / 'build/physical-ai-camera.apk')).stdout.strip())
    forwarding = adb('forward', '--list').stdout.splitlines()
    expected = f'{serial} tcp:8765 tcp:8765'
    if expected not in forwarding:
        adb('forward', '--no-rebind', 'tcp:8765', 'tcp:8765')
    print(adb('shell', 'am', 'start', '-n', 'ai.physical.thinklet/.CameraActivity').stdout.strip())
    print('Camera API: http://127.0.0.1:8765/status')

if __name__ == '__main__': main()
