#blu_connector.py

#!/usr/bin/env python3

import dbus
import dbus.mainloop.glib
from gi.repository import GLib
from bluezero import adapter
from bluezero import peripheral
import subprocess
import os
import sys

class BLEWiFiCharacteristic:
    def __init__(self, uuid, service):
        self.uuid = uuid
        self.flags = ['write']
        self.service = service
        self.value = []

    def WriteValue(self, value, options):
        message = bytearray(value).decode('utf-8')
        print(f"[Received from BLE]: {message}")

        try:
            ssid, password = message.split("++++")
        except ValueError:
            print("[Error] Invalid format. Use SSID++++Password")
            return

        print(f"[Parsed] SSID: {ssid}, Password: {password}")
        self.connect_to_wifi(ssid, password)

    def connect_to_wifi(self, ssid, password):
        # Ensure regulatory domain is set for correct channel availability
        print("[WiFi] Checking regulatory domain...")
        try:
            reg = subprocess.run(['iw', 'reg', 'get'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if 'country IN' not in reg.stdout:
                print("[WiFi] Setting regulatory domain to IN...")
                subprocess.run(['sudo', 'iw', 'reg', 'set', 'IN'], check=True)
        except subprocess.CalledProcessError as e:
            print(f"[WiFi] Failed to set regulatory domain: {e.stderr}")

        # Rescan available networks
        print("[WiFi] Rescanning networks...")
        try:
            subprocess.run(['sudo', 'nmcli', 'device', 'wifi', 'rescan'], check=True)
        except subprocess.CalledProcessError as e:
            print(f"[WiFi] Rescan failed: {e.stderr}")

        # Connect to the specified SSID
        print(f"[WiFi] Attempting to connect to {ssid}...")
        command = ['nmcli', 'device', 'wifi', 'connect', ssid, 'password', password]

        try:
            result = subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            print(f"[WiFi] Connected successfully:\n{result.stdout}")
        except subprocess.CalledProcessError as e:
            print(f"[WiFi] Connection failed:\n{e.stderr}")

class BLEWiFiService:
    def __init__(self):
        self.ble_adapter = adapter.Adapter()
        self.peripheral = peripheral.Peripheral(self.ble_adapter.address,
                                                local_name='VisitWisePi',
                                                appearance=0x0341)

        service_uuid = '12345678-1234-5678-1234-56789abcdef0'
        char_uuid = '12345678-1234-5678-1234-56789abcdef1'

        self.peripheral.add_service(srv_id=1, uuid=service_uuid, primary=True)
        self.peripheral.add_characteristic(srv_id=1,
                                           chr_id=1,
                                           uuid=char_uuid,
                                           value=[],
                                           notifying=False,
                                           flags=['write'],
                                           write_callback=self.on_write)

    def on_write(self, value, options=None):
        characteristic = BLEWiFiCharacteristic(None, None)
        characteristic.WriteValue(value, options)

    def start(self):
        print("[BLE] Starting BLE advertising as 'VisitWisePi'...")
        self.peripheral.publish()

if __name__ == '__main__':
    if os.geteuid() != 0:
        print("This script must be run as root. Use sudo.")
        sys.exit(1)

    service = BLEWiFiService()
    service.start()

    try:
        GLib.MainLoop().run()
    except KeyboardInterrupt:
        print("\n[BLE] Exiting...")
