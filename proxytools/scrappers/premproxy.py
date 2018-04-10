#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import re
import jsbeautifier.unpackers.packer as packer

from bs4 import BeautifulSoup

from ..proxy_scrapper import ProxyScrapper
from ..utils import validate_ip

log = logging.getLogger(__name__)


# This site has a "bot" network checker and may result in the pages not being loaded.
# This should only happen if you request scans too frequently.
class Premproxy(ProxyScrapper):

    def __init__(self, args):
        super(Premproxy, self).__init__(args, 'premproxy-com')
        self.base_url = 'https://premproxy.com'

    def scrap(self):
        proxylist = []
        urls = self.extract_pages()
        print urls
        for url in urls:
            html = self.request_url(url)
            if html is None:
                log.error('Failed to download webpage: %s', url)
                continue

            log.info('Parsing webpage from: %s', url)
            proxylist.extend(self.parse_webpage(html))

        return proxylist

    def parse_webpage(self, html):
        proxylist = []
        soup = BeautifulSoup(html, 'html.parser')
        # soup.prettify()

        # For now, we'll assume <script> #2 in the list is the one with ports.
        scripts = soup.findAll('script')
        js_url = self.base_url + scripts[1].get('src')
        ports = self.extract_ports(js_url)
        if (len(ports) == 0):
            return proxylist
    
        # Verify that a row contains ip/port and country.
        container = soup.find('tr', ["anon", "transp"])
        if not container:
            log.error('Unable to find element with proxy list.')
            return proxylist
    
        # Go through each row and pull out the informaton wanted.
        ips = []
        for row in soup.findAll('tr', ["anon", "transp"]):
    
            # Extract and check against ignored countries.
            country_td = row.find('td', attrs={'data-label': 'Country: '})
            if country_td:
                country = country_td.get_text().lower()
                if country in self.ignore_country:
                    continue
    
            # The ip/port list is provided via the checkbox, so grab it.
            input = row.find('input')
            if input['type'] in ('checkbox'):
                value = ''
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
            if ip and validate_ip(ip.split(':')[0]):
                proxylist.append('http://{}'.format(ip))

        log.info('Parsed %d socks5 proxies from webpage.', len(proxylist))
        return proxylist


    # Premproxy does not contain a consistent number of additional pages.
    # So we check the main page for the links for pages and extract those.
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
    
        print 'step 1'
    
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
    
        dictionary = {}
    
        # Download the JS file.
        html = self.request_url(js_url)
        if html is None:
            log.error('Failed to download webpage: %s', js_url)
            return dict
    
        try:
            # For now, try and extract out the css/port pairs from the JS.
            # This likely is a really back way of doing it, I'll revisit later.
            unpack = packer.unpack(html)
            unpack = unpack.replace("$(document).ready(function(){", "")
            unpack = unpack.replace("});", "")
            unpack = unpack.replace("\\", "")
            unpack = unpack.replace("'", "")
            unpack = unpack.replace(".", "")
    
            # Pull out everything that is within a bracket.
            parts = re.findall('\((.*?)\)', unpack)
    
            # Now convert the list into a dictionary.
            # Every other entry in the list is a pair css/port.
            i = 0
            while i < len(parts):
                dictionary[parts[i]] = parts[i+1]
                i += 2
    
            return dictionary
    
        except Exception as e:
            log.exception('Failed do extract ports from %s: %s.', js_url, e)
            return dictionary
