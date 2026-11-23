"""Publish the disposable NodePort on workstation loopback, preserving every end-to-end TLS byte."""

import json
from pathlib import Path
import runpy
import time

tools = runpy.run_path(str(Path(__file__).with_name("deploy.py")))
util, policy = tools["util"], tools["policy"]
ns, kube, run = (util[k] for k in ("namespace","kubectl","run"))

RELAY = """
import selectors, socket, socketserver, sys
upstream=(sys.argv[1],int(sys.argv[2]))
class Relay(socketserver.BaseRequestHandler):
    def handle(self):
        with socket.create_connection(upstream, timeout=3) as backend, selectors.DefaultSelector() as selector:
            backend.settimeout(10)
            self.request.settimeout(10)
            selector.register(self.request,selectors.EVENT_READ,backend)
            selector.register(backend,selectors.EVENT_READ,self.request)
            while True:
                ready=selector.select(15)
                if not ready: return
                for key,mask in ready:
                    data=key.fileobj.recv(65536)
                    if not data: return
                    key.data.sendall(data)
class Server(socketserver.ThreadingTCPServer):
    daemon_threads=True
    request_queue_size=256
with Server(('0.0.0.0',9443),Relay) as server:
    server.serve_forever()
"""


def main():
    util["validate_cluster"]()
    case=util["CASE"]
    deployment=json.loads((case/"deployment.json").read_text())
    node = json.loads(kube("get","node",util["NODES"][0],"-o","json"))
    node_ip=next(a["address"] for a in node["status"]["addresses"] if a["type"]=="InternalIP")
    service=json.loads(ns("get","service","gateway","-o","json"))
    assert service["spec"]["externalTrafficPolicy"]=="Local"
    port=service["spec"]["ports"][0]["nodePort"]
    name=util["NAMESPACE"]+"-tcp"
    valid=run(["docker","inspect",name],check=False)
    if valid.returncode:
        run(["docker","run","--detach","--name",name,"--network","kind","--read-only","--cap-drop","ALL",
             "--security-opt","no-new-privileges","--user","65532:65532","--pids-limit","300","--memory","256m",
             "--publish","127.0.0.1:"+str(deployment["port"])+":9443","--entrypoint","python",
             util["IMAGES"]["core"][1],"-I","-c",RELAY,node_ip,str(port)])
    info=json.loads(run(["docker","inspect",name]).stdout)[0]
    assert info["Config"]["Cmd"][-2:]==[node_ip,str(port)]
    ip=info["NetworkSettings"]["Networks"]["kind"]["IPAddress"]
    restricted=policy("relay-to-gateway","gateway","Ingress",[{"ipBlock":{"cidr":ip+"/32"}}],[{"protocol":"TCP","port":9443}])
    ns("apply","--server-side","--field-manager=obx-native-qualification","-f","-",data=json.dumps(restricted).encode())
    (case/"ingress.json").write_text(json.dumps({"relay_id":info["Id"],"relay_ip":ip,"bound":"127.0.0.1","node_ip":node_ip,
                                                    "nodeport":port,"policy":restricted,"edge_tls":"end-to-end Windows-to-Gateway"},indent=2)+"\n")
    from openbexi_runtime.spell_server_client import SpellServerClient
    for attempt in range(20):
        c=SpellServerClient.from_config(case/"clients/alice/connection.json")
        try:
            assert c.contexts()==["A"] and len(c.read("A","procedures")["procedures"])==10
            print("Verified ten catalog entries over end-to-end mTLS and the Kubernetes NodePort")
            return
        except Exception:
            if attempt==19: raise
            time.sleep(0.25)
        finally:
            c.forget()


if __name__=="__main__":
    main()
