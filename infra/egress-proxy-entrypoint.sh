#!/bin/sh
set -eu

api_ip="$(getent ahostsv4 api | awk 'NR == 1 { print $1 }')"

iptables -P OUTPUT DROP
iptables -A OUTPUT -o lo -j ACCEPT
iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m owner --uid-owner 101 -p udp --dport 53 -j ACCEPT
iptables -A OUTPUT -m owner --uid-owner 101 -p tcp -d "$api_ip" --dport 8000 -j ACCEPT
iptables -A OUTPUT -m owner --uid-owner 65532 -p udp --dport 53 -j ACCEPT
iptables -A OUTPUT -m owner --uid-owner 65532 -p tcp --dport 443 -j ACCEPT

exec su-exec 65532:65532 python /app/egress_proxy.py
