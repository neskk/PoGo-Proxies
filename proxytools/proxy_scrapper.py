#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from .utils import export_file

log = logging.getLogger(__name__)


class ProxyScrapper(object):
    REFERER = 'http://google.com'
    USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:76.0) '
                  'Gecko/20100101 Firefox/76.0')
    CLIENT_HEADERS = {
        'User-Agent': USER_AGENT,
        'Accept-Language': 'en-US,en',
        'Accept-Encoding': 'gzip, deflate',
        'Referer': REFERER
    }
    STATUS_FORCELIST = [500, 502, 503, 504]

    def __init__(self, args, name):
        self.timeout = args.scrapper_timeout
        self.proxy = args.scrapper_proxy
        self.ignore_country = args.proxy_ignore_country
        self.debug = args.verbose
        self.download_path = args.download_path

        self.name = name
        log.info('Initialized proxy scrapper: %s.', name)

        self.session = None
        self.retries = Retry(
            total=args.scrapper_retries,
            backoff_factor=args.scrapper_backoff_factor,
            status_forcelist=self.STATUS_FORCELIST)

    def setup_session(self):
        self.session = requests.Session()
        # Mount handler on both HTTP & HTTPS.
        self.session.mount('http://', HTTPAdapter(max_retries=self.retries))
        self.session.mount('https://', HTTPAdapter(max_retries=self.retries))

    def request_url(self, url, referer=None, post={}):
        content = None
        try:
            # Setup request headers.
            headers = self.CLIENT_HEADERS.copy()
            if referer:
                headers['Referer'] = referer

            if post:
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
                response = self.session.post(
                    url,
                    proxies={'http': self.proxy, 'https': self.proxy},
                    timeout=self.timeout,
                    headers=headers,
                    data=post)
            else:
                response = self.session.get(
                    url,
                    proxies={'http': self.proxy, 'https': self.proxy},
                    timeout=self.timeout,
                    headers=headers)

            if response.status_code == 200:
                content = response.text

            response.close()
        except Exception as e:
            log.exception('Failed to request URL "%s": %s', url, e)

        return content

    def download_file(self, url, filename, referer=None):
        result = False
        try:
            # Setup request headers.
            if referer:
                headers = self.CLIENT_HEADERS.copy()
                headers['Referer'] = referer
            else:
                headers = self.CLIENT_HEADERS

            response = self.session.get(
                url,
                proxies={'http': self.proxy, 'https': self.proxy},
                timeout=self.timeout,
                headers=headers)

            with open(filename, 'wb') as fd:
                for chunk in response.iter_content(chunk_size=128):
                    fd.write(chunk)
                result = True

            response.close()
        except Exception as e:
            log.exception('Failed to download file "%s": %s.', url, e)

        return result

    def export_webpage(self, soup, filename):
        content = soup.prettify()  # .encode('utf8')
        filename = '{}/{}'.format(self.download_path, filename)

        export_file(filename, content)
        log.debug('Web page output saved to: %s', filename)

    def validate_country(self, country):
        valid = True
        for ignore_country in self.ignore_country:
            if ignore_country in country:
                valid = False
                break
        return valid

    # Sub-classes are required to implement this method.
    # Method implementations must return found proxylist.
    def scrap(self):
        raise NotImplementedError('Must override scrap() method.')
