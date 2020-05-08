#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import random
import re
import time

from bs4 import BeautifulSoup

from ..packer import deobfuscate
from ..proxy_scrapper import ProxyScrapper

log = logging.getLogger(__name__)


# PremProxy.com has anti-scrapping measures and pages might not be loaded.
# This should only happen if you scrap this site too frequently.
class Premproxy(ProxyScrapper):

    def __init__(self, args):
        super(Premproxy, self).__init__(args, 'premproxy-com')
        self.base_url = 'https://premproxy.com'

    def scrap(self):
        self.setup_session()
        proxylist = []

        url = self.base_url + '/list/'
        html = self.request_url(url)
        if html is None:
            log.error('Failed to download webpage: %s', url)
            return proxylist

        log.info('Parsing proxylist from webpage: %s', url)
        soup = BeautifulSoup(html, 'html.parser')
        proxies = self.parse_webpage(soup)

        if not proxies:
            log.error('Scrapping aborted, found no proxies in main page: %s',
                      url)
            return proxylist

        proxylist.extend(proxies)

        next_url = self.parse_next_url(soup)
        while next_url:
            log.debug('Waiting a little bit before scrapping next page...')
            time.sleep(random.uniform(2.0, 4.0))
            html = self.request_url(next_url, url)
            if html is None:
                log.error('Failed to download webpage: %s', next_url)
                return proxylist

            log.info('Parsing proxylist from webpage: %s', next_url)
            soup = BeautifulSoup(html, 'html.parser')

            proxies = self.parse_webpage(soup)
            if not proxies:
                log.info('Scrapping finished, transparent proxies ignored.')
                break

            proxylist.extend(proxies)
            url = next_url
            next_url = self.parse_next_url(soup)

        self.session.close()
        return proxylist

    def parse_webpage(self, soup):
        proxylist = []

        # Go through the scripts and check to see if they contain ports.
        ports = {}
        for script in soup.findAll('script'):
            js_url = script.get('src')
            if not js_url:
                continue

            ports = self.extract_ports(js_url)
            # Once ports are returned, we don't need to check further.
            if ports:
                log.info('Found ports decoding dictionary.')
                break

        # Ensure we have found ports decoding dictionary.
        if not ports:
            log.error('Failed to find ports decoding dictionary.')
            return proxylist

        # Go through each row and pull out the information wanted.
        for row in soup.findAll('tr', class_='anon'):

            # Extract country and check against ignored countries.
            country_td = row.find('td', attrs={'data-label': 'Country: '})
            if country_td:
                country = country_td.get_text().lower()

                if not self.validate_country(country):
                    continue

            # The ip/port information is contained inside checkbox input tag.
            input_tag = row.find('input', attrs={'type': 'checkbox'})

            if not input_tag or not input_tag.has_attr('value'):
                log.warning('Unable to find proxy information in table row.')
                continue

            if input_tag['value']:
                # Attribute format: IP|decoding-key
                parts = input_tag['value'].split('|')
                if len(parts) != 2:
                    log.warning('Unknown proxy format on input tag.')
                    continue

                if parts[1] not in ports:
                    log.warning('Unable to find port in decoding dictionary.')
                    continue

                proxy_url = '{}:{}'.format(parts[0], ports[parts[1]])
                proxylist.append(proxy_url)

        log.info('Parsed %d http proxies from webpage.', len(proxylist))
        return proxylist

    # PremProxy.com does not have a consistent number of additional pages.
    # Check the main page for links to additional pages and extract them.
    def parse_next_url(self, soup):
        url = None

        pagination = soup.find('ul', class_='pagination')
        if not pagination:
            log.error('Unable to find pagination list.')
            return url

        # Check if there is an additional page to scrap.
        for link in pagination.findAll('a'):
            if link.get_text() == 'next':
                url = '{}/list/{}'.format(self.base_url, link.get('href'))
                break

        return url

    # PremProxy.com uses javascript to obfuscate proxies port number.
    # Check if script file has the decoding function and build a dictionary
    # with the decoding information: {'<key>': <port>, ...}.
    def extract_ports(self, js_url):
        dictionary = {}

        # Download the JS file.
        js = self.request_url(self.base_url + js_url)
        if js is None:
            log.error('Failed to download javascript file: %s', js_url)
            return dictionary

        try:
            # Check to see if script contains the decoding function.
            clean_code = deobfuscate(js)
            if not clean_code:
                return dictionary

            # Extract all the key,port pairs found in unpacked script.
            # Format: $('.<key>').html(<port>);
            clean_code = clean_code.replace("\\\'", "\'")
            matches = re.findall("\(\'\.([\w]+)\'\).html\((\d+)\)", clean_code)

            # Convert matches list into a dictionary for decoding.
            for match in matches:
                dictionary[match[0]] = match[1]

        except Exception as e:
            log.exception('Failed to extract decoding dictionary from %s: %s.',
                          js_url, e)

        return dictionary
