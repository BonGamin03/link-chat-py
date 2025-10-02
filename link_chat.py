import os
import socket
import struct
import time
import uuid


ETHER_TYPE = 0x88B5

BROADCAST = 1
MESSAGE = 2


def mac_to_bytes(mac: str) -> bytes:
    return bytes(int(x, 16) for x in mac.split(':'))


def mac_to_string(b: bytes) -> str:
    return ':'.join('{:02x}'.format(x) for x in b)
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
    
    
    def create_frame(self, dst_mac: str, ftype: int, payload: bytes) -> bytes:
        dst = mac_to_bytes(dst_mac)
        src = mac_to_bytes(self.mac)
        ethertype = struct.pack('!H', ETHER_TYPE)
        header = dst + src + ethertype
        # payload: 1 byte type + data
        frame_payload = struct.pack('!B', ftype) + payload
        return header + frame_payload

    def broadcast_msg(self):
        data = {'name': self.name, 'node_id': self.node_id, 'mac': self.mac}
        self.send_frame('ff:ff:ff:ff:ff:ff', BROADCAST, data=data)

    
    def sen_msg(self, dst_mac: str, message: str):
        data = {'from': self.name, 'node_id': self.node_id, 'text': message}
        self.send_frame(dst_mac, MESSAGE, data=data)

    
    def loop_for_frames(self):
        while self.running:
            try:
                frame, addr = self.sock.recvfrom(65535)
            except BlockingIOError:
                time.sleep(0.05)
                continue
            except Exception:
                continue
            try:
                self.unboxing_frame(frame, addr)
            except Exception as e:
                print('Error manejando trama', e)

    def broadcast_loop(self):
        while self.running:
            self.broadcast_msg()
            time.sleep(5)