#!/usr/bin/env python3
"""Local camera → Arduino bridge and control board. Python standard library only."""
import argparse
from collections import deque
import json
import math
import os
from pathlib import Path
import select
import termios
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import URLError
from urllib.request import Request, urlopen

from bridge.control import BrightnessControl

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = 'PHYSICAL_AI_ARM_V1'
CAMERA = 'http://127.0.0.1:8765'

def validate_settings(data):
    keys = ('servo_pin', 'lower_angle', 'upper_angle', 'home_angle')
    for key in keys:
        if type(data[key]) is not int: raise ValueError('ピン・角度は整数で指定してください')
    if not 2 <= data['servo_pin'] <= 19: raise ValueError('サーボ信号ピンは2〜19で指定してください')
    low, high = sorted((data['lower_angle'], data['upper_angle']))
    if not 0 <= low < high <= 180 or not low <= data['home_angle'] <= high:
        raise ValueError('上下角度は0〜180°、初期角度はその範囲内にしてください')
    if type(data['hardware_confirmed']) is not bool: raise ValueError('配線確認の指定が不正です')
    BrightnessControl(data['threshold'], data['hysteresis'], data['bright_raises'])
    return dict(data)

class SerialArm:
    def __init__(self, port):
        self.fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        self.buffer = b''
        try:
            if hasattr(termios, 'TIOCEXCL'):
                import fcntl
                fcntl.ioctl(self.fd, termios.TIOCEXCL)
            settings = termios.tcgetattr(self.fd)
            settings[0] = settings[1] = settings[3] = 0
            settings[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
            settings[4] = settings[5] = termios.B115200
            settings[6][termios.VMIN] = settings[6][termios.VTIME] = 0
            termios.tcsetattr(self.fd, termios.TCSANOW, settings)
            # Opening an Uno can reboot it. No servo is attached by our firmware at boot.
            time.sleep(2)
            termios.tcflush(self.fd, termios.TCIFLUSH)
            self.exchange('HELLO', 'READY ' + IDENTITY, timeout=1.5)
        except Exception:
            self.close(); raise

    def close(self):
        if self.fd is not None:
            os.close(self.fd); self.fd = None

    def exchange(self, command, prefix='STATE ', timeout=.5):
        os.write(self.fd, (command+'\n').encode('ascii'))
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            while b'\n' in self.buffer:
                line, self.buffer = self.buffer.split(b'\n', 1)
                value = line.decode('ascii', errors='replace').strip()
                if value.startswith(prefix): return value
                if value.startswith('ERR '): raise RuntimeError(value[4:])
                if value.startswith('READY ') and prefix != 'READY '+IDENTITY:
                    raise RuntimeError('Arduinoが再起動しました。再接続してください')
            readable, _, _ = select.select([self.fd], [], [], max(0, deadline-time.monotonic()))
            if readable:
                chunk = os.read(self.fd, 4096)
                if not chunk: raise RuntimeError('Arduinoが切断されました')
                self.buffer += chunk
                if len(self.buffer) > 8192: raise RuntimeError('Arduinoの応答形式が異なります')
        raise RuntimeError('Arduinoの応答がありません。専用ファームウェアを確認してください')

    def command(self, text):
        line = self.exchange(text)
        values = list(map(int, line.split()[1:]))
        if len(values) != 6: raise RuntimeError('Arduinoの応答形式が異なります')
        armed, angle, target, pin, low, high = values
        if armed not in (0, 1) or not 0 <= low <= angle <= high <= 180 or not low <= target <= high:
            raise RuntimeError('Arduinoの状態値が不正です')
        return dict(armed=bool(armed), commanded_angle=angle, target_angle=target,
                    servo_pin=pin, min_angle=low, max_angle=high)

class Bridge:
    def __init__(self, device_config, settings_path=None, arm_factory=SerialArm):
        self.lock = threading.RLock()
        self.devices = device_config
        self.settings_path = settings_path or ROOT / 'config/arm.local.json'
        source = self.settings_path if self.settings_path.exists() else ROOT / 'config/arm.example.json'
        self.settings = validate_settings(json.loads(source.read_text()))
        self.control = BrightnessControl(self.settings['threshold'], self.settings['hysteresis'], self.settings['bright_raises'])
        self.camera = dict(state='DISCONNECTED', error='', fresh=False, brightness=None, frame_age_ms=-1)
        self.last_frame = None
        self.arm, self.arm_factory = None, arm_factory
        self.arm_state = dict(armed=False, commanded_angle=None, target_angle=None)
        self.mode = 'stopped'
        self.events = deque(maxlen=40)
        self.running = True
        self.thread = None
        self.event('起動しました。カメラ計測のみ。アーム制御は停止中です。')

    def event(self, message):
        self.events.appendleft(dict(at=time.time(), message=message))

    def fresh(self):
        return self.camera.get('fresh', False)

    def stop(self, message='アーム制御を停止しました'):
        self.mode = 'stopped'
        if self.arm:
            try: self.arm_state = self.arm.command('STOP')
            except Exception as e:
                self.arm.close(); self.arm = None
                self.arm_state = dict(armed=False, commanded_angle=None, target_angle=None)
                self.event(str(e))
        self.event(message)

    def snapshot(self):
        with self.lock:
            return dict(camera=dict(self.camera), arm={**self.arm_state, 'connected': self.arm is not None,
                'position_feedback': False}, mode=self.mode, settings=dict(self.settings),
                control=dict(brightness=self.control.smoothed, light=self.control.light,
                             decision=self.control.decision), events=list(self.events))

    def act(self, action, data=None):
        with self.lock:
            if action == 'stop': self.stop()
            elif action == 'connect':
                if self.arm: return
                self.arm = self.arm_factory(self.devices['arduino']['serial_port'])
                try: self.arm_state = self.arm.command('STATUS')
                except Exception:
                    self.arm.close(); self.arm = None; raise
                self.stop('Arduino接続を確認しました。制御は停止中です。')
            elif action == 'disconnect':
                self.stop();
                if self.arm: self.arm.close(); self.arm = None
                self.arm_state = dict(armed=False, commanded_angle=None, target_angle=None)
                self.event('Arduinoを切断しました')
            elif action == 'configure':
                if self.arm_state['armed']: raise ValueError('設定変更の前に停止してください')
                keys = set(self.settings)
                if set(data or {}) != keys: raise ValueError('設定項目が不足しています')
                settings = validate_settings(data)
                self.settings_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.settings_path.with_suffix('.tmp')
                temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2)+'\n')
                temporary.replace(self.settings_path)
                self.settings = settings
                self.control.configure(settings['threshold'], settings['hysteresis'], settings['bright_raises'])
                self.event('しきい値とアーム設定を保存しました')
            elif action in ('arm', 'auto', 'up', 'down'):
                if not self.arm: raise ValueError('Arduinoを接続してください')
                if not self.settings['hardware_confirmed']: raise ValueError('サーボの配線と可動範囲を確認してください')
                if not self.fresh(): raise ValueError('新しいカメラ映像が届いていません')
                if action == 'arm':
                    s = self.settings; low, high = sorted((s['lower_angle'], s['upper_angle']))
                    self.arm_state = self.arm.command(f"ARM {s['servo_pin']} {low} {high} {s['home_angle']}")
                    self.mode = 'manual'; self.event('アーム制御を有効にしました')
                else:
                    if not self.arm_state['armed']: raise ValueError('先にアーム制御を有効にしてください')
                    if action == 'auto':
                        self.mode = 'auto'; self.event('明るさに連動する自動制御を開始しました')
                    else:
                        self.mode = 'manual'
                        target = self.settings['upper_angle' if action == 'up' else 'lower_angle']
                        self.arm_state = self.arm.command(f'TARGET {target}')
                        self.event('手動：' + ('上げる' if action == 'up' else '下げる'))
            else: raise ValueError('不明な操作です')

    def ingest(self, camera):
        age = camera.get('frame_age_ms', -1)
        fresh = camera.get('state') == 'READY' and type(age) in (int, float) and 0 <= age < 1500
        if fresh:
            value = float(camera['brightness'])
            if not math.isfinite(value) or not 0 <= value <= 100: fresh = False
        was_fresh = self.fresh()
        self.camera = {**camera, 'fresh': fresh}
        if fresh:
            frame = camera.get('frames')
            if frame != self.last_frame:
                self.control.update(camera['brightness']); self.last_frame = frame
        elif self.arm_state['armed']:
            self.stop('カメラ映像が途切れたため、アーム制御を停止しました')
        if not fresh:
            self.last_frame = None
            self.control.smoothed = None
            self.control.light = 'unknown'
        if fresh and not was_fresh: self.event('THINKLETカメラの映像を受信しました')
        elif was_fresh and not fresh: self.event('カメラ接続を確認してください')

    def tick_arm(self):
        if not self.arm or not self.arm_state['armed']: return
        try:
            if self.mode == 'auto' and self.control.decision != 'hold':
                key = 'upper_angle' if self.control.decision == 'up' else 'lower_angle'
                self.arm_state = self.arm.command(f'TARGET {self.settings[key]}')
            else: self.arm_state = self.arm.command('PING')
            if not self.arm_state['armed']:
                self.mode = 'stopped'; self.event('Arduino側で制御が停止されました。再度有効にしてください。')
        except Exception as e: self.stop(str(e))

    def loop(self):
        while self.running:
            started = time.monotonic()
            try:
                with urlopen(CAMERA+'/status', timeout=.45) as response:
                    camera = json.load(response)
            except Exception as e:
                camera = dict(state='DISCONNECTED', error=str(e), frame_age_ms=-1)
            with self.lock:
                try: self.ingest(camera)
                except (ValueError, TypeError, KeyError) as e:
                    self.ingest(dict(state='ERROR', error=str(e), frame_age_ms=-1))
                self.tick_arm()
            time.sleep(max(.02, .25-(time.monotonic()-started)))

    def start(self):
        self.thread = threading.Thread(target=self.loop, daemon=True); self.thread.start()

    def close(self):
        self.running = False
        if self.thread: self.thread.join(timeout=2)
        with self.lock:
            self.stop('ボードを終了しました')
            if self.arm: self.arm.close(); self.arm = None

