#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys
import logging
import time

from proxytools.proxy_tester import load_proxies, check_proxies
from proxytools.proxy_scrapper import scrap_sockslist_net, scrap_vipsocks24_net
from proxytools.utils import get_args

logging.getLogger(
    'requests.packages.urllib3.connectionpool').setLevel(logging.CRITICAL)
logging.basicConfig(
    format='%(asctime)s [%(threadName)15.15s][%(levelname)8.8s] %(message)s',
    level=logging.INFO)
log = logging.getLogger(__name__)


def export_proxies(filename, proxies):
    with open(filename, 'w') as file:
        file.truncate()
        for proxy in proxies:
            file.write(proxy + '\n')


def export_proxies_proxychains(filename, proxies):
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


def export_proxies_kinan(filename, proxies):
    with open(filename, 'w') as file:
        file.truncate()
        file.write('[')
        for proxy in proxies:
            file.write(proxy + ',')

        file.seek(-1, 1)
        file.write(']\n')


def work_cycle(args):
    proxies = set()
    if args.proxy_file:
        log.info('Loading proxies from file: %s', args.proxy_file)
        proxylist = load_proxies(args.proxy_file)

        if len(proxylist) > 0:
            proxies.update(proxylist)
        else:
            log.error('Proxy file was configured but no proxies were loaded.')
            sys.exit(1)
    else:
        log.info('No proxy file supplied. Scrapping proxy list from the web.')

        proxies.update(scrap_sockslist_net(args.ignore_country))
        proxies.update(scrap_vipsocks24_net())

    working_proxies = check_proxies(args, proxies)

    output_file = args.output_file
    log.info('Writing %d working proxies to: %s',
             len(working_proxies), output_file)

    if args.proxychains:
        export_proxies_proxychains(output_file, working_proxies)
    elif args.kinan:
        export_proxies_kinan(output_file, working_proxies)
    else:
        export_proxies(output_file, working_proxies)


if __name__ == '__main__':
    log.setLevel(logging.INFO)

    args = get_args()
    working_proxies = []

    if args.verbose:
        log.setLevel(logging.DEBUG)
        log.debug('Running in verbose mode (-v).')

    # Run periodical proxy refresh thread.
    if args.restart_work > 0:
        while True:
            work_cycle(args)
            time.sleep(args.restart_work)
    else:
        work_cycle(args)

    sys.exit(0)
