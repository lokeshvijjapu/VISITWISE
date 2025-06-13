#!/usr/bin/env python3

import dbus
import dbus.mainloop.glib
from gi.repository import GLib
from bluezero import adapter
from bluezero import peripheral
import subprocess
import os
import sys
import time
import logging

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('/home/neonflake/Desktop/visitwise/ble_log.txt'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class BLEWiFiCharacteristic:
    def __init__(self, uuid, service):
        self.uuid = uuid
        self.flags = ['write']
        self.service = service
        self.value = []

    def WriteValue(self, value, options):
        message = bytearray(value).decode('utf-8')
        logger.info(f"Received from BLE: {message}")

        try:
            ssid, password = message.split("++++")
        except ValueError:
            logger.error("Invalid format. Use SSID++++Password")
            return

        logger.info(f"Parsed SSID: {ssid}, Password: {password}")
        self.connect_to_wifi(ssid, password)

    def connect_to_wifi(self, ssid, password):
        logger.info("Enabling networking...")
        try:
            subprocess.run(['sudo', 'nmcli', 'networking', 'on'], check=True, capture_output=True, text=True)
            time.sleep(1)  # Reduced stabilization time
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to enable networking: {e.stderr}")
            return

        logger.info("Deleting existing Wi-Fi connections...")
        try:
            result = subprocess.run(['nmcli', '-t', '-f', 'NAME', 'connection', 'show'], stdout=subprocess.PIPE, text=True, check=True)
            connections = result.stdout.strip().splitlines()
            for conn in connections:
                logger.debug(f"Deleting connection: {conn}")
                subprocess.run(['sudo', 'nmcli', 'connection', 'delete', conn], check=True, capture_output=True)
            logger.info("Existing Wi-Fi connections deleted")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to delete connections: {e.stderr}")
            return

        logger.info("Setting regulatory domain to IN...")
        try:
            subprocess.run(['sudo', 'iw', 'reg', 'set', 'IN'], check=True, capture_output=True)
            time.sleep(0.5)  # Reduced delay
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to set regulatory domain: {e.stderr}")

        logger.info("Rescanning networks...")
        try:
            subprocess.run(['sudo', 'nmcli', 'device', 'wifi', 'rescan'], check=True, capture_output=True)
            time.sleep(1)  # Reduced delay
        except subprocess.CalledProcessError as e:
            logger.error(f"Rescan failed: {e.stderr}")

        logger.info(f"Attempting to connect to {ssid}...")
        try:
            result = subprocess.run(
                ['sudo', 'nmcli', 'device', 'wifi', 'connect', ssid, 'password', password],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            logger.info(f"Connected successfully: {result.stdout}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Connection failed: {e.stderr}")

class BLEWiFiService:
    def __init__(self):
        try:
            logger.debug("Checking Bluetooth adapters...")
            adapters = list(adapter.list_adapters())
            if not adapters:
                raise RuntimeError("No Bluetooth adapters found")
            logger.debug(f"Found adapters: {adapters}")

            logger.debug("Initializing BLE adapter...")
            self.ble_adapter = adapter.Adapter(adapters[0])  # Explicitly select first adapter
            if not self.ble_adapter.powered:
                logger.info("Powering on adapter...")
                self.ble_adapter.powered = True

            self.peripheral = peripheral.Peripheral(
                self.ble_adapter.address,
                local_name='VisitWisePi',
                appearance=0x0341
            )
            logger.debug("Peripheral initialized")

            service_uuid = '12345678-1234-5678-1234-56789abcdef0'
            char_uuid = '12345678-1234-5678-1234-56789abcdef1'

            self.peripheral.add_service(srv_id=1, uuid=service_uuid, primary=True)
            self.peripheral.add_characteristic(
                srv_id=1,
                chr_id=1,
                uuid=char_uuid,
                value=[],
                notifying=False,
                flags=['write'],
                write_callback=self.on_write
            )
            logger.debug("BLE service and characteristic added")
        except Exception as e:
            logger.error(f"Failed to initialize BLE: {str(e)}", exc_info=True)
            raise

    def on_write(self, value, options=None):
        characteristic = BLEWiFiCharacteristic(None, None)
        characteristic.WriteValue(value, options)

    def start(self):
        try:
            logger.info("Starting BLE advertising as 'VisitWisePi'...")
            self.peripheral.publish()
            logger.info("BLE advertising started successfully")
        except Exception as e:
            logger.error(f"Failed to start BLE advertising: {str(e)}", exc_info=True)
            raise

if __name__ == '__main__':
    if os.geteuid() != 0:
        logger.error("This script must be run as root. Use sudo.")
        sys.exit(1)

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    logger.debug("D-Bus main loop set up")

    while True:
        try:
            service = BLEWiFiService()
            service.start()
            GLib.MainLoop().run()
        except Exception as e:
            logger.error(f"Service failed: {str(e)}", exc_info=True)
            logger.info("Retrying in 1 second...")
            time.sleep(1)  # Further reduced retry delay
        except KeyboardInterrupt:
            logger.info("Exiting...")
            sys.exit(0)
