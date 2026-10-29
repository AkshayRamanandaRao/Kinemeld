"""Tour choice survives a backend restart and rejects malformed updates."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
import server


class TourPreferenceTest(unittest.TestCase):
    def test_persist_across_ports_and_reject_invalid_input(self):
        with tempfile.TemporaryDirectory() as directory:
            original = server.TOUR_PREFERENCE
            server.TOUR_PREFERENCE = Path(directory) / "tour-preference.json"
            def start():
                instance = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
                threading.Thread(target=instance.serve_forever, daemon=True).start()
                return instance
            def request(instance, method, value=None):
                conn = http.client.HTTPConnection("127.0.0.1", instance.server_port, timeout=5)
                body = json.dumps(value) if value is not None else None
                conn.request(method, "/api/tour-preference", body, {"Content-Type": "application/json"} if body else {})
                response = conn.getresponse()
                result = response.status, json.loads(response.read())
                conn.close()
                return result
            first = start()
            try:
                self.assertEqual(request(first,"GET"),(200,{"enabled":False}))
                self.assertEqual(request(first,"POST",{"enabled":False}),(200,{"enabled":False}))
                self.assertEqual(request(first,"POST",{"enabled":"false"})[0],400)
            finally:
                first.shutdown(); first.server_close()
            second = start()
            try:
                self.assertEqual(request(second,"GET"),(200,{"enabled":False}))
                self.assertEqual(request(second,"POST",{"enabled":True,"other":1})[0],400)
                self.assertEqual(request(second,"GET"),(200,{"enabled":False}))
            finally:
                second.shutdown(); second.server_close(); server.TOUR_PREFERENCE = original


if __name__ == "__main__":
    unittest.main()
