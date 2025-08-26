
# Raspberry Pi Zero 2W – Systemd Service Setup Documentation

## Overview
We are running three background programs as services:  

1. **BLE Wi-Fi Connector** (`blewifi.service`)  
   - Starts at boot.  
   - Keeps running in background (so Wi-Fi can be reconfigured mid-session).  

2. **MediaMTX** (`mediamtx.service`)  
   - Starts automatically after network is online.  
   - Keeps running in background.  

3. **Sender** (`sender.service`)  
   - Starts automatically after network is online.  
   - Keeps running in background.  

---

## Service Files

### 1. BLE Wi-Fi Connector
File: `/etc/systemd/system/blewifi.service`
```ini
[Unit]
Description=BLE Wi-Fi Connector
After=network.target
Wants=network.target

[Service]
ExecStart=/home/neonflake/visitwise/venv/bin/python3 /home/neonflake/visitwise/blu_wifi_connector.py
WorkingDirectory=/home/neonflake/visitwise
Restart=always
User=neonflake

[Install]
WantedBy=multi-user.target
```

### 2. MediaMTX
File: `/etc/systemd/system/mediamtx.service`
```ini
[Unit]
Description=MediaMTX Service
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/home/neonflake/mediamtx
WorkingDirectory=/home/neonflake
Restart=always
User=neonflake

[Install]
WantedBy=multi-user.target
```

### 3. Sender
File: `/etc/systemd/system/sender.service`
```ini
[Unit]
Description=Sender Python Script
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/python3 /home/neonflake/project/sender.py
WorkingDirectory=/home/neonflake/project
Restart=always
User=neonflake

[Install]
WantedBy=multi-user.target
```

---

## Commands

### Reload systemd (after editing services)
```bash
sudo systemctl daemon-reload
```

### Enable services at boot
```bash
sudo systemctl enable blewifi
sudo systemctl enable mediamtx
sudo systemctl enable sender
```

### Start services immediately
```bash
sudo systemctl start blewifi
sudo systemctl start mediamtx
sudo systemctl start sender
```

### Stop services
```bash
sudo systemctl stop blewifi
sudo systemctl stop mediamtx
sudo systemctl stop sender
```

### Restart services
```bash
sudo systemctl restart blewifi
sudo systemctl restart mediamtx
sudo systemctl restart sender
```

### Check status
```bash
systemctl status blewifi
systemctl status mediamtx
systemctl status sender
```

### View logs (live)
```bash
sudo journalctl -u blewifi -f
sudo journalctl -u mediamtx -f
sudo journalctl -u sender -f
```

---

## Notes
- `blewifi.service` runs first at boot to manage Wi-Fi over BLE.  
- `mediamtx.service` and `sender.service` wait for the network to be online.  
- All services run as **user = neonflake**.  
- If any service crashes, systemd will restart it automatically (`Restart=always`).  
