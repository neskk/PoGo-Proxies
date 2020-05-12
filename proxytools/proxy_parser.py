#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

from .utils import validate_ip
from .models import ProxyProtocol, Proxy

from .scrappers.filereader import FileReader
from .scrappers.freeproxylist import Freeproxylist
from .scrappers.premproxy import Premproxy
from .scrappers.idcloak import Idcloak
from .scrappers.proxyserverlist24 import Proxyserverlist24
from .scrappers.sockslist import Sockslist
from .scrappers.socksproxy import Socksproxy
from .scrappers.socksproxylist24 import Socksproxylist24
from .scrappers.spysone import SpysHTTPS, SpysSOCKS
from .scrappers.vipsocks24 import Vipsocks24

from .scrappers.proxynova import ProxyNova

log = logging.getLogger(__name__)


class ProxyParser(object):

    def __init__(self, args, protocol=None):
        self.debug = args.verbose
        self.download_path = args.download_path
        self.refresh_interval = args.proxy_refresh_interval
        self.protocol = protocol

        # Configure proxy scrappers.
        self.scrappers = []

    def __parse_proxylist(self, proxylist):
        result = {}

        for proxy in proxylist:
            # Strip spaces from proxy string.
            proxy = proxy.strip()
            if len(proxy) < 9:
                log.debug('Invalid proxy address: %s', proxy)
                continue

            parsed = {
                'hash': None,
                'ip': None,
                'port': None,
                'protocol': self.protocol,
                'username': None,
                'password': None
            }

            # Check and separate protocol from proxy address.
            if '://' in proxy:
                pieces = proxy.split('://')
                proxy = pieces[1]
                if pieces[0] == 'http':
                    parsed['protocol'] = ProxyProtocol.HTTP
                elif pieces[0] == 'socks4':
                    parsed['protocol'] = ProxyProtocol.SOCKS4
                elif pieces[0] == 'socks5':
                    parsed['protocol'] = ProxyProtocol.SOCKS5
                else:
                    log.error('Unknown proxy protocol in: %s', proxy)
                    continue

            if parsed['protocol'] is None:
                log.error('Proxy protocol is not set for: %s', proxy)
                continue

            # Check and separate authentication from proxy address.
            if '@' in proxy:
                pieces = proxy.split('@')
                if ':' not in pieces[0]:
                    log.error('Unknown authentication format in: %s', proxy)
                    continue
                auth = pieces[0].split(':')

                parsed['username'] = auth[0]
                parsed['password'] = auth[1]
                proxy = pieces[1]

            # Check and separate IP and port from proxy address.
            if ':' not in proxy:
                log.error('Proxy address port not specified in: %s', proxy)
                continue

            pieces = proxy.split(':')

            if not validate_ip(pieces[0]):
                log.error('IP address is not valid in: %s', proxy)
                continue

            parsed['ip'] = pieces[0]
            parsed['port'] = pieces[1]
            parsed['hash'] = Proxy.generate_hash(parsed)

            result[parsed['hash']] = parsed

        log.info('Successfully parsed %d proxies.', len(result))
        return result

    def load_proxylist(self):
        if not self.scrappers:
            return

        proxylist = set()

        for scrapper in self.scrappers:
            try:
                proxylist.update(scrapper.scrap())
            except Exception as e:
                log.exception('%s proxy scrapper failed: %s',
                              type(scrapper).__name__, e)

        log.info('%s scrapped a total of %d proxies.',
                 type(self).__name__, len(proxylist))
        proxylist = self.__parse_proxylist(proxylist)
        Proxy.insert_new(list(proxylist.values()))


class MixedParser(ProxyParser):

    def __init__(self, args):
        super(MixedParser, self).__init__(args)
        if args.proxy_file:
            self.scrappers.append(FileReader(args))


class HTTPParser(ProxyParser):

    def __init__(self, args):
        super(HTTPParser, self).__init__(args, ProxyProtocol.HTTP)
        self.scrappers.append(Freeproxylist(args))
        self.scrappers.append(Premproxy(args))
        self.scrappers.append(Proxyserverlist24(args))
        self.scrappers.append(SpysHTTPS(args))
        self.scrappers.append(ProxyNova(args))
        # self.scrappers.append(Idcloak(args))  # OFFLINE


class SOCKSParser(ProxyParser):

    def __init__(self, args):
        super(SOCKSParser, self).__init__(args, ProxyProtocol.SOCKS5)
        self.scrappers.append(Sockslist(args))
        self.scrappers.append(Socksproxy(args))
        self.scrappers.append(SpysSOCKS(args))
        self.scrappers.append(Vipsocks24(args))
        # self.scrappers.append(Socksproxylist24(args))  # Duplicate of VipSocks24
