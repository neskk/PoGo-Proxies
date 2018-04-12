#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

from bs4 import BeautifulSoup

from ..proxy_scrapper import ProxyScrapper

log = logging.getLogger(__name__)


class Socksproxy(ProxyScrapper):

    def __init__(self, args):
        super(Socksproxy, self).__init__(args, 'socksproxy-net')
        self.base_url = 'https://socks-proxy.net'

    def scrap(self):
        self.setup_session()
        proxylist = []

        html = self.request_url(self.base_url)
        if html is None:
            log.error('Failed to download webpage: %s', self.base_url)
            return proxylist

        log.info('Parsing proxylist from webpage: %s', self.base_url)
        soup = BeautifulSoup(html, 'html.parser')
        proxies = self.parse_webpage(soup)

        if not proxies:
            log.error('Scrapping aborted, found no proxies in main page: %s',
                      self.base_url)
            return proxylist

        proxylist.extend(proxies)

        self.session.close()
        return proxylist

    def parse_webpage(self, soup):
        proxylist = []

        # This table doesn't have any additional css or attributes to
        # separate columns, so we'll need to rely on indexes:
        # 0: IP Address
        # 1: Port
        # 2: Code
        # 3: Country
        # 4: Version
        # 5: Anonymity
        # 6: Https
        # 7: Last Checked
        table = soup.find('table', attrs={'id': 'proxylisttable'})

        # Go through each row and pull out the information wanted.
        for row in table.findAll('tr'):

            # Only use the rows that are in the table body.
            if row.parent.name != 'tbody':
                continue

            # Get the columns and make sure we have enough.
            columns = row.findAll('td')
            if len(columns) != 8:
                log.error('Scrapping aborted, not enough columns in: %s',
                          self.base_url)
                return proxylist

            # Extract country and check against ignored countries.
            country = columns[3].get_text().lower()
            if not self.accepted_country(country):
                continue

            # Ignore transparent proxies
            anonymity = columns[5].get_text().lower()
            if anonymity == 'transparent':
                continue

            # Extract Protocol/IP/Port.
            protocol = columns[4].get_text().lower()
            ip = columns[0].get_text()
            port = columns[1].get_text()

            proxy_url = '{}://{}:{}'.format(protocol, ip, port)
            proxylist.append(proxy_url)

        log.info('Parsed %d http proxies from webpage.', len(proxylist))
        return proxylist
