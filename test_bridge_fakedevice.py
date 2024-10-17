import os
import threading
import time
from flask import Flask, jsonify, request
from pyhap.accessory import Accessory, Bridge
from pyhap.accessory_driver import AccessoryDriver
from pyhap.const import CATEGORY_LIGHTBULB, CATEGORY_FAN
from time import sleep
import requests
import socket
from zeroconf import Zeroconf, ServiceInfo
#FELIX, NOTE
#in windows, accessory_driver.py, line 653 change
#                os.path.exists(self.persist_file) and os.chmod(self.persist_file, 0o644)
#add period task to update advertissmnet

# Device state (fake device)
device_state = {'light': 'off', 'fan': 'off'}

# Setup RESTful API for fake device
app = Flask(__name__)

@app.route('/device/<device_name>/on', methods=['POST'])
def turn_on_device(device_name):
    if device_name in device_state:
        print(f"{device_name}: orig {device_state[device_name]} to on")
        device_state[device_name] = 'on'
        return jsonify({"message": f"{device_name.capitalize()} turned on", "state": device_state[device_name]}), 200
    return jsonify({"error": "Device not found"}), 404

@app.route('/device/<device_name>/off', methods=['POST'])
def turn_off_device(device_name):
    if device_name in device_state:
        print(f"{device_name}: orig {device_state[device_name]} to off")
        device_state[device_name] = 'off'
        return jsonify({"message": f"{device_name.capitalize()} turned off", "state": device_state[device_name]}), 200
    return jsonify({"error": "Device not found"}), 404

@app.route('/device/<device_name>/status', methods=['GET'])
def get_device_status(device_name):
    if device_name in device_state:
        return jsonify({"state": device_state[device_name]}), 200
    return jsonify({"error": "Device not found"}), 404

# --------------- Light Accessory ---------------
class LightAccessory(Accessory):
    category = CATEGORY_LIGHTBULB

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Create a Lightbulb service
        serv_light = self.add_preload_service('Lightbulb')
        self.char_on = serv_light.get_characteristic('On')

        # Set the callback for when the HomeKit app toggles the light
        self.char_on.setter_callback = self.set_light

    def set_light(self, value):
        state = "on" if value else "off"
        print(f"Turning light {state}")
        try:
            response = requests.post(f"http://192.168.121.66:5000/device/light/{state}")
            response.raise_for_status()
            print(f"Device responded with: {response.json()}")
        except requests.exceptions.RequestException as e:
            print(f"Error communicating with device: {e}")
        # Notify HomeKit of the updated state
        self.char_on.notify()

    @Accessory.run_at_interval(10)  # Run every 10 seconds
    def run(self):
        """Periodically update and broadcast the accessory state."""
        try:
            response = requests.get(f"http://192.168.121.66:5000/device/light/status")
            response.raise_for_status()
            device_state = response.json().get("state")
            is_on = device_state == "on"
            
            # Debugging: Print current device and HomeKit states
            print(f"Device state: {device_state}, HomeKit state: {self.char_on.value}")
            
            if self.char_on.value != is_on:
                print(f"notify Updating HomeKit state to: {'on' if is_on else 'off'}")
                self.char_on.set_value(is_on)
                self.char_on.notify()  # Notify HomeKit of the state change
            else:
                # Even if no change, notify HomeKit to keep it responsive
                print(f"notify.nochange Updating HomeKit state to: {'on' if is_on else 'off'}")
                self.char_on.notify()
        except requests.exceptions.RequestException as e:
            print(f"Error polling device status: {e}")
            
# --------------- Fan Accessory ---------------
class FanAccessory(Accessory):
    category = CATEGORY_FAN

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Create a Fan service
        serv_fan = self.add_preload_service('Fan')
        self.char_on = serv_fan.get_characteristic('On')

        # Set the callback for when the HomeKit app toggles the fan
        self.char_on.setter_callback = self.set_fan

    def set_fan(self, value):
        state = "on" if value else "off"
        print(f"Turning fan {state}")
        try:
            response = requests.post(f"http://192.168.121.66:5000/device/fan/{state}")
            response.raise_for_status()
            print(f"Device responded with: {response.json()}")
        except requests.exceptions.RequestException as e:
            print(f"Error communicating with device: {e}")

    @Accessory.run_at_interval(10)
    def run(self):
        """This method will run every 10 seconds and update the fan status."""
        try:
            response = requests.get(f"http://192.168.121.66:5000/device/fan/status")
            response.raise_for_status()
            device_state = response.json().get("state")
            is_on = device_state == "on"
            if self.char_on.value != is_on:
                self.char_on.set_value(is_on)
        except requests.exceptions.RequestException as e:
            print(f"Error polling device status: {e}")


