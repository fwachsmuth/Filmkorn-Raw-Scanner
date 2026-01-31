#!/usr/bin/env python3
"""
Filmkorn Scanner WiFi Setup Captive Portal

This script creates a WiFi access point and runs a captive portal
that allows users to configure WiFi on the Raspberry Pi.

Usage: sudo python3 portal.py

The script will:
1. Create an AP named "Filmkorn Scanner Setup"
2. Run a DHCP/DNS server (dnsmasq)
3. Run a Flask web server for the captive portal
4. Allow users to scan and connect to WiFi networks
5. Tear down the AP when configuration is complete
"""

import json
import logging
import os
import signal
import subprocess
import sys
import time
from typing import Optional, List, Dict

# Flask imports
try:
    from flask import Flask, render_template, request, jsonify, redirect
except ImportError:
    print("Flask not installed. Install with: sudo apt install python3-flask")
    sys.exit(1)

# Configuration
AP_INTERFACE = "wlan0"
AP_SSID = "Filmkorn Scanner Setup"
AP_IP = "192.168.4.1"
AP_SUBNET = "192.168.4.0/24"
AP_DHCP_START = "192.168.4.10"
AP_DHCP_END = "192.168.4.100"
PORTAL_PORT = 80

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
WIFI_NETWORKS_FILE = os.path.join(PARENT_DIR, ".wifi_networks")
LOGO_PATH = os.path.join(PARENT_DIR, "controller-screens", "logo.png")
HOSTAPD_CONF = "/tmp/filmkorn-hostapd.conf"
DNSMASQ_CONF = "/tmp/filmkorn-dnsmasq.conf"

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

# Flask app
app = Flask(__name__, template_folder=os.path.join(SCRIPT_DIR, "templates"))

# Global state
hostapd_proc: Optional[subprocess.Popen] = None
dnsmasq_proc: Optional[subprocess.Popen] = None
original_nm_managed: bool = True
configured_ssid: Optional[str] = None
# Cached scan from before AP start (wlan0 cannot scan while in AP mode)
_cached_networks: List[Dict] = []


