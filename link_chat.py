
import sys
import os
import socket
import struct
import threading
import time
import json
import argparse
import uuid

# EtherType personalizado
ETHER_TYPE = 0x88B5

# Códigos de tipo de trama
BROADCAST = 1
MESSAGE = 2
BEGIN = 3
CHUNK = 4
COMPLETE = 5

# Tamaño de fragmento de datos que contendra la trama 
SIZE_DATA_TRAMA = 1024


def mac_to_bytes(mac: str) -> bytes:
    return bytes(int(x, 16) for x in mac.split(':'))


def mac_to_string(b: bytes) -> str:
    return ':'.join('{:02x}'.format(x) for x in b)


def get_interface():
    # Preferir primera interfaz no-loopback de /sys/class/net
    try:
        for name in os.listdir('/sys/class/net'):
            if name == 'lo':
                continue
            # omitir interfaces virtuales sin dirección
            addr_path = f'/sys/class/net/{name}/address'
            if os.path.exists(addr_path):
                with open(addr_path, 'r') as f:
                    mac = f.read().strip()
                if mac and mac != '00:00:00:00:00:00':
                    return name
    except Exception:
        pass
    return None


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

    def send_frame(self, dst_mac: str, ftype: int, data: dict = None, raw: bytes = None):
        if data is not None:
            b = json.dumps(data, ensure_ascii=False).encode('utf-8')
        else:
            b = raw or b''
        frame = self.create_frame(dst_mac, ftype, b)
        self.sock.send(frame)

    def broadcast_msg(self):
        data = {'name': self.name, 'node_id': self.node_id, 'mac': self.mac}
        self.send_frame('ff:ff:ff:ff:ff:ff', BROADCAST, data=data)

    def send_msg(self, dst_mac: str, message: str):
        data = {'from': self.name, 'node_id': self.node_id, 'text': message}
        self.send_frame(dst_mac, MESSAGE, data=data)

    def send_file(self, dst_mac: str, path: str):
        filename = os.path.basename(path)
        total = os.path.getsize(path)
        transfer_id = str(uuid.uuid4())[:8]

        # enviar FILE_START
        start = {'transfer_id': transfer_id, 'filename': filename, 'size': total}
        self.send_frame(dst_mac, BEGIN, data=start)
        print(f'Enviando archivo {filename} ({total} bytes) a {dst_mac}')

        seq = 0
        total_sent = 0
        with open(path, 'rb') as f:
            while True:
                chunk = f.read(SIZE_DATA_TRAMA)
                if not chunk:
                    break
                metadata = {'transfer_id': transfer_id, 'seq': seq}
                # payload = metadata json + raw chunk
                meta_b = json.dumps(metadata, ensure_ascii=False).encode('utf-8')
                payload = struct.pack('!H', len(meta_b)) + meta_b + chunk
                self.send_frame(dst_mac, CHUNK, raw=payload)
                total_sent += len(chunk)
                print(f'Enviado fragmento {seq} ({len(chunk)} bytes, {total_sent}/{total} total)')
                seq += 1

        # FILE_END
        end = {'transfer_id': transfer_id}
        self.send_frame(dst_mac, COMPLETE, data=end)
        print('Archivo enviado exitosamente')

    def send_folder(self, dst_mac: str, folder_path: str):
        # crear un tar.gz de la carpeta y enviarlo como un solo archivo
        import tarfile, tempfile
        if not os.path.isdir(folder_path):
            print('Carpeta no encontrada')
            return
        transfer_id = str(uuid.uuid4())[:8]
        base = os.path.basename(os.path.abspath(folder_path.rstrip('/')))
        tmp = tempfile.NamedTemporaryFile(delete=False, prefix=f'netcomm_{transfer_id}_', suffix='.tar.gz')
        tmp.close()
        try:
            with tarfile.open(tmp.name, 'w:gz') as tf:
                tf.add(folder_path, arcname=base)
            print(f'Archivo comprimido creado {tmp.name} ({os.path.getsize(tmp.name)} bytes)')
            self.send_file(dst_mac, tmp.name)
        finally:
            try:
                os.remove(tmp.name)
            except Exception:
                pass

    def unboxing_frame(self, frame: bytes, addr):
        if len(frame) < 15:
            return
        dst = mac_to_string(frame[0:6])
        src = mac_to_string(frame[6:12])
        eth = struct.unpack('!H', frame[12:14])[0]
        payload = frame[14:]
        if eth != ETHER_TYPE:
            return
        if len(payload) < 1:
            return
        ftype = payload[0]
        body = payload[1:]

        # actualizar peer visto
        self.connected_peers[src] = {'last_seen': time.time(), 'mac': src}

        if ftype == BROADCAST:
            try:
                info = json.loads(body.decode('utf-8'))
                self.connected_peers[src].update({'name': info.get('name'), 'node_id': info.get('node_id')})
            except Exception:
                pass
        elif ftype == MESSAGE:
            try:
                info = json.loads(body.decode('utf-8'))
                print(f"\n[MENSAJE] {info.get('from')} ({src}): {info.get('text')}")
            except Exception:
                pass
        elif ftype == BEGIN:
            try:
                info = json.loads(body.decode('utf-8'))
                tid = info.get('transfer_id')
                fname = info.get('filename')
                size = info.get('size')

                print(f"\n[ARCHIVO] Auto-aceptando archivo de {src}: {fname} ({size} bytes)")
                out_path = f"recibido_{tid}_{fname}"
                self.active_transfers[(src, tid)] = {'f': open(out_path, 'wb'), 'expected_seq': 0, 'filename': fname, 'out_path': out_path}
                print(f"Recibiendo en {out_path}")

            except Exception as e:
                print('FILE_START malformado', e)
        elif ftype == CHUNK:
            # payload: 2 bytes meta_len, meta json, luego fragmento crudo
            if len(body) < 2:
                return
            meta_len = struct.unpack('!H', body[:2])[0]
            if len(body) < 2 + meta_len:
                return
            meta = body[2:2+meta_len]
            chunk = body[2+meta_len:]
            try:
                j = json.loads(meta.decode('utf-8'))
            except Exception:
                return
            tid = j.get('transfer_id')
            seq = j.get('seq')
            key = (src, tid)
            state = self.active_transfers.get(key)
            if state is None:
                # no aceptado o desconocido
                return
            # verificación ingenua de orden
            if seq == state['expected_seq']:
                try:
                    state['f'].write(chunk)
                    state['f'].flush()  # asegurar que los datos se escriban inmediatamente
                    state['expected_seq'] += 1
                    print(f"[ARCHIVO] Fragmento recibido {seq} ({len(chunk)} bytes)")
                except Exception as e:
                    print(f"[ARCHIVO] Error escribiendo fragmento {seq}: {e}")
            else:
                print(f"[ARCHIVO] Fragmento fuera de orden: esperado {state['expected_seq']}, recibido {seq}")
        elif ftype == COMPLETE:
            try:
                info = json.loads(body.decode('utf-8'))
                tid = info.get('transfer_id')
                key = (src, tid)
                state = self.active_transfers.get(key)
                if state is None:
                    return
                # cerrar archivo y verificar
                try:
                    state['f'].flush()
                    state['f'].close()
                    # verificar tamaño del archivo
                    out_path = state.get('out_path')
                    if out_path and os.path.exists(out_path):
                        actual_size = os.path.getsize(out_path)
                        print(f"\n[ARCHIVO] Transferencia {tid} completada -> {out_path} ({actual_size} bytes)")
                    else:
                        print(f"\n[ARCHIVO] Transferencia {tid} completada pero archivo no encontrado!")
                except Exception as e:
                    print(f"[ARCHIVO] Error cerrando archivo: {e}")
                    out_path = state.get('out_path')
                # post-proceso: si es archivo comprimido, intentar extraer
                if out_path and (out_path.endswith('.tar') or out_path.endswith('.tar.gz') or out_path.endswith('.tgz')):
                    import tarfile
                    try:
                        extract_dir = out_path + '_extraido'
                        with tarfile.open(out_path, 'r:*') as tf:
                            tf.extractall(path=extract_dir)
                        print(f"[ARCHIVO] Archivo comprimido extraído en {extract_dir}")
                    except Exception as e:
                        print('No se pudo extraer el archivo comprimido:', e)
                # limpiar estado
                try:
                    del self.active_transfers[key]
                except Exception:
                    pass
            except Exception:
                pass

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

    def start(self):
        self.initialize_socket()
        self.running = True
        threading.Thread(target=self.loop_for_frames, daemon=True).start()
        threading.Thread(target=self.broadcast_loop, daemon=True).start()

    def stop(self):
        self.running = False
        try:
            self.sock.close()
        except Exception:
            pass


