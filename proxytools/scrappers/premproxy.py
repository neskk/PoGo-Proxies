#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import re
import jsbeautifier.unpackers.packer as packer

from bs4 import BeautifulSoup

from ..proxy_scrapper import ProxyScrapper

log = logging.getLogger(__name__)


# This site has a "bot" network checker and may result in the
# pages not being loaded. This should only happen if you request
# scans too frequently.
class Premproxy(ProxyScrapper):

    def __init__(self, args):
        super(Premproxy, self).__init__(args, 'premproxy-com')
        self.base_url = 'https://premproxy.com'

    def scrap(self):
        proxylist = []
        urls = self.extract_pages()
        for url in urls:
            html = self.request_url(url)
            if html is None:
                log.error('Failed to download webpage: %s', url)
                continue

            log.info('Parsing webpage from: %s', url)
            proxylist.extend(self.parse_webpage(html))

        return proxylist

    def parse_webpage(self, html):
        ports = {}
        proxylist = []
        soup = BeautifulSoup(html, 'html.parser')
        # soup.prettify()

        # Go through the scripts and check to see if they contain ports.
        scripts = soup.findAll('script')
        for script in scripts:
            src = script.get('src')
            if src is not None:
                extracted = self.extract_ports(src)
                # Once ports are returned, we don't need to check further.
                if extracted is not None and len(extracted) > 0:
                    ports = extracted
                    break

        # Ensure we have some ports to work with, if not, give up.
        if (len(ports) == 0):
            return proxylist

        # Verify that a row contains ip/port and country.
        container = soup.find('tr', ["anon"])
        if not container:
            log.error('Unable to find anonymous proxies in list.')
            return proxylist

        # Go through each row and pull out the information wanted.
        ips = []
        for row in soup.findAll('tr', ["anon"]):

            # Extract and check against ignored countries.
            country_td = row.find('td', attrs={'data-label': 'Country: '})
            if country_td:
                country = country_td.get_text().lower()
                if country in self.ignore_country:
                    continue

            # The ip/port list is provided via the checkbox, so grab it.
            input = row.find('input')
            if input['type'] in ('checkbox'):
                if input.has_attr('value'):
                    value = input['value']
                    if value is not None:
                        # Assume "IP | css"
                        parts = value.split('|')
                        if (len(parts) == 2):
                            if parts[1] in ports:
                                url = "{}:{}".format(parts[0], ports[parts[1]])
                                ips.append(url)

        for ip in ips:
            ip = ip.strip()
            if ip:
                proxylist.append('http://{}'.format(ip))

        log.info('Parsed %d http proxies from webpage.', len(proxylist))
        return proxylist

    # Premproxy does not have a consistent number of additional pages.
    # Check the main page for the links for pages and extract from there.
    def extract_pages(self):

        urls = []
        page_urls = []
        list_url = self.base_url + '/list/'

        html = self.request_url(list_url)
        if html is None:
            log.error('Failed to download webpage: %s', list_url)
            return urls

        # Check to see how many additional pages we can grab.
        soup = BeautifulSoup(html, 'html.parser')
        # soup.prettify()

        pagination = soup.find('ul', class_='pagination')
        if not pagination:
            log.error('Unable to find element with proxy list.')
            return urls

        links = pagination.findAll("a")
        for link in links:
            if not link.get_text() == 'next':
                urls.append(link.get('href'))

        # Now go through each of the page links and create the final url.
        for url in urls:
            if "list" in url:
                page_urls.append(self.base_url + url)
            else:
                page_urls.append(list_url + url)

        return page_urls

    # Premproxy.com uses javascript to obfuscate proxies port number.
    # Builds a dictionary with decoded values for each variable.
    # Dictionary = {'var': intValue, ...})
    def extract_ports(self, js_url):

        # Download the JS file.
        html = self.request_url(self.base_url + js_url)
        if html is None:
            log.error('Failed to download webpage: %s', js_url)
            return None

        # Check to see if this script contains the packed details needed.
        if not re.match('^eval\(function\(p,a,c,k,e,d\)', html):
            return None

        # Check to see if this script contains packing info.
        # If not, then we don't use it.
        dictionary = {}
        try:
            # For now, try and extract out the css/port pairs from the JS.
            unpack = packer.unpack(html)
            parts = re.findall(
                '\(\\\\\'\.([\w\d]+)\\\\\'\).html\((\d+)\)', unpack)

            # Now convert the list into a dictionary.
            for info in parts:
                dictionary[info[0]] = info[1]

        except Exception as e:
            log.exception('Failed do extract ports from %s: %s.', js_url, e)

        return dictionary