def make_handler(bridge):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass

        def send(self, code, body, content_type='application/json'):
            if isinstance(body, dict): body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            try: self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError): pass

        def allowed_host(self):
            return self.headers.get('Host', '').split(':')[0] in ('127.0.0.1', 'localhost')

        def do_GET(self):
            if not self.allowed_host(): return self.send(403, {'error': 'local access only'})
            path = self.path.split('?')[0]
            if path == '/api/status': return self.send(200, bridge.snapshot())
            if path == '/api/frame.jpg':
                if not bridge.snapshot()['camera']['fresh']: return self.send(503, {'error': '映像待ち'})
                try:
                    with urlopen(CAMERA+'/frame.jpg', timeout=.6) as response:
                        return self.send(200, response.read(), 'image/jpeg')
                except (URLError, OSError): return self.send(503, {'error': '映像待ち'})
            files = {'/': ('index.html', 'text/html; charset=utf-8'),
                     '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                     '/style.css': ('style.css', 'text/css; charset=utf-8')}
            if path not in files: return self.send(404, {'error': 'not found'})
            name, kind = files[path]
            return self.send(200, (ROOT/'dashboard'/name).read_bytes(), kind)

        def do_POST(self):
            if not self.allowed_host(): return self.send(403, {'error': 'local access only'})
            origin = self.headers.get('Origin')
            if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}',
                                        f'http://localhost:{self.server.server_port}'):
                return self.send(403, {'error': 'origin rejected'})
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.send(415, {'error': 'JSON required'})
            try:
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 4096: raise ValueError('リクエストが不正です')
                data = json.loads(self.rfile.read(length))
                if self.path == '/api/exposure-reset':
                    with bridge.lock:
                        bridge.stop('露出を再調整するため、アーム制御を停止しました')
                    with urlopen(Request(CAMERA+'/exposure-reset', data=b'', method='POST'), timeout=1): pass
                elif self.path == '/api/action': bridge.act(data['action'], data.get('settings'))
                else: return self.send(404, {'error': 'not found'})
                self.send(200, bridge.snapshot())
            except (ValueError, KeyError, TypeError, RuntimeError, OSError) as e:
                self.send(400, {'error': str(e)})
    return Handler

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    devices = json.loads((ROOT/'config/devices.local.json').read_text())
    bridge = Bridge(devices); bridge.start()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(bridge))
    print(f'Control board: http://127.0.0.1:{args.port}', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close(); bridge.close()

if __name__ == '__main__': main()
