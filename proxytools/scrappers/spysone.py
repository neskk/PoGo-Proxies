#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
# import random
import re
# import time

from bs4 import BeautifulSoup

from ..crazyxor import parse_crazyxor, decode_crazyxor
from ..packer import deobfuscate
from ..proxy_scrapper import ProxyScrapper
from ..utils import validate_ip

log = logging.getLogger(__name__)


class SpysOne(ProxyScrapper):

    def __init__(self, args, name):
        super(SpysOne, self).__init__(args, name)

    def scrap(self):
        self.setup_session()
        proxylist = []

        url = self.base_url
        html = self.request_url(url, url, post=self.post_data)
        if html is None:
            log.error('Failed to download webpage: %s', url)
        else:
            log.info('Parsing proxylist from webpage: %s', url)
            proxylist.extend(self.parse_webpage(html))
            # time.sleep(random.uniform(2.0, 4.0))

        self.session.close()
        return proxylist

    def parse_webpage(self, html):
        proxylist = []
        encoding = {}
        soup = BeautifulSoup(html, 'html.parser')

        for script in soup.find_all('script'):

            code = script.string
            if not code:
                continue

            for line in code.split('\n'):
                if '^' in line and ';' in line and '=' in line:
                    line = line.strip()
                    log.info('Found crazy XOR decoding script.')
                    # log.debug("Script: %s" % line)
                    clean_code = deobfuscate(line)
                    if clean_code:
                        line = clean_code
                        # log.debug("Unpacked script: %s" % clean_code)
                    # Check to see if script contains the decoding function.
                    encoding = parse_crazyxor(line)
                    log.debug('Crazy XOR decoding dictionary: %s', encoding)

        if not encoding:
            log.error('Unable to find crazy XOR decoding script.')

            if self.debug:
                self.export_webpage(soup, self.name + '.html')

            return proxylist

        # Select table rows and skip first one.
        table_rows = soup.find_all('tr', attrs={'class': ['spy1x', 'spy1xx']})[1:]

        for row in table_rows:
            columns = row.find_all('td')
            if len(columns) != 10:
                # Bad table row selected, moving on.
                continue

            # Format:
            #   <td colspan="1">
            #     <font class="spy14">
            #         183.88.16.161
            #         <script type="text/javascript">
            #         document.write("<font class=spy2>:<\/font>"+(FourFourEightNine^Two3Eight)+(ThreeSixFourTwo^NineEightFour)+(FourFourEightNine^Two3Eight)+(ThreeSixFourTwo^NineEightFour))
            #         </script>
            #     </font>
            #   </td>

            # Grab first column
            fonts = columns[0].find_all('font')
            if len(fonts) != 1:
                log.warning('Unknown format of proxy table cell.')
                continue

            info = fonts[0]
            script = info.find('script')

            if not script:
                log.warning('Unable to find port obfuscation script.')
                continue

            # Remove script tag from contents.
            script = script.extract().string
            ip = info.get_text()

            if not validate_ip(ip):
                log.warning('Invalid IP found: %s', ip)
                continue

            matches = re.findall('\(([\w\^]+)\)', script)
            numbers = [decode_crazyxor(encoding, m) for m in matches]
            port = ''.join(numbers)

            anonymous = country = columns[2].get_text()
            if anonymous != 'HIA':
                continue

            country = columns[3].get_text().lower()
            clean_name = re.match('([\w\s]+) \(.*', country)

            if clean_name:
                country = clean_name.group(1)

            if not self.validate_country(country):
                continue

            proxy_url = '{}:{}'.format(ip, port)
            proxylist.append(proxy_url)

        if self.debug and not proxylist:
            self.export_webpage(soup, self.name + '.html')

        log.info('Parsed %d proxies from webpage.', len(proxylist))
        return proxylist


class SpysHTTPS(SpysOne):

    def __init__(self, args):
        super(SpysHTTPS, self).__init__(args, 'spys-one-https')
        self.base_url = 'http://spys.one/en/https-ssl-proxy/'
        self.post_data = 'xpp=5&xf1=1&xf4=0&xf5=0'


class SpysSOCKS(SpysOne):

    def __init__(self, args):
        super(SpysSOCKS, self).__init__(args, 'spys-one-socks')
        self.base_url = 'http://spys.one/en/socks-proxy-list/'
        self.post_data = 'xpp=5&xf1=0&xf2=0&xf4=0&xf5=0'
