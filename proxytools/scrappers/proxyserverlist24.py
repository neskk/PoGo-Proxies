#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

from bs4 import BeautifulSoup

from ..proxy_scrapper import ProxyScrapper

log = logging.getLogger(__name__)


class Proxyserverlist24(ProxyScrapper):

    def __init__(self, args):
        super(Proxyserverlist24, self).__init__(args, 'proxyserverlist24-top')
        self.base_url = 'http://www.proxyserverlist24.top/'

    def scrap(self):
        self.setup_session()
        proxylist = []
        html = self.request_url(self.base_url)

        if html is None:
            log.error('Failed to download webpage: %s', self.base_url)
        else:
            log.info('Parsing links from webpage: %s', self.base_url)
            urls = self.parse_links(html)

            for url in urls:
                html = self.request_url(url, self.base_url)
                if html is None:
                    log.error('Failed to download webpage: %s', url)
                    continue

                log.info('Parsing proxylist from webpage: %s', url)
                proxylist.extend(self.parse_webpage(html))

        self.session.close()
        return proxylist

    def parse_links(self, html):
        urls = []
        soup = BeautifulSoup(html, 'html.parser')

        for post_title in soup.find_all('h3', class_='post-title entry-title'):
            url = post_title.find('a')
            if url is None:
                continue

            if 'Proxy Server' in url.get_text():
                url = url.get('href')
                log.debug('Found potential proxy list in: %s', url)
                urls.append(url)

        if self.debug and not urls:
            self.export_webpage(soup, self.name + '.html')

        log.info('Parsed %d links from webpage.', len(urls))
        return urls

    def parse_webpage(self, html):
        proxylist = []
        soup = BeautifulSoup(html, 'html.parser')

        container = soup.find('pre', attrs={'class': 'alt2', 'dir': 'ltr'})
        if not container:
            log.error('Unable to find element with proxy list.')

            if self.debug:
                self.export_webpage(soup, self.name + '.html')

            return proxylist

        spans = container.find_all('span')
        if not spans or len(spans) < 3:
            log.error('Unable to find element with proxy list.')

            if self.debug:
                self.export_webpage(soup, self.name + '.html')

            return proxylist

        proxylist = spans[2].get_text().split('\n')

        if self.debug and not proxylist:
            self.export_webpage(soup, self.name + '.html')

        log.info('Parsed %d http proxies from webpage.', len(proxylist))
        return proxylist
