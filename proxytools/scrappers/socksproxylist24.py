#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

from bs4 import BeautifulSoup

from ..proxy_scrapper import ProxyScrapper

log = logging.getLogger(__name__)


class Socksproxylist24(ProxyScrapper):

    def __init__(self, args):
        super(Socksproxylist24, self).__init__(args, 'socksproxylist24-top')
        self.base_url = 'http://www.socksproxylist24.top/'

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

        textarea = soup.find('textarea', onclick='this.focus();this.select()')
        if textarea is None:
            log.error('Unable to find textarea with proxy list.')
        else:
            proxylist = textarea.get_text().split('\n')

        if self.debug and not proxylist:
            self.export_webpage(soup, self.name + '.html')

        log.info('Parsed %d socks5 proxies from webpage.', len(proxylist))
        return proxylist
