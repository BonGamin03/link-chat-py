import os
import socket
import uuid


ETHER_TYPE = 0x88B5



def retrieve_mac_address(iface: str) -> str:
    path = f'/sys/class/net/{iface}/address'
    with open(path, 'r') as f:
        return f.read().strip()
    
class LinkChat:
    def __init__(self, iface: str, name: str = None):
        self.iface = iface
        self.name = name or os.uname().nodename
        self.node_id = str(uuid.uuid4())[:8]
        self.mac = retrieve_mac_address(iface)
        self.running = False

        # Socket raw
        self.sock = None

        # estructuras thread-safe
        self.connected_peers = {}  

        # estado de transferencia de archivos indexado
        self.active_transfers = {}

    def initialize_socket(self):
        self.sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETHER_TYPE))
        self.sock.bind((self.iface, 0))
        # recv no bloqueante
        self.sock.setblocking(False)