#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import random
import time

from bs4 import BeautifulSoup

from ..proxy_scrapper import ProxyScrapper

log = logging.getLogger(__name__)


# idcloak.com does offer SOCKS5 and SOCKS4 but don't appear too often.
# For now we'll just be scrapping the HTTP/HTTPS protocols.
class Idcloak(ProxyScrapper):

    def __init__(self, args):
        super(Idcloak, self).__init__(args, 'idcloak-com')
        self.base_url = 'http://www.idcloak.com/proxylist/proxy-list.html'

    def scrap(self):
        self.setup_session()
        page = 1
        proxylist = []

        proxies, next_page = self.scrap_page(page)
        if not proxies:
            log.error('Scrapping aborted, found no proxies in main page: %s',
                      self.base_url)
            return proxylist

        proxylist.extend(proxies)

        while next_page:
            page = next_page
            log.debug('Waiting a little bit before scrapping next page...')
            time.sleep(random.uniform(2.0, 4.0))
            proxies, next_page = self.scrap_page(page)
            if not proxies:
                log.info('Scrapping finished, transparent proxies ignored.')
                break

            proxylist.extend(proxies)

        self.session.close()
        return proxylist

    def scrap_page(self, page):
        payload = {
            'port[]': 'all',
            'protocol-http': 'true',
            'protocol-https': 'true',
            'anonymity-medium': 'true',
            'anonymity-high': 'true',
            'page': page}

        html = self.request_url(self.base_url, post=payload)
        if html is None:
            log.error('Failed to download webpage: %s, page: %d',
                      self.base_url, page)
        else:
            log.info('Parsing proxylist from webpage: %s, page: %d',
                     self.base_url, page)

            soup = BeautifulSoup(html, 'html.parser')
            proxylist = self.parse_webpage(soup)
            next_page = self.parse_next_page(soup)

        return proxylist, next_page

    def parse_webpage(self, soup):
        proxylist = []

        table = soup.find('table', attrs={'id': 'sort'})
        if not table:
            log.error('Unable to find proxy list table.')
            return proxylist

        table_rows = table.find_all('tr')
        for row in table_rows:
            columns = row.find_all('td')
            if len(columns) != 8:
                continue
            ip = columns[7].get_text().strip()
            port = columns[6].get_text().strip()

            proxy_url = '{}:{}'.format(ip, port)
            proxylist.append(proxy_url)

        if self.debug and not proxylist:
            self.export_webpage(soup, self.name + '.html')

        log.info('Parsed %d http proxies from webpage.', len(proxylist))
        return proxylist

    # idcloak.com does not have a consistent number of additional pages.
    # Check the main page for links to additional pages and extract them.
    def parse_next_page(self, soup):
        page = None

        pagination = soup.find('div', class_='pagination')
        if not pagination:
            log.error('Unable to find pagination list.')
            return page

        # Check if there is an additional page to scrap.
        pages = pagination.findAll('input')
        current = pagination.find('input', class_='this_page')
        current_page = pages.index(current) + 1

        if current_page < len(pages):
            page = current_page + 1

        return page
