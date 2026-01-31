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
    
    # Check device state first
    dev_result = run_cmd(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device"], check=False)
    log.info("Device states: %s", dev_result.stdout.replace('\n', '; '))
    
    # First, trigger a rescan
    rescan_result = run_cmd(["nmcli", "dev", "wifi", "rescan"], check=False)
    if rescan_result.returncode != 0:
        log.warning("Rescan failed: %s", rescan_result.stderr or rescan_result.stdout)
    time.sleep(2)  # Wait for scan to complete
    
    # Get network list
    result = run_cmd([
        "nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list"
    ], check=False)
    
    log.info("nmcli wifi list returned %d, output length: %d", result.returncode, len(result.stdout or ""))
    
    if result.returncode != 0:
        log.warning("nmcli wifi list failed: %s, trying iwlist", result.stderr or result.stdout)
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
    """Connect to a WiFi network using NetworkManager.
    
    Uses nmcli connection add + nmcli connection up instead of nmcli dev wifi connect,
    because newer NetworkManager versions require explicit key-mgmt which isn't
    supported via 'dev wifi connect' on all distros.
    """
    log.info(f"Attempting to connect to: {ssid}")
    err_path = "/tmp/filmkorn-nmcli-connect.err"
    
    def write_err(msg: str):
        with open(err_path, "a") as f:
            f.write(msg + "\n")
            f.flush()
        log.info("nmcli: %s", msg)
    
    # Clear previous error log
    with open(err_path, "w") as f:
        f.write(f"=== connect_to_wifi({ssid}) ===\n")
        f.flush()
    
    # First, stop our AP services
    write_err("Stopping AP services...")
    stop_ap_services()
    
    # Give NetworkManager control of the interface and time to take over wlan0
    write_err("Setting wlan0 to managed...")
    run_cmd(["nmcli", "dev", "set", AP_INTERFACE, "managed", "yes"], check=False)
    
    # Disconnect any active connection on wlan0 first
    write_err("Disconnecting any active connection on wlan0...")
    subprocess.run(
        ["nmcli", "dev", "disconnect", AP_INTERFACE],
        capture_output=True, text=True, check=False
    )
    
    # Ensure radio is on
    write_err("Ensuring WiFi radio is enabled...")
    subprocess.run(["nmcli", "radio", "wifi", "on"], capture_output=True, text=True, check=False)
    
    # Bring interface up explicitly
    write_err("Bringing interface up...")
    subprocess.run(["ip", "link", "set", AP_INTERFACE, "up"], capture_output=True, text=True, check=False)
    
    # Wait for interface to stabilize
    write_err("Waiting for interface to stabilize (8s)...")
    time.sleep(8)  # wlan0 needs time to leave AP mode and be ready for client connect
    
    # Log current state
    try:
        dev_show = subprocess.run(
            ["nmcli", "-t", "dev", "show", AP_INTERFACE],
            capture_output=True, text=True, check=False, timeout=5
        )
        state_line = [l for l in dev_show.stdout.split('\n') if 'STATE' in l or 'CONNECTION' in l]
        write_err(f"Interface state: {'; '.join(state_line)}")
    except Exception as e:
        write_err(f"Could not get interface state: {e}")
    
    # Delete any existing connection profile for this SSID (to avoid duplicates)
    write_err(f"Deleting any existing profile for '{ssid}'...")
    del_result = subprocess.run(
        ["sudo", "-u", "pi", "nmcli", "connection", "delete", "id", ssid],
        capture_output=True, text=True, check=False
    )
    # Exit code 10 = unknown connection (no profile to delete) - expected on first add
    if del_result.returncode == 0:
        write_err("delete result: 0 - existing profile removed")
    elif del_result.returncode == 10:
        write_err("delete result: 10 - no existing profile (ok)")
    else:
        write_err(f"delete result: {del_result.returncode} - {(del_result.stdout or del_result.stderr or '').strip()}")
    
    # Create a new connection profile with explicit settings
    # This avoids the "802-11-wireless-security.key-mgmt: property is missing" error
    write_err(f"Creating connection profile for '{ssid}'...")
    if password:
        add_cmd = [
            "sudo", "-u", "pi", "nmcli", "connection", "add",
            "type", "wifi",
            "con-name", ssid,
            "ssid", ssid,
            "ifname", AP_INTERFACE,
            "wifi-sec.key-mgmt", "wpa-psk",
            "wifi-sec.psk", password,
        ]
    else:
        add_cmd = [
            "sudo", "-u", "pi", "nmcli", "connection", "add",
            "type", "wifi",
            "con-name", ssid,
            "ssid", ssid,
            "ifname", AP_INTERFACE,
        ]
    
    write_err(f"Running: {' '.join(add_cmd[:10])}...")  # Don't log password
    try:
        add_result = subprocess.run(add_cmd, capture_output=True, text=True, check=False, timeout=30)
        write_err(f"add result: {add_result.returncode} - {(add_result.stdout or add_result.stderr or '').strip()}")
    except subprocess.TimeoutExpired:
        write_err("add TIMEOUT after 30s")
        start_ap_services()
        return False
    except Exception as e:
        write_err(f"add EXCEPTION: {e}")
        start_ap_services()
        return False
    
    if add_result.returncode != 0:
        log.error("Failed to create connection profile: %s", (add_result.stderr or add_result.stdout or "").strip())
        start_ap_services()
        return False
    
    # Log device state before attempting connection
    write_err("Checking device state before connection up...")
    try:
        dev_status = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device"],
            capture_output=True, text=True, check=False, timeout=10
        )
        write_err(f"device status:\n{dev_status.stdout.strip()}")
    except Exception as e:
        write_err(f"device status error: {e}")
    
    # Activate the connection
    write_err(f"Activating connection '{ssid}'...")
    try:
        up_result = subprocess.run(
            ["sudo", "-u", "pi", "nmcli", "connection", "up", "id", ssid],
            capture_output=True, text=True, check=False, timeout=60
        )
        write_err(f"up result: {up_result.returncode} - {(up_result.stdout or up_result.stderr or '').strip()}")
    except subprocess.TimeoutExpired:
        write_err("up TIMEOUT after 60s - connection may still be pending")
        # Check if we connected despite timeout
        try:
            conn_check = subprocess.run(
                ["nmcli", "-t", "-f", "NAME,DEVICE", "connection", "show", "--active"],
                capture_output=True, text=True, check=False, timeout=10
            )
            write_err(f"active connections after timeout:\n{conn_check.stdout.strip()}")
            if ssid in conn_check.stdout:
                write_err("Connection appears active despite timeout - SUCCESS!")
                save_wifi_network(ssid)
                return True
        except Exception:
            pass
        write_err("FAILED: timeout and connection not active")
        subprocess.run(
            ["sudo", "-u", "pi", "nmcli", "connection", "delete", "id", ssid],
            capture_output=True, text=True, check=False
        )
        start_ap_services()
        return False
    except Exception as e:
        write_err(f"up EXCEPTION: {e}")
        subprocess.run(
            ["sudo", "-u", "pi", "nmcli", "connection", "delete", "id", ssid],
            capture_output=True, text=True, check=False
        )
        start_ap_services()
        return False
    
    if up_result.returncode == 0:
        log.info(f"Successfully connected to {ssid}")
        write_err("SUCCESS!")
        save_wifi_network(ssid)
        return True
    else:
        err = (up_result.stderr or up_result.stdout or "").strip()
        log.error("Failed to activate connection: %s (see %s)", err, err_path)
        write_err(f"FAILED: {err}")
        # Clean up the profile we just created
        subprocess.run(
            ["sudo", "-u", "pi", "nmcli", "connection", "delete", "id", ssid],
            capture_output=True, text=True, check=False
        )
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
    log.info("Cleaning up... (configured_ssid=%s)", configured_ssid)
    stop_ap_services()
    exit_code = 0 if configured_ssid else 1
    log.info("Exiting with code %d", exit_code)
    # Use os._exit() to forcefully terminate even from a daemon thread
    # sys.exit() only terminates the calling thread, not the whole process
    os._exit(exit_code)


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
        # Exit portal after a short delay so the scanner's monitor can show the WiFi menu.
        # AP is already down so the browser may not receive this response; exit anyway.
        def exit_after_delay():
            time.sleep(2)
            cleanup_and_exit(0)
        import threading
        threading.Thread(target=exit_after_delay, daemon=True).start()
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
    
    # Ensure clean state before scanning - stop any leftover AP processes
    log.info("Ensuring clean interface state before scan...")
    run_cmd(["systemctl", "stop", "hostapd"], check=False)
    run_cmd(["systemctl", "stop", "dnsmasq"], check=False)
    run_cmd(["pkill", "-9", "hostapd"], check=False)
    run_cmd(["pkill", "-9", "dnsmasq"], check=False)
    
    # Scan for WiFi networks BEFORE starting the AP (wlan0 cannot scan while in AP mode)
    log.info("Preparing interface for WiFi scan...")
    run_cmd(["nmcli", "radio", "wifi", "on"], check=False)
    run_cmd(["nmcli", "dev", "set", AP_INTERFACE, "managed", "yes"], check=False)
    run_cmd(["ip", "link", "set", AP_INTERFACE, "up"], check=False)
    time.sleep(3)  # Wait for interface to stabilize
    
    log.info("Scanning for WiFi networks...")
    _cached_networks = scan_wifi_networks()
    log.info("Cached %d networks for portal", len(_cached_networks))
    
    # If no networks found, try again with longer wait
    if not _cached_networks:
        log.warning("No networks found on first scan, retrying...")
        time.sleep(3)
        _cached_networks = scan_wifi_networks()
        log.info("Retry scan found %d networks", len(_cached_networks))
    
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
