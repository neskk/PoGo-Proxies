#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

from bs4 import BeautifulSoup
from zipfile import ZipFile, is_zipfile

from ..proxy_scrapper import ProxyScrapper

log = logging.getLogger(__name__)


class Vipsocks24(ProxyScrapper):

    def __init__(self, args):
        super(Vipsocks24, self).__init__(args, 'vipsocks24-net')
        self.base_url = 'http://vipsocks24.net/'

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
            # XXX: deprecated check, webpage has changed format.
            log.debug('Unable to find textarea with proxy list.')
            download_button = soup.find('img', alt='Download')
            if download_button is None or download_button.parent.name != 'a':
                log.error('Unable to find download button for proxy list.')
            else:
                download_url = download_button.parent.get('href')

                log.info('Downloading proxylist from: %s', download_url)
                proxylist = self.download_proxylist(download_url)
        else:
            proxylist = textarea.get_text().split('\n')

        if self.debug and not proxylist:
            self.export_webpage(soup, self.name + '.html')

        log.info('Parsed %d socks5 proxies from webpage.', len(proxylist))
        return proxylist

    def download_proxylist(self, url):
        proxylist = []

        filename = '{}/{}.zip'.format(self.download_path, self.name)
        if not self.download_file(url, filename):
            log.error('Failed proxylist download: %s', url)
            return proxylist

        if not is_zipfile(filename):
            log.error('File "%s" downloaded from %s is not a Zip archive.',
                      filename, url)
            return proxylist

        with ZipFile(filename, 'r') as myzip:
            for proxyfile in myzip.namelist():
                if not proxyfile.endswith('.txt'):
                    log.debug('Skipped file in Zip archive: %s', proxyfile)
                    continue
                with myzip.open(proxyfile, 'rU') as proxies:
                    proxylist = proxies.readlines()
                    break

        return proxylist
