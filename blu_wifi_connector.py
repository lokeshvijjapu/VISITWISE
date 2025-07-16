# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
BLE provisioning server for Raspberry Pi:
- Read/write Wi-Fi credentials
- Read/write Device ID
- Notify client of current Wi-Fi status and Device ID

Uses Bluezero peripheral and D-Bus to advertise over BLE.
"""
import os
import sys
import json
import time
import logging
import subprocess
import dbus
import dbus.mainloop.glib
from gi.repository import GLib
from bluezero import adapter, peripheral, async_tools

# -------- Configuration --------
BLE_SERVICE_UUID = '12345678-1234-5678-1234-56789abcdef0'
BLE_CHAR_UUID    = '12345678-1234-5678-1234-56789abcdef2'

WIFI_FILE        = '/home/neonflake/Desktop/visitwise/last_wifi_credentials.json'
DEVICE_ID_FILE   = '/home/neonflake/Desktop/visitwise/device_id.txt'

# Logging setup
tlogging = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('/home/neonflake/Desktop/visitwise/ble_log.txt'),
        logging.StreamHandler(sys.stdout)
    ]
)

# -------- Persistence --------
def save_json(path, data):
    try:
        with open(path, 'w') as f:
            json.dump(data, f)
        logging.info(f"Saved JSON to {path}")
    except Exception as e:
        logging.error(f"Failed to save JSON: {e}")

def load_json(path):
    try:
        if os.path.exists(path):
            with open(path, 'r') as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load JSON: {e}")
    return {}

# -------- Device ID Persistence --------
def save_device_id(new_id):
    try:
        with open(DEVICE_ID_FILE, 'w') as f:
            f.write(new_id.strip())
        logging.info(f"Saved Device ID: {new_id}")
    except Exception as e:
        logging.error(f"Failed to save Device ID: {e}")

def load_device_id():
    try:
        if os.path.exists(DEVICE_ID_FILE):
            with open(DEVICE_ID_FILE, 'r') as f:
                return f.read().strip()
    except Exception as e:
        logging.error(f"Failed to load Device ID: {e}")
    return 'DEV_DEFAULT'

# -------- Wi-Fi Logic --------
def save_wifi(ssid, password):
    save_json(WIFI_FILE, {'ssid': ssid, 'password': password})

def load_wifi():
    data = load_json(WIFI_FILE)
    return data.get('ssid'), data.get('password')

def get_wifi_status():
    try:
        output = subprocess.run(
            ['nmcli', '--terse', '-f', 'ACTIVE,SSID', 'dev', 'wifi'],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        ).stdout.strip()
        for line in output.splitlines():
            active, ssid = line.split(':', 1)
            if active == 'yes':
                return f"Connected to {ssid}"
    except Exception as e:
        logging.error(f"Wi-Fi status check failed: {e}")
    return "Not connected"

# -------- BLE Characteristic Callbacks --------
def read_value():
    """Return Wi-Fi status and Device ID as byte array for notification/read."""
    status = get_wifi_status()
    device_id = load_device_id()
    payload = f"{status}; Device ID: {device_id}"
    logging.debug(f"Notify payload: {payload}")
    return [dbus.Byte(b) for b in payload.encode('utf-8')]

def connect_to_wifi(ssid, password):
    try:
        subprocess.run(['nmcli', 'networking', 'on'], check=True)
        time.sleep(1)
        subprocess.run(['iw', 'reg', 'set', 'IN'], check=True)
        time.sleep(0.5)
        subprocess.run(['nmcli', 'device', 'wifi', 'rescan'], check=True)
        time.sleep(1)
        result = subprocess.run(
            ['nmcli', 'device', 'wifi', 'connect', ssid, 'password', password],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        logging.info(f"Wi-Fi connected: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Wi-Fi connect failed: {e.stderr.strip()}")
        return False
    except Exception as e:
        logging.error(f"Error connecting Wi-Fi: {e}")
        return False

def write_value(data, characteristic):
    """Handle incoming writes: can be Wi-Fi creds or Device ID updates."""
    try:
        message = ''.join(chr(b) for b in data).strip()
        logging.debug(f"Received BLE write: {message}")
        # Device ID updates prefixed by DEV::::
        if message.startswith('DEV::::'):
            new_id = message.split('DEV::::', 1)[1]
            save_device_id(new_id)
            # Update notification value
            characteristic.set_value(read_value())
            logging.info(f"Updated Device ID via BLE: {new_id}")
            return
        # Wi-Fi credentials separated by ++++
        if '++++' in message:
            ssid, pwd = message.split('++++', 1)
            logging.info(f"Configuring Wi-Fi: SSID={ssid}")
            # delete existing except ssid
            try:
                conns = subprocess.run(['nmcli','-t','-f','NAME','connection','show'],
                                       check=True, stdout=subprocess.PIPE, text=True).stdout.splitlines()
                for conn in conns:
                    if conn != ssid:
                        subprocess.run(['nmcli','connection','delete',conn], check=True)
                logging.debug("Old connections cleared")
            except Exception as e:
                logging.error(f"Failed to clear connections: {e}")
            # connect and save
            if connect_to_wifi(ssid, pwd):
                save_wifi(ssid, pwd)
            characteristic.set_value(read_value())
            return
        logging.error("BLE write unrecognized format")
    except Exception as e:
        logging.error(f"Error in write_value: {e}")

def update_notify(characteristic):
    """Periodic notifier callback to push updates."""
    characteristic.set_value(read_value())
    return characteristic.is_notifying

def notify_callback(notifying, characteristic):
    if notifying:
        logging.info("BLE client subscribed")
        async_tools.add_timer_seconds(3, update_notify, characteristic)
    else:
        logging.info("BLE client unsubscribed")

# -------- Main BLE Server --------
def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    # Attempt auto-reconnect Wi-Fi
    ssid, pwd = load_wifi()
    if ssid and pwd:
        logging.info(f"Auto-reconnecting to Wi-Fi {ssid}")
        connect_to_wifi(ssid, pwd)
    # Setup BLE adapter
    adapters = adapter.list_adapters()
    if not adapters:
        logging.error("No BLE adapter found")
        sys.exit(1)
    ble = adapter.Adapter(adapters[0])
    ble.powered = True
    periph = peripheral.Peripheral(
        adapter_address=ble.address,
        local_name='VisitWisePi',
        appearance=0x0341
    )
    periph.add_service(srv_id=1, uuid=BLE_SERVICE_UUID, primary=True)
    periph.add_characteristic(
        srv_id=1, chr_id=1, uuid=BLE_CHAR_UUID,
        value=[], notifying=False,
        flags=['read','write','notify'],
        read_callback=read_value,
        write_callback=write_value,
        notify_callback=notify_callback
    )
    periph.publish()
    logging.info("BLE service running; advertising VisitWisePi")
    GLib.MainLoop().run()

if __name__ == '__main__':
    if os.geteuid() != 0:
        logging.error("Requires root privileges")
        sys.exit(1)
    main()
