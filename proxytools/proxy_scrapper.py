#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import os
import re
import requests

from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from bs4 import BeautifulSoup
from zipfile import ZipFile, is_zipfile

from .utils import validate_ip

log = logging.getLogger('pogo-proxies')


def download_webpage(target_url, proxy=None, timeout=5):
    s = requests.Session()

    retries = Retry(total=3,
                    backoff_factor=0.5,
                    status_forcelist=[500, 502, 503, 504])

    s.mount('http://', HTTPAdapter(max_retries=retries))

    headers = {
        'User-Agent': ('Mozilla/5.0 (Windows NT 6.1; WOW64; rv:54.0) ' +
                       'Gecko/20100101 Firefox/54.0'),
        'Referer': 'http://google.com'
    }

    r = s.get(target_url,
              proxies={'http': proxy, 'https': proxy},
              timeout=timeout,
              headers=headers)

    if r.status_code == 200:
        return r.content

    return None


def download_file(target_url, filename):
    try:
        headers = {
            'User-Agent': ('Mozilla/5.0 (Windows NT 6.1; WOW64; rv:54.0) ' +
                           'Gecko/20100101 Firefox/54.0'),
            'Referer': 'http://google.com'
        }
        r = requests.get(target_url, headers=headers)

        with open(filename, 'wb') as fd:
            for chunk in r.iter_content(chunk_size=128):
                fd.write(chunk)

    except Exception as e:
        log.exception('Failed do download file from %s: %s.', target_url, e)
        return False

    return True


# Sockslist.net uses javascript to obfuscate proxies port number.
# Builds a dictionary with decoded values for each variable.
# Dictionary = {'var': intValue, ...})
def parse_crazy_encoding(code):
    dictionary = {}
    variables = code.split(';')
    for var in variables:
        if '=' in var:
            assignment = var.split(' = ')
            dictionary[assignment[0]] = assignment[1]

    for var in dictionary:
        recursive_decode(dictionary, var)
    return dictionary


def recursive_decode(dictionary, var):
    if var.isdigit():
        return var

    value = dictionary[var]
    if value.isdigit():
        return value
    elif '^' in value:
        l_value, r_value = value.split('^')
        answer = str(int(recursive_decode(dictionary, l_value)) ^
                     int(recursive_decode(dictionary, r_value)))
        dictionary[var] = answer
        return answer


def crazy_decode(dictionary, code):
    if code.isdigit():
        return code
    value = dictionary.get(code, False)
    if value and value.isdigit():
        return value
    elif '^' in code:
        l_value, r_value = code.split('^', 1)
        answer = str(int(crazy_decode(dictionary, l_value)) ^
                     int(crazy_decode(dictionary, r_value)))
        return answer


def parse_sockslist(html, ignore_country=[]):
    proxies = []
    dictionary = {}
    soup = BeautifulSoup(html, 'html.parser')
    soup.prettify()

    for script in soup.find_all('script'):
        code = script.get_text()
        for line in code.split('\n'):
            if '^' in line and ';' in line and ' = ' in line:
                line = line.strip()
                log.debug('Found crazy XOR decoding secret code.')
                dictionary = parse_crazy_encoding(line)
                log.debug('Crazy XOR decoding dictionary: %s', dictionary)

    table = soup.find('table', class_='proxytbl')
    if table is None:
        log.error('Unable to find table with proxy list.')
        return proxies

    for table_row in table.find_all('tr'):
        ip_td = table_row.find('td', class_='t_ip')
        if ip_td is None:
            continue
        ip = ip_td.get_text()

        if not validate_ip(ip):
            log.warning('Invalid IP found: %s', ip)
            continue

        port_text = table_row.find('td', class_='t_port').get_text()
        try:
            # Find encoded string with proxy port.
            m = re.search('(?<=document.write\()([\w\d\^]+)\)', port_text)
            # Decode proxy port using 'secret' decoding dictionary.
            port = crazy_decode(dictionary, m.group(1))
            if not port.isdigit():
                log.error('Unable to find proxy port number.')
                continue
        except Exception as e:
            log.error('Unable to parse proxy port: %s', repr(e))
            continue
        country = table_row.find('td', class_='t_country').get_text()

        if country in ignore_country:
            continue
        proxies.append('socks5://{}:{}'.format(ip, port))

    return proxies


def scrap_sockslist_net(ignore_country):
    urls = (
        'https://sockslist.net/list/proxy-socks-5-list#proxylist',
        'https://sockslist.net/list/proxy-socks-5-list/2#proxylist',
        'https://sockslist.net/list/proxy-socks-5-list/3#proxylist'
    )
    proxylist = set()
    for url in urls:
        html = download_webpage(url)
        if html is None:
            log.error('Failed to download webpage: %s', url)
            continue
        proxies = parse_sockslist(html, ignore_country)
        proxylist.update(proxies)
        log.info('Parsed webpage %s and got %d socks5 proxies.',
                 url, len(proxies))

    return proxylist


def parse_socksproxylist24(html):
    proxies = []
    soup = BeautifulSoup(html, 'html.parser')
    content = soup.prettify()

    proxylist = soup.find('textarea', onclick='this.focus();this.select()')
    if proxylist is None:
        log.error('Unable to find textarea with proxy list.')
        return proxies

    proxylist = proxylist.get_text().split('\n')
    for proxy in proxylist:
        proxy = proxy.strip()
        if proxy and validate_ip(proxy.split(':')[0]):
            proxies.append('socks5://{}'.format(proxy))

    if not proxies:
        log.debug('Blank webpage: %s', content)
    return proxies


