"""Run locally: python server.py. UI and dependencies are served from web/."""
import argparse,json
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from calibration.dataset import simulate
from calibration.solver import calibrate

ROOT=Path(__file__).resolve().parent
DEFAULT=None


class Handler(SimpleHTTPRequestHandler):
    def reply(self,status,payload):
        body=json.dumps(payload,allow_nan=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
        self.end_headers();self.wfile.write(body)

    def do_GET(self):
        if self.path=='/api/demo':self.reply(200,DEFAULT)
        else:super().do_GET()

    def do_POST(self):
        if self.path not in ('/api/demo','/api/calibrate'):
            self.reply(404,{'error':'Unknown endpoint'});return
        try:
            length=int(self.headers.get('Content-Length',0))
            if not 0<length<=2_000_000:raise ValueError('Request must be 1 byte–2 MB')
            body=json.loads(self.rfile.read(length))
            if self.path=='/api/demo':
                if not isinstance(body,dict):raise ValueError('Expected an options object')
                allowed={k:body[k] for k in ('count','noise_mm','missing','outliers') if k in body}
                data,truth=simulate(**allowed);result=calibrate(data,'synthetic',truth)
            else:result=calibrate(body)
        except (ValueError,TypeError,KeyError,OverflowError) as error:
            self.reply(400,{'error':str(error)});return
        self.reply(200,result)


def main():
    global DEFAULT
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);args=parser.parse_args()
    data,truth=simulate();DEFAULT=calibrate(data,'synthetic',truth)
    http=ThreadingHTTPServer(('127.0.0.1',args.port),partial(Handler,directory=str(ROOT/'web')))
    print(f'Head-camera calibration: http://127.0.0.1:{args.port}',flush=True)
    try:http.serve_forever()
    except KeyboardInterrupt:http.server_close()


if __name__=='__main__':main()
