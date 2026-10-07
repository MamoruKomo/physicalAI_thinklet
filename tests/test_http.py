import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from bridge.server import Bridge, make_handler
from tests.test_control import DEFAULT

class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        path = Path(self.temp.name)/'arm.local.json'; path.write_text(json.dumps(DEFAULT))
        self.bridge = Bridge({'arduino': {'serial_port': 'test-only'}}, path)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.bridge))
        self.thread = threading.Thread(target=self.server.serve_forever); self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):
        self.server.shutdown(); self.thread.join(); self.server.server_close(); self.bridge.close(); self.temp.cleanup()
    def test_status_and_local_assets(self):
        with urlopen(self.url+'/api/status') as response:
            data = json.load(response)
            self.assertFalse(data['arm']['connected']); self.assertEqual(data['mode'], 'stopped')
        with urlopen(self.url) as response:
            self.assertIn('カメラの視界', response.read().decode())
    def test_cross_origin_actions_and_form_posts_are_rejected(self):
        for headers, expected in [({'Origin': 'https://untrusted.example', 'Content-Type': 'application/json'},403),
                                  ({'Content-Type': 'application/x-www-form-urlencoded'},415),
                                  ({'Host': 'untrusted.example', 'Content-Type': 'application/json'},403)]:
            request = Request(self.url+'/api/action', data=b'{"action":"stop"}', headers=headers)
            with self.assertRaises(HTTPError) as error: urlopen(request)
            self.assertEqual(error.exception.code, expected)
    def test_invalid_motion_returns_error_without_arming(self):
        request = Request(self.url+'/api/action', data=b'{"action":"auto"}', headers={'Content-Type':'application/json'})
        with self.assertRaises(HTTPError) as error: urlopen(request)
        self.assertEqual(error.exception.code, 400)
        self.assertFalse(self.bridge.arm_state['armed'])

if __name__ == '__main__': unittest.main()
