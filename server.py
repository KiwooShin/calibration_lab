"""Local-only dashboard server with one bounded, on-demand calibration endpoint."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
from experiments import ghost

ROOT = Path(__file__).resolve().parent


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(302)
            self.send_header('Location', '/web/')
            self.end_headers()
            return
        super().do_GET()

    def send_json(self, status, data):
        body = json.dumps(data, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != '/api/ghost':
            self.send_json(404, {'error': 'Unknown experiment endpoint'})
            return
        try:
            size = int(self.headers.get('Content-Length', 0))
            if not 0 < size <= 4096:
                raise ValueError('Invalid request size')
            options = json.loads(self.rfile.read(size))
            count = options.get('count', 32)
            noise = options.get('noise_mm', .5)
            spread = options.get('spread', 'diverse')
            if type(count) is not int or not 4 <= count <= 128:
                raise ValueError('Sample count must be an integer between 4 and 128')
            if type(noise) not in (int, float) or not 0 <= noise <= 3:
                raise ValueError('Noise must be between 0 and 3 mm')
            if spread not in ('diverse', 'clustered'):
                raise ValueError('Unknown pose coverage')
            result = ghost(count, noise, spread)
        except (ValueError, TypeError, AttributeError) as exc:
            self.send_json(400, {'error': str(exc)})
            return
        self.send_json(200, result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if not (ROOT / 'results' / 'data.json').exists():
        from run_experiments import main as generate
        generate()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), partial(Handler, directory=str(ROOT)))
    print(f'Calibration lab: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == '__main__':
    main()
