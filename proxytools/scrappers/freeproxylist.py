#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

from bs4 import BeautifulSoup

from ..proxy_scrapper import ProxyScrapper

log = logging.getLogger(__name__)


class Freeproxylist(ProxyScrapper):

    def __init__(self, args):
        super(Freeproxylist, self).__init__(args, 'freeproxylist-net')
        self.base_url = 'https://free-proxy-list.net'

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

        table_rows = soup.find_all('tr')
        for row in table_rows:
            columns = row.find_all('td')
            if len(columns) != 8:
                continue
            ip = columns[0].get_text().strip()
            port = columns[1].get_text().strip()
            country = columns[3].get_text().strip().lower()
            status = columns[4].get_text().strip().lower()

            ignore = False
            for ignore_country in self.ignore_country:
                if ignore_country in country:
                    ignore = True
                    break

            if ignore:
                continue

            if status == 'transparent':
                continue

            proxy_url = 'http://{}:{}'.format(ip, port)
            proxylist.append(proxy_url)

        if self.debug and not proxylist:
            self.export_webpage(soup, self.name + '.html')

        log.info('Parsed %d http proxies from webpage.', len(proxylist))
        return proxylist
