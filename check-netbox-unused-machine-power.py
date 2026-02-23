#!/usr/bin/python3
# Copyright SUSE LLC

# ruff: noqa: N816, T201

# This script will exit 1 if qe.nue2.suse.org machines that are marked as unused
# in netbox still draw more than MAX_POWER Watts (default: 5).

import os
import sys

import netsnmp
import pynetbox
from termcolor import colored as co

verbose = os.environ.get("VERBOSE") == "1"
netbox_token = os.environ["NETBOX_TOKEN"]
max_power = int(os.environ.get("MAX_POWER", "5"))


class SNMP:
    def __init__(self, host: str, community: str = "public") -> None:
        self.host = host
        self.community = community

    def get(self, tag: str, iid: str = "0") -> str:
        var = netsnmp.Varbind(tag, iid)
        res = netsnmp.snmpget(var, Version=1, DestHost=self.host, Community=self.community)
        return res[0]


def print_device(device: pynetbox.models.dcim.Devices, dev_pdu_power: dict, watts: int) -> None:
    s = "  " if verbose else ""
    dev_pdu_power = " ".join([f"{h}:{co(p, 'green' if s else 'red')}={w}W" for (h, p), (w, s) in dev_pdu_power.items()])
    print(f"{s}{device.name} status={device.status.value} {dev_pdu_power} ∑{watts}W")


def print_no_connection(device: pynetbox.models.dcim.Devices) -> None:
    if verbose:
        print(f"No connection for {device.name} ({device.display_url})", file=sys.stderr)


# Either download the SNMP MIBs from the PDU's webui, extract them to ~/.snmp/mibs/
# and set os.environ['MIBS'] = 'EATON-EPDU-MIB' to load them, or set the OID statically:
outletDesignator = ".1.3.6.1.4.1.534.6.6.7.6.1.1.6"
outletWatts = ".1.3.6.1.4.1.534.6.6.7.6.5.1.3"
outletControlStatus = ".1.3.6.1.4.1.534.6.6.7.6.6.1.2"

# Initialize the NetBox instance
nb = pynetbox.api("https://netbox.suse.de", token=netbox_token)

# Fetch devices matching the tag and status filter, "role=server" only
devices = nb.dcim.devices.filter(tag="qe-lsg", status__n="active", location_id__n={11, 103}, site_id=5, role_id=24)

power_hungry_devices = []
good_devices = []

# Print the results
for device in devices:
    if not device.name.endswith("nue2.suse.org"):
        continue
    power_ports = nb.dcim.power_ports.filter(device_id=device.id)
    dev_pdu_power = {}
    for p in power_ports:
        if not p.connected_endpoints:
            continue
        pdu_host = p.connected_endpoints[0].device.description
        pwr_socket = p.connected_endpoints[0].name
        if "suse" not in pdu_host:
            print(f"Invalid PDU '{pdu_host}' for {device.name}", file=sys.stderr)
            continue
        if "-" in pwr_socket:
            pwr_socket = pwr_socket.split("-")[0]
        snmp = SNMP(pdu_host)
        w = int(snmp.get(outletWatts, f"0.{pwr_socket}"))
        s = bool(int(snmp.get(outletControlStatus, f"0.{pwr_socket}")))
        dev_pdu_power[pdu_host, pwr_socket] = (w, s)
    if not dev_pdu_power:
        print_no_connection(device)
    else:
        dev_total_pwr = 0
        for w, _ in dev_pdu_power.values():
            dev_total_pwr += w
        dev = (device, dev_pdu_power, dev_total_pwr)
        if dev_total_pwr > max_power:
            power_hungry_devices.append(dev)
        else:
            good_devices.append(dev)

if verbose:
    print()
    print("Good:")
    for dev in good_devices:
        print_device(*dev)
    print()
    print("Powerhungry:")
for dev in power_hungry_devices:
    print_device(*dev)

sys.exit(int(len(power_hungry_devices) > 0))
