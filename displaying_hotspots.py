import subprocess
import time

def scan_wifi():
    # Run the iwlist scan command to get available Wi-Fi networks
    scan_result = subprocess.check_output(["sudo", "iwlist", "wlan0", "scan"])
    
    # Decode the byte output to a string
    scan_result = scan_result.decode('utf-8')
    
    # Parse the result and extract SSIDs (Wi-Fi names)
    networks = []
    for line in scan_result.split("\n"):
        if "ESSID" in line:
            ssid = line.strip().split(":")[1].strip('"')
            networks.append(ssid)
    
    return networks

def connect_wifi(ssid, password):
    # Create WPA configuration
    wpa_config = f"""
    network={{
        ssid="{ssid}"
        psk="{password}"
    }}
    """
    
    # Write configuration to the wpa_supplicant.conf file
    with open("/etc/wpa_supplicant/wpa_supplicant.conf", "a") as conf_file:
        conf_file.write(wpa_config)
    
    # Restart the Wi-Fi interface to apply the new configuration
    subprocess.run(["sudo", "wpa_cli", "-i", "wlan0", "reconfigure"])
    
    # Wait for the connection to be established
    print(f"Connecting to {ssid}...")
    time.sleep(5)  # Give it a few seconds to connect
    
    # Check if the connection was successful by getting the IP address
    ip_result = subprocess.check_output(["hostname", "-I"]).decode('utf-8').strip()
    
    if ip_result:
        print(f"Connected to {ssid} with IP address: {ip_result}")
    else:
        print(f"Failed to connect to {ssid}")

if __name__ == "__main__":
    # Show available networks
    networks = scan_wifi()
    
    if networks:
        print("Nearby Wi-Fi Networks:")
        for idx, network in enumerate(networks, 1):
            print(f"{idx}. {network}")
        
        # Ask the user to select a network
        choice = int(input("Enter the number of the network to connect to: ")) - 1
        if choice < 0 or choice >= len(networks):
            print("Invalid choice")
        else:
            ssid = networks[choice]
            password = input(f"Enter password for {ssid}: ")
            connect_wifi(ssid, password)
    else:
        print("No Wi-Fi networks found.")