def run_cmd(cmd: List[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command with logging."""
    log.debug(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        check=False
    )
    if check and result.returncode != 0:
        log.error(f"Command failed: {' '.join(cmd)}")
        if result.stderr:
            log.error(f"stderr: {result.stderr}")
    return result


def scan_wifi_networks() -> List[Dict]:
    """Scan for available WiFi networks using nmcli."""
    networks = []
    
    # First, trigger a rescan
    run_cmd(["nmcli", "dev", "wifi", "rescan"], check=False)
    time.sleep(2)  # Wait for scan to complete
    
    # Get network list
    result = run_cmd([
        "nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list"
    ], check=False)
    
    if result.returncode != 0:
        log.warning("nmcli wifi list failed, trying iwlist")
        return scan_wifi_networks_iwlist()
    
    seen = set()
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        parts = line.split(':')
        if len(parts) >= 2:
            ssid = parts[0]
            signal = int(parts[1]) if parts[1].isdigit() else 0
            security = parts[2] if len(parts) > 2 else ""
            
            if ssid and ssid not in seen:
                seen.add(ssid)
                networks.append({
                    "ssid": ssid,
                    "signal": signal,
                    "security": security,
                    "open": security == "" or security == "--"
                })
    
    # Sort by signal strength
    networks.sort(key=lambda x: x["signal"], reverse=True)
    return networks


def scan_wifi_networks_iwlist() -> List[Dict]:
    """Fallback WiFi scanning using iwlist."""
    networks = []
    result = run_cmd(["iwlist", AP_INTERFACE, "scan"], check=False)
    
    if result.returncode != 0:
        log.error("iwlist scan failed")
        return networks
    
    current_network = {}
    seen = set()
    
    for line in result.stdout.split('\n'):
        line = line.strip()
        if "ESSID:" in line:
            ssid = line.split('"')[1] if '"' in line else ""
            if ssid and ssid not in seen:
                if current_network.get("ssid"):
                    networks.append(current_network)
                current_network = {"ssid": ssid, "signal": 0, "security": "", "open": True}
                seen.add(ssid)
        elif "Quality=" in line:
            # Quality=70/100 or Quality=70/70
            try:
                quality_part = line.split("Quality=")[1].split()[0]
                num, denom = quality_part.split("/")
                current_network["signal"] = int(int(num) * 100 / int(denom))
            except:
                pass
        elif "Encryption key:" in line:
            if "on" in line.lower():
                current_network["open"] = False
                current_network["security"] = "WPA"
    
    if current_network.get("ssid"):
        networks.append(current_network)
    
    networks.sort(key=lambda x: x["signal"], reverse=True)
    return networks


def save_wifi_network(ssid: str):
    """Save a WiFi network to the networks file. Chown to pi:pi so scanner (running as pi) can read it."""
    networks = []
    if os.path.exists(WIFI_NETWORKS_FILE):
        try:
            with open(WIFI_NETWORKS_FILE, "r") as f:
                data = json.load(f)
                networks = data.get("networks", [])
        except Exception:
            pass
    
    # Remove existing entry for this SSID
    networks = [n for n in networks if n.get("ssid") != ssid]
    
    # Add new entry at the beginning
    networks.insert(0, {"ssid": ssid, "timestamp": int(time.time())})
    
    # Keep only the last 5
    networks = networks[:5]
    
    try:
        with open(WIFI_NETWORKS_FILE, "w") as f:
            json.dump({"networks": networks}, f)
        # Portal runs as root; scanner runs as pi. Make file readable by pi.
        try:
            import pwd
            pw = pwd.getpwnam("pi")
            os.chown(WIFI_NETWORKS_FILE, pw.pw_uid, pw.pw_gid)
            os.chmod(WIFI_NETWORKS_FILE, 0o644)
        except Exception as e:
            log.warning("Could not chown %s to pi: %s", WIFI_NETWORKS_FILE, e)
        log.info(f"Saved WiFi network: {ssid}")
    except Exception as e:
        log.error(f"Failed to save network: {e}")


def connect_to_wifi(ssid: str, password: str) -> bool:
    """Connect to a WiFi network using NetworkManager."""
    log.info(f"Attempting to connect to: {ssid}")
    
    # First, stop our AP services
    stop_ap_services()
    
    # Give NetworkManager control of the interface
    run_cmd(["nmcli", "dev", "set", AP_INTERFACE, "managed", "yes"], check=False)
    time.sleep(1)
    
    # Try to connect
    if password:
        result = run_cmd([
            "nmcli", "dev", "wifi", "connect", ssid,
            "password", password,
            "ifname", AP_INTERFACE
        ], check=False)
    else:
        result = run_cmd([
            "nmcli", "dev", "wifi", "connect", ssid,
            "ifname", AP_INTERFACE
        ], check=False)
    
    if result.returncode == 0:
        log.info(f"Successfully connected to {ssid}")
        save_wifi_network(ssid)
        return True
    else:
        log.error(f"Failed to connect: {result.stderr}")
        # Restart AP for another try
        start_ap_services()
        return False


def write_hostapd_conf():
    """Write hostapd configuration file."""
    config = f"""interface={AP_INTERFACE}
driver=nl80211
ssid={AP_SSID}
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=0
"""
    with open(HOSTAPD_CONF, "w") as f:
        f.write(config)
    log.info(f"Wrote hostapd config to {HOSTAPD_CONF}")


def write_dnsmasq_conf():
    """Write dnsmasq configuration file for DHCP and captive portal DNS."""
    config = f"""interface={AP_INTERFACE}
bind-interfaces
dhcp-range={AP_DHCP_START},{AP_DHCP_END},255.255.255.0,24h
address=/#/{AP_IP}
"""
    with open(DNSMASQ_CONF, "w") as f:
        f.write(config)
    log.info(f"Wrote dnsmasq config to {DNSMASQ_CONF}")


def start_ap_services():
    """Start the access point and related services."""
    global hostapd_proc, dnsmasq_proc, original_nm_managed
    
    log.info("Starting AP services...")
    
    # Check if NetworkManager is managing the interface
    result = run_cmd(["nmcli", "-t", "-f", "DEVICE,STATE", "dev"], check=False)
    if AP_INTERFACE in result.stdout:
        original_nm_managed = "unmanaged" not in result.stdout
    
    # Stop NetworkManager from managing wlan0
    run_cmd(["nmcli", "dev", "set", AP_INTERFACE, "managed", "no"], check=False)
    time.sleep(1)
    
    # Kill any existing instances
    run_cmd(["pkill", "-9", "hostapd"], check=False)
    run_cmd(["pkill", "-9", "-f", "dnsmasq.*filmkorn"], check=False)
    time.sleep(0.5)
    
    # Bring interface down and configure
    run_cmd(["ip", "link", "set", AP_INTERFACE, "down"], check=False)
    run_cmd(["ip", "addr", "flush", "dev", AP_INTERFACE], check=False)
    run_cmd(["ip", "addr", "add", f"{AP_IP}/24", "dev", AP_INTERFACE], check=False)
    run_cmd(["ip", "link", "set", AP_INTERFACE, "up"], check=False)
    
    # Write configs
    write_hostapd_conf()
    write_dnsmasq_conf()
    
    # Start hostapd
    log.info("Starting hostapd...")
    hostapd_proc = subprocess.Popen(
        ["hostapd", HOSTAPD_CONF],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    time.sleep(2)
    
    if hostapd_proc.poll() is not None:
        log.error("hostapd failed to start")
        stdout, _ = hostapd_proc.communicate()
        log.error(f"hostapd output: {stdout.decode()}")
        return False
    
    # Start dnsmasq
    log.info("Starting dnsmasq...")
    dnsmasq_proc = subprocess.Popen(
        ["dnsmasq", "-C", DNSMASQ_CONF, "-d"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    time.sleep(1)
    
    if dnsmasq_proc.poll() is not None:
        log.error("dnsmasq failed to start")
        stdout, _ = dnsmasq_proc.communicate()
        log.error(f"dnsmasq output: {stdout.decode()}")
        return False
    
    log.info(f"AP started: SSID={AP_SSID}, IP={AP_IP}")
    return True


def stop_ap_services():
    """Stop the access point and related services."""
    global hostapd_proc, dnsmasq_proc
    
    log.info("Stopping AP services...")
    
    if hostapd_proc:
        hostapd_proc.terminate()
        try:
            hostapd_proc.wait(timeout=5)
        except:
            hostapd_proc.kill()
        hostapd_proc = None
    
    if dnsmasq_proc:
        dnsmasq_proc.terminate()
        try:
            dnsmasq_proc.wait(timeout=5)
        except:
            dnsmasq_proc.kill()
        dnsmasq_proc = None
    
    # Clean up
    run_cmd(["pkill", "-9", "hostapd"], check=False)
    run_cmd(["pkill", "-9", "-f", "dnsmasq.*filmkorn"], check=False)
    
    # Restore NetworkManager control
    if original_nm_managed:
        run_cmd(["nmcli", "dev", "set", AP_INTERFACE, "managed", "yes"], check=False)
    
    # Clean up temp files
    for f in [HOSTAPD_CONF, DNSMASQ_CONF]:
        if os.path.exists(f):
            os.unlink(f)
    
    log.info("AP services stopped")


def cleanup_and_exit(signum=None, frame=None):
    """Clean up and exit."""
    log.info("Cleaning up...")
    stop_ap_services()
    sys.exit(0 if configured_ssid else 1)


# Flask routes

@app.route('/')
def index():
    """Main captive portal page."""
    return render_template('index.html')


@app.route('/scan')
def scan_route():
    """Return cached WiFi networks (scan was done before AP start; wlan0 cannot scan in AP mode)."""
    global _cached_networks
    return jsonify(_cached_networks)


@app.route('/connect', methods=['POST'])
def connect():
    """Connect to a WiFi network."""
    global configured_ssid
    
    data = request.get_json()
    ssid = data.get('ssid', '')
    password = data.get('password', '')
    
    if not ssid:
        return jsonify({"success": False, "error": "No SSID provided"})
    
    success = connect_to_wifi(ssid, password)
    
    if success:
        configured_ssid = ssid
        return jsonify({"success": True, "message": f"Connected to {ssid}"})
    else:
        return jsonify({"success": False, "error": "Connection failed. Check password."})


# Captive portal detection endpoints
@app.route('/generate_204')
def generate_204():
    """Android captive portal detection."""
    return redirect('/')


@app.route('/hotspot-detect.html')
def hotspot_detect():
    """Apple captive portal detection."""
    return redirect('/')


@app.route('/ncsi.txt')
def ncsi():
    """Windows captive portal detection."""
    return redirect('/')


@app.route('/connecttest.txt')
def connecttest():
    """Windows 10 captive portal detection."""
    return redirect('/')


@app.route('/redirect')
def portal_redirect():
    """Generic redirect to portal."""
    return redirect('/')


@app.route('/logo.png')
def logo():
    """Serve the logo image."""
    from flask import send_file
    if os.path.exists(LOGO_PATH):
        return send_file(LOGO_PATH, mimetype='image/png')
    else:
        return '', 404


@app.route('/success')
def success():
    """Success page - shown after successful connection."""
    return render_template('success.html', ssid=configured_ssid)


@app.route('/shutdown', methods=['POST'])
def shutdown():
    """Shutdown the portal (called after successful config)."""
    cleanup_and_exit()
    return '', 200


def main():
    """Main entry point."""
    global _cached_networks
    
    # Check for root
    if os.geteuid() != 0:
        print("This script must be run as root (sudo)")
        sys.exit(1)
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, cleanup_and_exit)
    signal.signal(signal.SIGTERM, cleanup_and_exit)
    
    # Scan for WiFi networks BEFORE starting the AP (wlan0 cannot scan while in AP mode)
    log.info("Scanning for WiFi networks before starting AP...")
    run_cmd(["nmcli", "dev", "set", AP_INTERFACE, "managed", "yes"], check=False)
    time.sleep(1)
    _cached_networks = scan_wifi_networks()
    log.info("Cached %d networks for portal", len(_cached_networks))
    
    # Start AP
    if not start_ap_services():
        log.error("Failed to start AP services")
        cleanup_and_exit()
    
    # Run Flask
    log.info(f"Starting web server on http://{AP_IP}:{PORTAL_PORT}")
    try:
        app.run(host=AP_IP, port=PORTAL_PORT, debug=False, threaded=True)
    except Exception as e:
        log.error(f"Flask server error: {e}")
    finally:
        cleanup_and_exit()


if __name__ == '__main__':
    main()