def console_interface(node: LinkChat):
    print('Terminal LinkChat. Escriba "ayuda" para ver comandos disponibles.')
    while True:
        try:
            cmd = input('>> ').strip()
        except EOFError:
            break
        if not cmd:
            continue
        parts = cmd.split()
        if parts[0] in ('salir', 'terminar', 'fin'):
            break
        elif parts[0] == 'ayuda':
            print('Comandos disponibles: usuarios, enviar <mac> <texto>, archivo <mac> <ruta>, carpeta <mac> <ruta>, difundir <texto>, salir')
        elif parts[0] == 'usuarios':
            for m, info in node.connected_peers.items():
                name = info.get('name') or ''
                seen = time.time() - info.get('last_seen', 0)
                print(f"{m}  {name}  visto hace {seen:.1f}s")
        elif parts[0] == 'enviar' and len(parts) >= 3:
            mac = parts[1]
            text = ' '.join(parts[2:])
            node.send_msg(mac, text)
        elif parts[0] == 'archivo' and len(parts) == 3:
            mac = parts[1]
            path = parts[2]
            if not os.path.exists(path):
                print('Archivo no encontrado')
                continue
            node.send_file(mac, path)
        elif parts[0] == 'carpeta' and len(parts) == 3:
            mac = parts[1]
            path = parts[2]
            if not os.path.exists(path):
                print('Carpeta no encontrada')
                continue
            node.send_folder(mac, path)
        elif parts[0] == 'difundir' and len(parts) >= 2:
            text = ' '.join(parts[1:])
            node.send_msg('ff:ff:ff:ff:ff:ff', text)
        else:
            print('Comando desconocido o formato incorrecto. Escriba "ayuda"')


def main():
    parser = argparse.ArgumentParser(description='EtherNet-Comm: Mensajero a nivel de capa Ethernet')
    parser.add_argument('-i', '--interfaz', help='Interfaz de red a utilizar (ej. eth0)')
    parser.add_argument('-n', '--nombre', help='Nombre para mostrar')
    args = parser.parse_args()

    if os.name != 'posix':
        print('Este programa requiere Linux (AF_PACKET). Use Docker/WSL o ejecute en una máquina Linux.')
        sys.exit(1)

    iface = args.interfaz or get_interface()
    if not iface:
        print('No se encontró interfaz adecuada. Especifique con -i')
        sys.exit(1)

    node = LinkChat(iface, name=args.nombre)
    try:
        node.start()
    except PermissionError:
        print('Permiso denegado: debe ejecutar como root para abrir sockets raw')
        sys.exit(1)

    try:
        console_interface(node)
    finally:
        node.stop()


if __name__ == '__main__':
    main()