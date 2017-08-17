#!/usr/bin/python
# -*- coding: utf-8 -*-

import argparse
import logging

log = logging.getLogger('pogo-proxies')


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose',
                        help='Run in the verbose mode.',
                        action='store_true')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('-f', '--proxy-file',
                        help='Filename of proxy list to verify.')
    source.add_argument('-s', '--scrap',
                        help='Specify which proxy type to scrap.',
                        default='socks',
                        choices=('http', 'socks'))
    parser.add_argument('-o', '--output-file',
                        help='Output filename for working proxies.',
                        default='working_proxies.txt')
    parser.add_argument('-r', '--retries',
                        help='Number of attempts to check each proxy.',
                        default=5,
                        type=int)
    parser.add_argument('-t', '--timeout',
                        help='Connection timeout. Default is 5 seconds.',
                        default=5,
                        type=float)
    parser.add_argument('-er', '--extra-request',
                        help='Make an extra request to validate PTC.',
                        default=False,
                        action='store_true')
    parser.add_argument('-bf', '--backoff-factor',
                        help=('Factor (in seconds) by which the delay ' +
                              'until next retry will increase.'),
                        default=0.25,
                        type=float)
    parser.add_argument('-mc', '--max-concurrency',
                        help='Maximum concurrent proxy testing requests.',
                        default=50,
                        type=int)
    parser.add_argument('-bs', '--batch-size',
                        help='Check proxies in batches of limited size.',
                        default=200,
                        type=int)
    parser.add_argument('-ic', '--ignore-country',
                        help='Ignore proxies from countries in this list.',
                        action='append', default=['china'])
    parser.add_argument('--proxychains',
                        help='Output in proxychains-ng format.',
                        action='store_true')
    parser.add_argument('--kinancity',
                        help='Output in Kinan City format.',
                        action='store_true')
    args = parser.parse_args()

    return args


# Load proxies and return a list.
def load_proxies(filename):
    proxies = []

    # Load proxies from the file. Override args.proxy if specified.
    with open(filename) as f:
        for line in f:
            stripped = line.strip()

            # Ignore blank lines and comment lines.
            if len(stripped) == 0 or line.startswith('#'):
                continue

            proxies.append(stripped)

        log.info('Loaded %d proxies.', len(proxies))

    return proxies


def export(filename, proxies):
    with open(filename, 'w') as file:
        file.truncate()
        for proxy in proxies:
            file.write(proxy + '\n')


def export_proxychains(filename, proxies):
    with open(filename, 'w') as file:
        file.truncate()
        for proxy in proxies:
            # Split the protocol
            protocol, address = proxy.split('://', 2)
            # address = proxy.split('://')[1]
            # Split the port
            ip, port = address.split(':', 2)
            # Write to file
            file.write(protocol + ' ' + ip + ' ' + port + '\n')


def export_kinancity(filename, proxies):
    with open(filename, 'w') as file:
        file.truncate()
        file.write('[')
        for proxy in proxies:
            file.write(proxy + ',')

        file.seek(-1, 1)
        file.write(']\n')


def validate_ip(ip):
    try:
        parts = ip.split('.')
        return len(parts) == 4 and all(0 <= int(part) < 256 for part in parts)
    except ValueError:
        # one of the 'parts' not convertible to integer.
        log.warning('Bad IP: %s', ip)
        return False
    except (AttributeError, TypeError):
        # `ip` isn't even a string
        log.warning('Weird IP: %s', ip)
        return False
