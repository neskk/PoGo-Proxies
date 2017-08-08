#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys
import logging

from proxytools.proxy_tester import check_proxies
from proxytools.proxy_scrapper import scrap_sockslist_net, scrap_vipsocks24_net
from proxytools import utils

logging.getLogger(
    'requests.packages.urllib3.connectionpool').setLevel(logging.CRITICAL)
logging.basicConfig(
    format='%(asctime)s [%(threadName)15.15s][%(levelname)8.8s] %(message)s',
    level=logging.INFO)
log = logging.getLogger('pogo-proxies')


def work_cycle(args):
    proxies = set()
    if args.proxy_file:
        log.info('Loading proxies from file: %s', args.proxy_file)
        proxylist = utils.load_proxies(args.proxy_file)

        if len(proxylist) > 0:
            proxies.update(proxylist)
        else:
            log.error('Proxy file was configured but no proxies were loaded.')
            sys.exit(1)
    else:
        log.info('No proxy file supplied. Scrapping proxy list from the web.')

        proxies.update(scrap_sockslist_net(args.ignore_country))
        proxies.update(scrap_vipsocks24_net())

    proxies = list(proxies)
    if args.batch_size > 0:
        chunks = [proxies[x:x+args.batch_size]
                  for x in xrange(0, len(proxies), args.batch_size)]
        working_proxies = []
        for chunk in chunks:
            working_proxies.extend(check_proxies(args, chunk))
            output(args, working_proxies)
    else:
        working_proxies = check_proxies(args, proxies)
        output(args, working_proxies)


def output(args, proxies):
    output_file = args.output_file
    log.info('Writing %d working proxies to: %s',
             len(proxies), output_file)

    if args.proxychains:
        utils.export_proxychains(output_file, proxies)
    elif args.kinancity:
        utils.export_kinancity(output_file, proxies)
    else:
        utils.export(output_file, proxies)


if __name__ == '__main__':
    log.setLevel(logging.INFO)

    args = utils.get_args()
    working_proxies = []

    if args.verbose:
        log.setLevel(logging.DEBUG)
        log.debug('Running in verbose mode (-v).')

    work_cycle(args)

    sys.exit(0)