def parse_socksproxylist24_links(html):
    urls = []
    soup = BeautifulSoup(html, 'html.parser')
    soup.prettify()

    for post_title in soup.find_all('h3', class_='post-title entry-title'):
        url = post_title.find('a')
        if url is None:
            continue
        url = url.get('href')
        log.debug('Found potential proxy list in: %s', url)
        urls.append(url)

    return urls


def scrap_socksproxylist24_top():
    url = 'http://www.socksproxylist24.top'
    proxylist = set()

    html = download_webpage(url)
    if html is None:
        log.error('Failed to download webpage: %s', url)
        return proxylist

    urls = parse_socksproxylist24_links(html)
    log.info('Parsed webpage %s and got %d links to proxylists.',
             url, len(urls))

    for url in urls:
        html = download_webpage(url)
        if html is None:
            log.error('Failed to download webpage: %s', url)
            continue
        proxies = parse_socksproxylist24(html)
        proxylist.update(proxies)
        log.info('Parsed webpage %s and got %d socks5 proxies.',
                 url, len(proxies))

    return proxylist


def parse_vipsocks24(html):
    proxies = []
    soup = BeautifulSoup(html, 'html.parser')
    content = soup.prettify()

    proxylist = soup.find('textarea', onclick='this.focus();this.select()')
    if proxylist is None:
        log.error('Unable to find textarea with proxy list.')
        download_button = soup.find('img', alt='Download')
        if download_button is None or download_button.parent.name != 'a':
            log.error('Unable to find download button for proxy list.')
        else:
            proxylist_url = download_button.parent.get('href')
            download_path = 'download'
            if not os.path.exists(download_path):
                os.makedirs(download_path)

            filename = '{}/vipsocks24.zip'.format(download_path)
            if download_file(proxylist_url, filename) and is_zipfile(filename):
                with ZipFile(filename, 'r') as myzip:
                    for proxyfile in myzip.namelist():
                        if not proxyfile.endswith('.txt'):
                            log.debug('Skipped archived file %s.', proxyfile)
                            continue
                        with myzip.open(proxyfile, 'rU') as proxylist:
                            for proxy in proxylist:
                                proxy = proxy.strip()
                                if proxy and validate_ip(proxy.split(':')[0]):
                                    proxies.append('socks5://{}'.format(proxy))
        return proxies

    proxylist = proxylist.get_text().split('\n')
    for proxy in proxylist:
        proxy = proxy.strip()
        if proxy and validate_ip(proxy.split(':')[0]):
            proxies.append('socks5://{}'.format(proxy))

    if not proxies:
        log.debug('Blank webpage: %s', content)
    return proxies


def parse_vipsocks24_links(html):
    urls = []
    soup = BeautifulSoup(html, 'html.parser')
    soup.prettify()

    for post_title in soup.find_all('h3', class_='post-title entry-title'):
        url = post_title.find('a')
        if url is None:
            continue
        url = url.get('href')
        log.debug('Found potential proxy list in: %s', url)
        urls.append(url)

    return urls


def scrap_vipsocks24_net():
    url = 'http://vipsocks24.net/'
    proxylist = set()

    html = download_webpage(url)
    if html is None:
        log.error('Failed to download webpage: %s', url)
        return proxylist

    urls = parse_vipsocks24_links(html)
    log.info('Parsed webpage %s and got %d links to proxylists.',
             url, len(urls))

    for url in urls:
        html = download_webpage(url)
        if html is None:
            log.error('Failed to download webpage: %s', url)
            continue
        proxies = parse_vipsocks24(html)
        proxylist.update(proxies)
        log.info('Parsed webpage %s and got %d socks5 proxies.',
                 url, len(proxies))

    return proxylist


def parse_proxyserverlist24(html):
    proxies = []
    soup = BeautifulSoup(html, 'html.parser')
    content = soup.prettify()

    container = soup.find('pre', attrs={'class': 'alt2', 'dir': 'ltr'})
    if not container:
        log.error('Unable to find element with proxy list.')
        return proxies

    spans = container.find_all('span')
    if not spans or len(spans) < 3:
        log.error('Unable to find element with proxy list.')
        return proxies

    proxylist = spans[2].get_text().split('\n')
    for proxy in proxylist:
        proxy = proxy.strip()
        if proxy and validate_ip(proxy.split(':')[0]):
            proxies.append('http://{}'.format(proxy))

    if not proxies:
        log.debug('Blank webpage: %s', content)
    return proxies


def parse_proxyserverlist24_links(html):
    urls = []
    soup = BeautifulSoup(html, 'html.parser')
    soup.prettify()

    for post_title in soup.find_all('h3', class_='post-title entry-title'):
        url = post_title.find('a')
        if url is None:
            continue
        url = url.get('href')
        log.debug('Found potential proxy list in: %s', url)
        urls.append(url)

    return urls


def scrap_proxyserverlist24_top():
    url = 'http://proxyserverlist24.top/'
    proxylist = set()

    html = download_webpage(url)
    if html is None:
        log.error('Failed to download webpage: %s', url)
        return proxylist

    urls = parse_proxyserverlist24_links(html)
    log.info('Parsed webpage %s and got %d links to proxylists.',
             url, len(urls))

    for url in urls:
        html = download_webpage(url)
        if html is None:
            log.error('Failed to download webpage: %s', url)
            continue
        proxies = parse_proxyserverlist24(html)
        proxylist.update(proxies)
        log.info('Parsed webpage %s and got %d http proxies.',
                 url, len(proxies))

    return proxylist
