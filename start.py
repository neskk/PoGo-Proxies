#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import os
import sys
import time

from timeit import default_timer

from proxytools import utils
from proxytools.proxy_tester import ProxyTester
from proxytools.proxy_parser import ProxyParser
from proxytools.models import init_database, Proxy

log = logging.getLogger()


class LogFilter(logging.Filter):

    def __init__(self, level):
        self.level = level

    def filter(self, record):
        return record.levelno < self.level


def setup_workspace(args):
    if not os.path.exists(args.log_path):
        # Create directory for log files.
        os.mkdir(args.log_path)

    if not os.path.exists(args.download_path):
        # Create directory for downloaded files.
        os.mkdir(args.download_path)


def configure_logging(args, log):
    date = time.strftime('%Y%m%d_%H%M')
    filename = os.path.join(args.log_path, '{}-pogo-proxies.log'.format(date))
    filelog = logging.FileHandler(filename)
    formatter = logging.Formatter(
        '%(asctime)s [%(threadName)18s][%(module)20s][%(levelname)8s] '
        '%(message)s')
    filelog.setFormatter(formatter)
    log.addHandler(filelog)

    if args.verbose:
        log.setLevel(logging.DEBUG)
        log.debug('Running in verbose mode (-v).')
    else:
        log.setLevel(logging.INFO)

    logging.getLogger('peewee').setLevel(logging.INFO)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.ERROR)

    # Redirect messages lower than WARNING to stdout
    stdout_hdlr = logging.StreamHandler(sys.stdout)
    stdout_hdlr.setFormatter(formatter)
    log_filter = LogFilter(logging.WARNING)
    stdout_hdlr.addFilter(log_filter)
    stdout_hdlr.setLevel(5)

    # Redirect messages equal or higher than WARNING to stderr
    stderr_hdlr = logging.StreamHandler(sys.stderr)
    stderr_hdlr.setFormatter(formatter)
    stderr_hdlr.setLevel(logging.WARNING)

    log.addHandler(stdout_hdlr)
    log.addHandler(stderr_hdlr)


def check_configuration(args):
    if not args.proxy_file and not args.proxy_scrap:
        log.error('You must supply a proxylist file or enable scrapping.')
        sys.exit(1)

    if not args.proxy_judge:
        log.error('You must specify a URL for an AZenv proxy judge.')
        sys.exit(1)

    if args.tester_max_concurrency <= 0:
        log.error('Proxy tester max concurrency must be greater than zero.')
        sys.exit(1)

    if args.tester_count <= 0:
        log.error('Proxy tester thread count must be greater than zero.')
        sys.exit(1)

    args.local_ip = None
    if not args.tester_disable_anonymity:
        local_ip = utils.get_local_ip(args.proxy_judge)

        if not local_ip:
            log.error('Failed to identify local IP address.')
            sys.exit(1)

        log.info('External IP address found: %s', local_ip)
        args.local_ip = local_ip

    if args.proxy_refresh_interval < 15:
        log.warning('Checking proxy sources every %d minutes is inefficient.',
                    args.proxy_refresh_interval)
        args.proxy_refresh_interval = 15
        log.warning('Proxy refresh interval overriden to 15 minutes.')

    args.proxy_refresh_interval *= 60

    if args.output_interval < 15:
        log.warning('Outputting proxylist every %d minutes is inefficient.',
                    args.output_interval)
        args.output_interval = 15
        log.warning('Proxylist output interval overriden to 15 minutes.')

    args.output_interval *= 60


def work(tester, parser):
    # Fetch and insert new proxies from configured sources.
    proxy_parser.load_proxylist()

    refresh_timer = default_timer()
    output_timer = default_timer()

    while True:
        now = default_timer()
        if now > refresh_timer + args.proxy_refresh_interval:
            refresh_timer = now
            log.info('Refreshing proxylists configured from sources.')
            proxy_parser.load_proxylist()

            # Remove failed proxies from database.
            Proxy.clean_failed()

        if now > output_timer + args.output_interval:
            output_timer = now
            output(args)

        time.sleep(60)


def output(args):
    log.info('Outputting working proxylist.')
    proxylist = Proxy.get_valid(
        args.output_limit, args.tester_disable_anonymity)
    if not proxylist:
        log.warning('Found no valid proxies in database.')
        return

    log.info('Writing %d working proxylist to: %s',
             len(proxylist), args.output_file)

    if args.output_proxychains:
        proxylist = [Proxy.url_format_proxychains(proxy)
                     for proxy in proxylist]
    else:
        proxylist = [Proxy.url_format(proxy, args.output_no_protocol)
                     for proxy in proxylist]

    if args.output_kinancity:
        proxylist = '[' + ','.join(proxylist) + ']'

    utils.export_file(args.output_file, proxylist)


if __name__ == '__main__':

    args = utils.get_args()

    setup_workspace(args)
    configure_logging(args, log)
    check_configuration(args)
    init_database(
        args.db_name, args.db_host, args.db_port, args.db_user, args.db_pass)

    proxy_tester = ProxyTester(args)
    proxy_parser = ProxyParser(args)

    try:
        work(proxy_tester, proxy_parser)
    except KeyboardInterrupt:
        log.info('Shutting down...')
        output(args)

        proxy_tester.running.set()
        log.info('Waiting for proxy tester to shutdown...')

    sys.exit(0)
