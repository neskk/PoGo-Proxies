#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import re

from bs4 import BeautifulSoup

from ..proxy_scrapper import ProxyScrapper
from ..utils import validate_ip

log = logging.getLogger(__name__)


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
        proxylist = []
        for url in self.urls:
            html = self.request_url(url, self.base_url)
            if html is None:
                log.error('Failed to download webpage: %s', url)
                continue

            log.info('Parsing webpage from: %s', url)
            proxylist.extend(self.parse_webpage(html))

        return proxylist

    def parse_webpage(self, html):
        proxylist = []
        encoding = {}
        soup = BeautifulSoup(html, 'html.parser')
        # soup.prettify()

        for script in soup.find_all('script'):
            code = script.get_text()
            for line in code.split('\n'):
                if '^' in line and ';' in line and ' = ' in line:
                    line = line.strip()
                    log.info('Found crazy XOR decoding secret code.')
                    encoding = parse_crazy_encoding(line)
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

        for table_row in table.find_all('tr'):
            ip_td = table_row.find('td', class_='t_ip')
            if ip_td is None:
                continue
            ip = ip_td.get_text()

            if not validate_ip(ip):
                log.warning('Invalid IP found: %s', ip)
                continue

            port_text = table_row.find('td', class_='t_port').get_text()
            try:
                # Find encoded string with proxy port.
                m = re.search('(?<=document.write\()([\w\d\^]+)\)', port_text)
                # Decode proxy port using secret encoding dictionary.
                port = crazy_decode(encoding, m.group(1))
                if not port.isdigit():
                    log.error('Unable to find proxy port number.')
                    continue

            except Exception as e:
                log.error('Unable to parse proxy port: %s', repr(e))
                continue

            country = table_row.find('td', class_='t_country').get_text()

            if country in self.ignore_country:
                continue

            proxylist.append('{}:{}'.format(ip, port))

        if self.debug and not proxylist:
            self.export_webpage(soup, self.name + '.html')

        log.info('Parsed %d socks5 proxies from webpage.', len(proxylist))
        return proxylist


# Sockslist.net uses javascript to obfuscate proxies port number.
# Builds a dictionary with decoded values for each variable.
# Dictionary = {'var': intValue, ...})
def parse_crazy_encoding(code):
    dictionary = {}
    variables = code.split(';')
    for var in variables:
        if '=' in var:
            assignment = var.split(' = ')
            dictionary[assignment[0]] = assignment[1]

    for var in dictionary:
        recursive_decode(dictionary, var)
    return dictionary


def recursive_decode(dictionary, var):
    if var.isdigit():
        return var

    value = dictionary[var]
    if value.isdigit():
        return value
    elif '^' in value:
        l_value, r_value = value.split('^')
        answer = str(int(recursive_decode(dictionary, l_value)) ^
                     int(recursive_decode(dictionary, r_value)))
        dictionary[var] = answer
        return answer


def crazy_decode(dictionary, code):
    if code.isdigit():
        return code
    value = dictionary.get(code, False)
    if value and value.isdigit():
        return value
    elif '^' in code:
        l_value, r_value = code.split('^', 1)
        answer = str(int(crazy_decode(dictionary, l_value)) ^
                     int(crazy_decode(dictionary, r_value)))
        return answer
