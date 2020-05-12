#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import re

from bs4 import BeautifulSoup

from ..crazyxor import parse_crazyxor, decode_crazyxor
from ..proxy_scrapper import ProxyScrapper
from ..utils import validate_ip

log = logging.getLogger(__name__)


# Sockslist.net uses javascript to obfuscate proxies port number.
class Sockslist(ProxyScrapper):

    def __init__(self, args):
        super(Sockslist, self).__init__(args, 'sockslist-net')
        self.base_url = 'https://sockslist.net'
        self.urls = (
            'https://sockslist.net/list/proxy-socks-5-list#proxylist',
            'https://sockslist.net/list/proxy-socks-5-list/2#proxylist',
            'https://sockslist.net/list/proxy-socks-5-list/3#proxylist'
        )

    def scrap(self):
        self.setup_session()
        proxylist = []
        for url in self.urls:
            html = self.request_url(url, self.base_url)
            if html is None:
                log.error('Failed to download webpage: %s', url)
                continue

            log.info('Parsing proxylist from webpage: %s', url)
            proxies = self.parse_webpage(html)
            if not proxies:
                break

            proxylist.extend(proxies)

        self.session.close()
        return proxylist

    def parse_webpage(self, html):
        proxylist = []
        encoding = {}
        soup = BeautifulSoup(html, 'html.parser')

        for script in soup.find_all('script'):
            code = script.string
            if not code:
                continue
            for line in code.split('\n'):
                if '^' in line and ';' in line and ' = ' in line:
                    line = line.strip()
                    log.info('Found crazy XOR decoding secret code.')
                    encoding = parse_crazyxor(line)
                    log.debug('Crazy XOR decoding dictionary: %s', encoding)

        if not encoding:
            log.error('Unable to find crazy XOR decoding secret code.')

            if self.debug:
                self.export_webpage(soup, self.name + '.html')

            return proxylist

        table = soup.find('table', class_='proxytbl')
        if table is None:
            log.error('Unable to find table with proxy list.')

            if self.debug:
                self.export_webpage(soup, self.name + '.html')

            return proxylist

        pattern = re.compile(r"document.write\(([\w\^]+)\)")
        for table_row in table.find_all('tr'):
            ip_td = table_row.find('td', class_='t_ip')
            if ip_td is None:
                continue
            ip = ip_td.get_text()

            if not validate_ip(ip):
                log.warning('Invalid IP found: %s', ip)
                continue

            port_td = table_row.find('td', class_='t_port')
            port_script = port_td.find('script').string
            try:
                # Find encoded string with proxy port.
                m = pattern.search(port_script)
                # Decode proxy port using secret encoding dictionary.
                port = decode_crazyxor(encoding, m.group(1))
                if not port.isdigit():
                    log.error('Unable to find proxy port number.')
                    continue

            except Exception as e:
                log.error('Unable to parse proxy port: %s', e)
                continue

            country = table_row.find('td', class_='t_country').get_text()
            if not self.validate_country(country):
                continue

            proxylist.append('{}:{}'.format(ip, port))

        if self.debug and not proxylist:
            self.export_webpage(soup, self.name + '.html')

        log.info('Parsed %d socks5 proxies from webpage.', len(proxylist))
        return proxylist
