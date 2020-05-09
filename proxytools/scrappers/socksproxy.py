#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

from bs4 import BeautifulSoup

from ..proxy_scrapper import ProxyScrapper

log = logging.getLogger(__name__)


class Socksproxy(ProxyScrapper):

    def __init__(self, args):
        super(Socksproxy, self).__init__(args, 'socksproxy-net')
        self.base_url = 'https://www.socks-proxy.net/'

    def scrap(self):
        self.setup_session()
        proxylist = []

        html = self.request_url(self.base_url)
        if html is None:
            log.error('Failed to download webpage: %s', self.base_url)
        else:
            log.info('Parsing proxylist from webpage: %s', self.base_url)

            soup = BeautifulSoup(html, 'html.parser')
            proxylist = self.parse_webpage(soup)

        self.session.close()
        return proxylist

    def parse_webpage(self, soup):
        proxylist = []
        counter = 0

        table = soup.find('table', attrs={'id': 'proxylisttable'})

        if not table:
            log.error('Unable to find proxylist table.')
            return proxylist

        table_rows = table.find_all('tr')
        for row in table_rows:
            columns = row.find_all('td')
            if len(columns) != 8:
                continue

            ip = columns[0].get_text().strip()
            port = columns[1].get_text().strip()
            country = columns[3].get_text().strip().lower()
            version = columns[4].get_text().strip().lower()
            status = columns[5].get_text().strip().lower()
            counter += 1

            if not self.validate_country(country):
                continue

            if version != 'socks5':
                continue

            if status == 'transparent':
                continue

            proxy_url = '{}:{}'.format(ip, port)
            proxylist.append(proxy_url)

        if self.debug and counter == 0:
            self.export_webpage(soup, self.name + '.html')

        log.info('Parsed %d socks5 proxies from webpage (found %d socks4).', len(proxylist), counter)
        return proxylist
