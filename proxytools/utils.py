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
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('-f', '--proxy-file',
                        help='Filename of proxy list to verify.')
    source.add_argument('-s', '--scrap',
                        help='Scrap webpages for proxy lists.',
                        default=False,
                        action='store_true')
    parser.add_argument('-m', '--mode',
                        help=('Specify which proxy mode to use for testing. ' +
                              'Default is "socks".'),
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
    parser.add_argument('-pj', '--proxy-judge',
                        help='URL for AZenv script used to test proxies.',
                        default='http://pascal.hoez.free.fr/azenv.php')
    parser.add_argument('-na', '--no-anonymous',
                        help='Disable anonymous proxy test.',
                        default=False,
                        action='store_true')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('-nt', '--no-test',
                      help='Disable PTC/Niantic proxy test.',
                      default=False,
                      action='store_true')
    mode.add_argument('-er', '--extra-request',
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
                        default=100,
                        type=int)
    parser.add_argument('-bs', '--batch-size',
                        help='Check proxies in batches of limited size.',
                        default=300,
                        type=int)
    parser.add_argument('-l', '--limit',
                        help='Stop tests when we have enough good proxies.',
                        default=100,
                        type=int)
    parser.add_argument('-ic', '--ignore-country',
                        help='Ignore proxies from countries in this list.',
                        action='append', default=['china'])
    output = parser.add_mutually_exclusive_group()
    output.add_argument('--proxychains',
                        help='Output in proxychains-ng format.',
                        default=False,
                        action='store_true')
    output.add_argument('--kinancity',
                        help='Output in Kinan City format.',
                        default=False,
                        action='store_true')
    output.add_argument('--clean',
                        help='Output proxy list without protocol.',
                        default=False,
                        action='store_true')
    args = parser.parse_args()

    if not args.proxy_file and not args.scrap:
        log.error('You must supply a proxylist file or enable scrapping.')
        exit(1)

    if not args.proxy_judge:
        log.error('You must specify a URL for an AZenv proxy judge.')
        exit(1)

    return args


# Load proxies and return a list.
def load_proxies(filename, mode):
    proxies = []
    protocol = ''
    if mode == 'socks':
        protocol = 'socks5://'
    else:
        protocol = 'http://'

    # Load proxies from the file. Override args.proxy if specified.
    with open(filename) as f:
        for line in f:
            stripped = line.strip()

            # Ignore blank lines and comment lines.
            if len(stripped) == 0 or line.startswith('#'):
                continue

            if '://' in stripped:
                proxies.append(stripped)
            else:
                proxies.append(protocol + stripped)

        log.info('Loaded %d proxies.', len(proxies))

    return proxies


def export(filename, proxies, clean=False):
    with open(filename, 'w') as file:
        file.truncate()
        for proxy in proxies:
            if clean:
                proxy = proxy.split('://', 2)[1]

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
