# LinkChat

Una aplicación de mensajería y transferencia de archivos que funciona directamente a nivel de capa de enlace.

## Características

- **Mensajería en tiempo real** entre dispositivos en la misma red
- **Transferencia de archivos** punto a punto
- **Compartir carpetas** comprimidas automáticamente
- **Detección automática** de peers en la red
- **Comunicación directa** sin servidores intermedios

## Requisitos

- Linux (requiere capacidades de socket raw)
- Python 3.6+
- Ejecutar como root

## Instalación y Uso

```bash
# Clonar el repositorio
git clone https://github.com/BonGamin03/link-chat-py.git
cd link-chat-py

# Ejecutar la aplicación (como root)
sudo python3 link_chat.py

```

## Comandos Disponibles

- `usuarios` - Lista peers conectados
- `enviar <mac> <texto>` - Enviar mensaje
- `archivo <mac> <ruta>` - Enviar archivo
- `carpeta <mac> <ruta>` - Enviar carpeta
- `difundir <texto>` - Mensaje broadcast
- `salir` - Terminar aplicación

## Notas

- Los archivos recibidos se guardan en el directorio actual
- Las carpetas se comprimen automáticamente antes de enviar
- Requiere ejecución con privilegios de root para acceso a sockets raw