class HomeKitBridge:

    def __init__(self, name, service_type="_hap._tcp.local.", port=51826):
        self.name = name
        self.service_type = service_type
        self.port = port
        self.zeroconf = Zeroconf()
        self.info = None
        

    def start(self):
        """Start broadcasting the Bonjour service."""
        ip_address = socket.inet_aton(socket.gethostbyname(socket.gethostname()))
        self.info = ServiceInfo(
            type_=self.service_type,
            name=f"{self.name}.{self.service_type}",
            port=self.port,
            addresses=[ip_address],
            properties={'md': self.name, 'pv': '1.0', 'id': 'C8:09:A8:B4:1B:58'},
        )
        self.zeroconf.register_service(self.info)
        print(f"Broadcasting HomeKit Bridge: {self.name} on port {self.port}")

    def stop(self):
        """Stop broadcasting the Bonjour service."""
        if self.info:
            self.zeroconf.unregister_service(self.info)
        self.zeroconf.close()
        print("Stopped broadcasting HomeKit Bridge.")

    def broadcast_periodically(self, interval=60, driver=None):
        """Periodically broadcast the Bonjour service."""
        while True:
            try:
                print(f"skpi broadcasting service...FELIX")
                #self.start()
                sleep(interval)  # Broadcast every `interval` seconds
                driver.update_advertisement()
                #print("Re-broadcasting Bonjour service...")
            except Exception as e:
                print(f"Error broadcasting service: {e}!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
                #break
            sleep(interval)  # Broadcast every `interval` seconds

def run_hap_bridge():
    # Create and start the HomeKit Bridge with mDNS broadcasting
    bridge = HomeKitBridge(name="HomeKit Bridge", port=51826)

    # Start a separate thread for periodic Bonjour broadcasts

    # Main logic for handling accessories (like LightAccessory, FanAccessory, etc.)
    driver = AccessoryDriver(port=51826, persist_file='accessory.state')

    # Create a Bridge instance
    bridge_acc = Bridge(driver, 'HomeKit Bridge')
    
    # Add Light and Fan accessories
    light_accessory = LightAccessory(driver, 'Smart Light')
    fan_accessory = FanAccessory(driver, 'Smart Fan')

    bridge_acc.add_accessory(light_accessory)
    bridge_acc.add_accessory(fan_accessory)

    # Start the accessory driver
    driver.add_accessory(accessory=bridge_acc)
    driver.update_advertisement()

    broadcast_thread = threading.Thread(target=bridge.broadcast_periodically, args=(10,driver), daemon=True)
    broadcast_thread.start()

    driver.start()

    try:
        while True:
            print("TEST")
            sleep(10)  # Keep the program running
    except KeyboardInterrupt:
        bridge.stop()  # Stop broadcasting when the program exits
        
def run_hap_bridge_nozero_cfg():
    # Create the accessory driver without the poll_interval
    driver = AccessoryDriver(port=51826, persist_file='accessory.state')

    # Create a Bridge instance
    bridge = Bridge(driver, 'HomeKit Bridge')

    # Add Light accessory to the bridge
    light_accessory = LightAccessory(driver, 'Smart Light')
    bridge.add_accessory(light_accessory)

    # Add Fan accessory to the bridge
    fan_accessory = FanAccessory(driver, 'Smart Fan')
    bridge.add_accessory(fan_accessory)

    # Start the accessory driver
    driver.add_accessory(accessory=bridge)
    driver.start()

def run_fake_device():
    # Run the fake device's Flask API
    #app.run(port=5000, debug=True, use_reloader=False)
    app.run(host='192.168.121.66', port=5000, debug=False)


if __name__ == "__main__":
    # Run the fake device (Flask server) in one thread
    fake_device_thread = threading.Thread(target=run_fake_device)
    fake_device_thread.start()

    # Run the HAP bridge in another thread
    hap_bridge_thread = threading.Thread(target=run_hap_bridge)
    hap_bridge_thread.start()

    # Join both threads to the main thread
    fake_device_thread.join()
    hap_bridge_thread.join()
