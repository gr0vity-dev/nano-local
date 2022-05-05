#!/bin/env python3

import lmdb
import binascii
import ipaddress
import argparse


def parse_endpoint(string, default_port=None):
    # IPv6 with port
    if string[0] == '[':
        ip_end_index = string.index(']')
        ip_address = string[1:ip_end_index]
        port = int(string[ip_end_index + 2:])

    # IPv6 without port
    elif string.count(':') > 1:
        ip_address = string
        port = default_port

    #IPv4
    else:
        details = string.split(':')

        if len(details) == 1:
            # Without port
            ip_address = string

            # Checking if it is a domain name or not
            if not non_digits_in_ip(ip_address):
                ip_address = '::FFFF:' + ip_address

            port = default_port
        else:
            # With port
            ip_address = details[0]

            # If there are non digit characters in the ip address it is a domain (not including '.')
            # Otherwise there are only digits and it is an IPv4
            if not non_digits_in_ip(ip_address):
                ip_address = '::FFFF:' + ip_address

            port = int(details[1])

    return ip_address, port


def non_digits_in_ip(string):
    for s in string:
        if s == '.':
            continue
        elif not s.isdigit():
            return True
    return False

class ip_addr:
    def __init__(self, ipv6 = ipaddress.IPv6Address(0)):
        if isinstance(ipv6, str):
            self.ipv6 = ipaddress.IPv6Address(ipv6)
        else:
            self.ipv6 = ipv6
        assert isinstance(self.ipv6, ipaddress.IPv6Address)

    @classmethod
    def from_string(cls, ipstr):
        assert isinstance(ipstr, str)
        a = ipaddress.ip_address(ipstr)
        if a.version == 4:
            ipstr = '::ffff:' + str(a)
        ipv6 = ipaddress.IPv6Address(ipstr)
        return ip_addr(ipv6)

    def serialise(self):
        return self.ipv6.packed

    def is_ipv4(self):
        return self.ipv6.ipv4_mapped is not None

    def __str__(self):
        if self.ipv6.ipv4_mapped:
            return '::ffff:' + str(self.ipv6.ipv4_mapped)
        return str(self.ipv6)

    def __eq__(self, other):
        if not isinstance(other, ip_addr):
            return False
        return self.ipv6 == other.ipv6

    def __hash__(self):
        return hash(self.ipv6)

class PeersTable:
    def __init__(self, filename):
        self.filename = filename


    def print_peers(self):
        with lmdb.open(self.filename, subdir=False, max_dbs=10000, map_size=10*1000*1000*1000) as env:
            peers_db = env.open_db(b'peers')
            with env.begin() as tx:
                for key, value in tx.cursor(db=peers_db):
                    print(PeersTable.parse_entry(key))


    def delete_peers(self):
        with lmdb.open(self.filename, subdir=False, max_dbs=10000, map_size=10*1000*1000*1000) as env:
            peers_db = env.open_db(b'peers')
            with env.begin(write=True) as tx:
                peers = []
                for key, value in tx.cursor(db=peers_db):
                    peers.append(key)
                for peer in peers:
                    print('Deleting peer %s' % PeersTable.parse_entry(peer))
                    tx.delete(peer, db=peers_db)


    def add_peer(self, peer_str):
        assert peer_str is not None
        ipaddr_str, port = parse_endpoint(peer_str, default_port=7075)
        data = ip_addr(ipaddr_str).serialise() + port.to_bytes(2, "big")
        assert len(data) == 18

        with lmdb.open(self.filename, subdir=False, max_dbs=10000, map_size=10*1000*1000*1000) as env:
            peers_db = env.open_db(b'peers')
            print('Adding peer [%s]:%s' % (ipaddr_str, port))
            with env.begin(write=True) as tx:
                with tx.cursor(db=peers_db) as curs:
                    rc = curs.put(data, b'')
                    assert rc


    def delete_peer(self, peer_str):
        assert peer_str is not None
        ipaddr_str, port = parse_endpoint(peer_str, default_port=7075)
        data = ip_addr(ipaddr_str).serialise() + port.to_bytes(2, "big")
        assert len(data) == 18

        with lmdb.open(self.filename, subdir=False, max_dbs=10000, map_size=10*1000*1000*1000) as env:
            peers_db = env.open_db(b'peers')
            with env.begin(write=True) as tx:
                peer = None
                for key, value in tx.cursor(db=peers_db):
                    if key == data:
                        peer = key
                        break
                if peer is not None:
                    print('Deleting peer %s' % PeersTable.parse_entry(peer))
                    tx.delete(peer, db=peers_db)
                else:
                    print('Cannot find peer %s to delete' % PeersTable.parse_entry(data))


    def parse_entry(data):
        assert len(data) == 18
        ipv6 = ipaddress.IPv6Address(data[:-2])
        port = int.from_bytes(data[-2:], "big")
        ipstr = str(ipv6)
        if ipv6.ipv4_mapped:
            ipstr = '::ffff:' + str(ipv6.ipv4_mapped)
        return '[%s]:%s' % (ipstr, port)
    
    


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--dataldb', default='data.ldb',
                        help='data.ldb path')
    parser.add_argument('-p', '--peer',
                        help='peer to add or delete')
    parser.add_argument('command',
            help='print, add, delete or delall')
    return parser.parse_args()


def main():
    args = parse_args()

    peers_table = PeersTable(args.dataldb)

    if args.command == 'print':
        peers_table.print_peers()
    elif args.command == 'delall':
        peers_table.delete_peers()
    elif args.command == 'add':
        peers_table.add_peer(args.peer)
    elif args.command == 'delete':
        peers_table.delete_peer(args.peer)
    else:
        print('Unknown command %s', args.command)


if __name__ == "__main__":
    main()