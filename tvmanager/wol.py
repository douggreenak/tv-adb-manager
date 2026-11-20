"""Wake-on-LAN: wake a TV that is fully powered off (so ADB can't reach it) with a magic packet."""
import re
import socket

_MAC = re.compile(r"^([0-9a-f]{2})([:\-]?)(?:([0-9a-f]{2})\2){4}([0-9a-f]{2})$", re.I)


def normalize_mac(mac):
    """'aa-bb-cc-dd-ee-ff' / 'AABBCCDDEEFF' -> 'aa:bb:cc:dd:ee:ff'. Empty string clears. Raises ValueError."""
    mac = (mac or "").strip()
    if not mac:
        return ""
    if not _MAC.match(mac):
        raise ValueError("invalid MAC address (expected like aa:bb:cc:dd:ee:ff)")
    raw = re.sub(r"[^0-9a-f]", "", mac.lower())
    if raw in ("0" * 12, "f" * 12):
        raise ValueError("invalid MAC address")
    return ":".join(raw[i:i + 2] for i in range(0, 12, 2))


def magic_packet(mac):
    raw = bytes.fromhex(normalize_mac(mac).replace(":", ""))
    return b"\xff" * 6 + raw * 16


def targets(host):
    """Where to send: limited broadcast, the TV's own /24 broadcast (routed subnets) and the TV itself."""
    out = ["255.255.255.255"]
    m = re.match(r"^(\d+\.\d+\.\d+)\.\d+$", host or "")
    if m:
        out += [m.group(1) + ".255", host]
    return out


def send(mac, host, ports=(9, 7), sock_factory=None):
    """Send the magic packet. Returns the number of datagrams sent (0 means every send failed)."""
    pkt = magic_packet(mac)
    s = (sock_factory or socket.socket)(socket.AF_INET, socket.SOCK_DGRAM)
    sent = 0
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for ip in targets(host):
            for port in ports:
                try:
                    s.sendto(pkt, (ip, port))
                    sent += 1
                except OSError:
                    pass
    finally:
        s.close()
    return sent


def arp_mac(host, path="/proc/net/arp"):
    """MAC of `host` from this server's ARP table. Only works for TVs on the server's own subnet."""
    try:
        with open(path) as f:
            for line in f.read().splitlines()[1:]:
                c = line.split()
                if len(c) >= 4 and c[0] == host and c[2] != "0x0":
                    return normalize_mac(c[3])
    except (OSError, ValueError):
        pass
    return None
