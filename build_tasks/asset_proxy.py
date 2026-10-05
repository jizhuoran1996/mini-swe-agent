"""Forward the existing unauthenticated asset proxy to the Docker bridge."""
import ipaddress
import json
import os
from pathlib import Path
import selectors
import socket
import socketserver
import subprocess
import threading
import urllib.parse
from status import ROOT

configured=urllib.parse.urlsplit(os.environ.get('HTTPS_PROXY',os.environ.get('https_proxy','')))
assert configured.scheme=='http' and configured.hostname in ['127.0.0.1','localhost'] and configured.port
assert not configured.username and not configured.password,'credentialed proxy forwarding is prohibited'
network=json.loads(subprocess.run(['docker','network','inspect','bridge'],capture_output=True,text=True,check=True).stdout)[0]['IPAM']['Config'][0]
subnet=ipaddress.ip_network(network['Subnet']);gateway=network['Gateway'];slots=threading.BoundedSemaphore(16)

class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        if ipaddress.ip_address(self.client_address[0]) not in subnet or not slots.acquire(blocking=False):return
        peer=None
        try:
            peer=socket.create_connection((configured.hostname,configured.port),timeout=10)
            self.request.setblocking(False);peer.setblocking(False)
            ready=selectors.DefaultSelector();ready.register(self.request,selectors.EVENT_READ,peer);ready.register(peer,selectors.EVENT_READ,self.request)
            while True:
                events=ready.select(60)
                if not events:break
                for key,_ in events:
                    data=key.fileobj.recv(65536)
                    if not data:return
                    destination=key.data;destination.setblocking(True);destination.settimeout(30);destination.sendall(data);destination.setblocking(False)
        except (OSError,TimeoutError):pass
        finally:
            if peer:peer.close()
            slots.release()

class Server(socketserver.ThreadingTCPServer):
    daemon_threads=True
    request_queue_size=16

with Server((gateway,0),Handler) as server:
    record={'url':'http://'+gateway+':'+str(server.server_address[1]),'pid':os.getpid(),'credentialed':False,'max_connections':16,'role':'asset preparation only'}
    (ROOT/'runs/asset_proxy.json').write_text(json.dumps(record,indent=2));print('ASSET_TRANSPORT_READY',record['url'],flush=True);server.serve_forever()
