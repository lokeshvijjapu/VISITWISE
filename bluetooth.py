#!/usr/bin/env python3
# use to check the ble if we enter any msg through ble (nrf) it appears 

import dbus
import dbus.mainloop.glib
from gi.repository import GLib
from bluezero import adapter
from bluezero import peripheral

# Define a characteristic that can be written to
class HelloCharacteristic:
    def __init__(self, uuid, service):
        self.uuid = uuid
        self.flags = ['write']
        self.service = service
        self.value = []

    def WriteValue(self, value, options):
        message = bytearray(value).decode('utf-8')
        print(f"[Received from BLE]: {message}")

# Define a simple BLE service
class HelloService:
    def __init__(self):
        self.ble_adapter = adapter.Adapter()  # Get the default BLE adapter
        self.peripheral = peripheral.Peripheral(self.ble_adapter.address,
                                                local_name='VisitWisePi',
                                                appearance=0x0341)

        hello_service_uuid = '12345678-1234-5678-1234-56789abcdef0'
        hello_char_uuid = '12345678-1234-5678-1234-56789abcdef1'

        self.peripheral.add_service(srv_id=1, uuid=hello_service_uuid, primary=True)
        self.peripheral.add_characteristic(srv_id=1,
                                           chr_id=1,
                                           uuid=hello_char_uuid,
                                           value=[],
                                           notifying=False,
                                           flags=['write'],
                                           write_callback=self.on_write)

    def on_write(self, value, options=None):
        message = bytearray(value).decode('utf-8')
        print(f"[Received from BLE]: {message}")

    def start(self):
        print("Starting BLE advertising...")
        self.peripheral.publish()

if __name__ == '__main__':
    service = HelloService()
    service.start()
    try:
        GLib.MainLoop().run()
    except KeyboardInterrupt:
        print("\nExiting...")
