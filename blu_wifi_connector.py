# -*- coding: utf-8 -*-
#!/usr/bin/env python3
# give the ssid and password in the format SSID++++Password

import dbus
import dbus.mainloop.glib
from gi.repository import GLib
from bluezero import adapter, peripheral, async_tools
import subprocess
import sys
import logging
import os
import time
import json

# Logging setup
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('/home/neonflake/Desktop/visitwise/ble_log.txt'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# BLE UUIDs
SERVICE_UUID = '12345678-1234-5678-1234-56789abcdef0'
CHAR_UUID    = '12345678-1234-5678-1234-56789abcdef2'

# File to store last Wi-Fi credentials
CREDENTIALS_FILE = '/home/neonflake/Desktop/visitwise/last_wifi_credentials.json'

def save_credentials(ssid, password):
    """Save Wi-Fi credentials to a file."""
    try:
        with open(CREDENTIALS_FILE, 'w') as f:
            json.dump({'ssid': ssid, 'password': password}, f)
        logger.info(f"Saved credentials to {CREDENTIALS_FILE}")
    except Exception as e:
        logger.error(f"Failed to save credentials: {e}")

def load_credentials():
    """Load Wi-Fi credentials from a file."""
    try:
        if os.path.exists(CREDENTIALS_FILE):
            with open(CREDENTIALS_FILE, 'r') as f:
                credentials = json.load(f)
            return credentials.get('ssid'), credentials.get('password')
        return None, None
    except Exception as e:
        logger.error(f"Failed to load credentials: {e}")
        return None, None

def get_wifi_status():
    """Return status string: either 'Connected to SSID' or 'Not connected'."""
    try:
        output = subprocess.run(
            ['nmcli', '--terse', '-f', 'ACTIVE,SSID', 'dev', 'wifi'],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        ).stdout.strip()
        for line in output.splitlines():
            active, ssid = line.split(':', 1)
            if active == 'yes':
                return f"Connected to {ssid}"
    except Exception as e:
        logger.error(f"Wi-Fi status check failed: {e}")
    return "Not connected"

def read_value():
    """Return the current Wi-Fi status as a byte array."""
    status = get_wifi_status()
    logger.debug(f"Preparing notification payload: '{status}'")
    data = status.encode('utf-8')
    return [dbus.Byte(b) for b in data]

def connect_to_wifi(ssid, password):
    """Attempt to connect to Wi-Fi with given credentials."""
    try:
        # Enable networking
        logger.info("Enabling networking...")
        subprocess.run(['nmcli', 'networking', 'on'], check=True, capture_output=True, text=True)
        time.sleep(1)

        # Set regulatory domain to IN
        logger.info("Setting regulatory domain to IN...")
        subprocess.run(['iw', 'reg', 'set', 'IN'], check=True, capture_output=True)
        time.sleep(0.5)

        # Rescan networks
        logger.info("Rescanning networks...")
        subprocess.run(['nmcli', 'device', 'wifi', 'rescan'], check=True, capture_output=True)
        time.sleep(1)

        # Connect to Wi-Fi
        logger.info(f"Attempting to connect to {ssid}...")
        result = subprocess.run(
            ['nmcli', 'device', 'wifi', 'connect', ssid, 'password', password],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        logger.info(f"Wi-Fi connection successful: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to connect to Wi-Fi: {e.stderr.strip()}")
        return False
    except Exception as e:
        logger.error(f"Error during Wi-Fi connection: {e}")
        return False

def write_value(data, characteristic):
    """Handle incoming Wi-Fi credentials and attempt to connect."""
    try:
        # Convert dbus.Byte array to string
        credentials = ''.join(chr(b) for b in data).strip()
        logger.debug(f"Received credentials: '{credentials}'")
        
        # Expecting format: "SSID++++password"
        if '++++' not in credentials:
            logger.error("Invalid credentials format. Expected 'SSID++++password'")
            return
        
        ssid, password = credentials.split('++++', 1)
        logger.info(f"Parsed SSID: {ssid}, Password: {password}")

        # Delete existing Wi-Fi connections except the one we might reconnect to
        logger.info("Deleting existing Wi-Fi connections...")
        try:
            result = subprocess.run(['nmcli', '-t', '-f', 'NAME', 'connection', 'show'], 
                                 stdout=subprocess.PIPE, text=True, check=True)
            connections = result.stdout.strip().splitlines()
            for conn in connections:
                if conn != ssid:  # Preserve the connection for the current SSID
                    logger.debug(f"Deleting connection: {conn}")
                    subprocess.run(['nmcli', 'connection', 'delete', conn], check=True, capture_output=True)
            logger.info("Existing Wi-Fi connections deleted")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to delete connections: {e.stderr}")
            return

        # Attempt to connect
        if connect_to_wifi(ssid, password):
            # Save credentials if connection is successful
            save_credentials(ssid, password)
        
        # Update characteristic value to reflect new status
        characteristic.set_value(read_value())
        
    except Exception as e:
        logger.error(f"Error processing write request: {e}")

def update_value(characteristic):
    """Called every 3s when notifying - send updated Wi-Fi status."""
    data = read_value()
    characteristic.set_value(data)
    return characteristic.is_notifying  # return False to stop notifications

def notify_callback(notifying, characteristic):
    """Handle client subscription/unsubscription for notifications."""
    if notifying:
        logger.info("Client subscribed - start notifications")
        async_tools.add_timer_seconds(3, update_value, characteristic)
    else:
        logger.info("Client unsubscribed - stop notifications")

def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    try:
        # Try to reconnect to last known Wi-Fi network
        ssid, password = load_credentials()
        if ssid and password:
            logger.info(f"Attempting to reconnect to last network: {ssid}")
            connect_to_wifi(ssid, password)

        adapters = adapter.list_adapters()
        if not adapters:
            logger.error("No BLE adapter found", exc_info=True)
            sys.exit(1)

        ble = adapter.Adapter(adapters[0])
        if not ble.powered:
            logger.info("Powering on adapter...")
            ble.powered = True

        periph = peripheral.Peripheral(
            adapter_address=ble.address,
            local_name='VisitWisePi',
            appearance=0x0341
        )

        periph.add_service(srv_id=1, uuid=SERVICE_UUID, primary=True)
        periph.add_characteristic(
            srv_id=1,
            chr_id=1,
            uuid=CHAR_UUID,
            value=[],
            notifying=False,
            flags=['read', 'write', 'notify'],
            read_callback=read_value,
            write_callback=write_value,
            notify_callback=notify_callback
        )

        periph.publish()
        logger.info("Advertising as 'VisitWisePi' - waiting for subscriber...")
        GLib.MainLoop().run()

    except Exception as e:
        logger.error(f"Service failed: {str(e)}", exc_info=True)
        logger.info("Retrying in 1 second...")
        time.sleep(1)
        main()

if __name__ == '__main__':
    if os.geteuid() != 0:
        logger.error("Root required; run with sudo.")
        sys.exit(1)
    main()