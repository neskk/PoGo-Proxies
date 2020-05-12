#!/usr/bin/python
# -*- coding: utf-8 -*-

import configargparse
import logging
import os
import requests
import socket
import struct
import sys

log = logging.getLogger(__name__)


def get_args():
    default_config = []
    if '-cf' not in sys.argv and '--config' not in sys.argv:
        default_config = [os.path.join(
            os.path.dirname(__file__), '../config/config.ini')]
    parser = configargparse.ArgParser(default_config_files=default_config)

    parser.add_argument('-cf', '--config',
                        is_config_file=True, help='Set configuration file.')
    parser.add_argument('-v', '--verbose',
                        help='Run in the verbose mode.',
                        action='store_true')
    parser.add_argument('--log-path',
                        help='Directory where log files are saved.',
                        default='logs')
    parser.add_argument('--download-path',
                        help='Directory where download files are saved.',
                        default='downloads')
    parser.add_argument('-pj', '--proxy-judge',
                        help='URL for AZenv script used to test proxies.',
                        default='http://pascal.hoez.free.fr/azenv.php')

    group = parser.add_argument_group('Database')
    group.add_argument('--db-name',
                       help='Name of the database to be used.',
                       required=True)
    group.add_argument('--db-user',
                       help='Username for the database.',
                       required=True)
    group.add_argument('--db-pass',
                       help='Password for the database.',
                       required=True)
    group.add_argument('--db-host',
                       help='IP or hostname for the database.',
                       default='127.0.0.1')
    group.add_argument('--db-port',
                       help='Port for the database.',
                       type=int, default=3306)

    group = parser.add_argument_group('Proxy Sources')
    group.add_argument('-Pf', '--proxy-file',
                       help='Filename of proxy list to verify.',
                       default=None)
    group.add_argument('-Ps', '--proxy-scrap',
                       help='Scrap webpages for proxy lists.',
                       default=False,
                       action='store_true')
    group.add_argument('-Pp', '--proxy-protocol',
                       help=('Specify proxy protocol we are testing. ' +
                             'Default: socks.'),
                       default='socks',
                       choices=('http', 'socks', 'all'))
    group.add_argument('-Pri', '--proxy-refresh-interval',
                       help=('Refresh proxylist from configured sources '
                             'every X minutes. Default: 180.'),
                       default=180,
                       type=int)
    group.add_argument('-Psi', '--proxy-scan-interval',
                       help=('Scan proxies from database every X minutes. '
                             'Default: 60.'),
                       default=60,
                       type=int)
    group.add_argument('-Pic', '--proxy-ignore-country',
                       help=('Ignore proxies from countries in this list. '
                             'Default: ["china"]'),
                       default=['china'],
                       action='append')

    group = parser.add_argument_group('Output')
    group.add_argument('-Oi', '--output-interval',
                       help=('Output working proxylist every X minutes. '
                             'Default: 60.'),
                       default=60,
                       type=int)
    group.add_argument('-Ol', '--output-limit',
                       help=('Maximum number of proxies to output. '
                             'Default: 100.'),
                       default=100,
                       type=int)
    group.add_argument('-Onp', '--output-no-protocol',
                       help='Proxy URL format will not include protocol.',
                       default=False,
                       action='store_true')
    group.add_argument('-Oh', '--output-http',
                       help=('Output filename for working HTTP proxies. '
                             'To disable: None/False.'),
                       default='working_http.txt')
    group.add_argument('-Os', '--output-socks',
                       help=('Output filename for working SOCKS proxies. '
                             'To disable: None/False.'),
                       default='working_socks.txt')
    group.add_argument('-Okc', '--output-kinancity',
                       help=('Output filename for KinanCity proxylist. '
                             'Default: None (disabled).'),
                       default=None)
    group.add_argument('-Opc', '--output-proxychains',
                       help=('Output filename for ProxyChains proxylist. '
                             'Default: None (disabled).'),
                       default=None)
    group.add_argument('-Orm', '--output-rocketmap',
                       help=('Output filename for RocketMap proxylist. '
                             'Default: None (disabled).'),
                       default=None)

    group = parser.add_argument_group('Proxy Tester')
    group.add_argument('-Tr', '--tester-retries',
                       help=('Maximum number of web request attempts. '
                             'Default: 5.'),
                       default=5,
                       type=int)
    group.add_argument('-Tbf', '--tester-backoff-factor',
                       help=('Time factor (in seconds) by which the delay '
                             'until next retry will increase. Default: 0.5.'),
                       default=0.5,
                       type=float)
    group.add_argument('-Tt', '--tester-timeout',
                       help='Connection timeout in seconds. Default: 5.',
                       default=5,
                       type=float)
    group.add_argument('-Tmc', '--tester-max-concurrency',
                       help=('Maximum concurrent proxy testing threads. '
                             'Default: 100.'),
                       default=100,
                       type=int)
    group.add_argument('-Tda', '--tester-disable-anonymity',
                       help='Disable anonymity proxy test.',
                       default=False,
                       action='store_true')
    group.add_argument('-Tni', '--tester-notice-interval',
                       help=('Print proxy tester statistics every X seconds. '
                             'Default: 60.'),
                       default=60,
                       type=int)
    group.add_argument('-Tpv', '--tester-pogo-version',
                       help='PoGo API version currently required by Niantic.',
                       default='0.175.1')

    group = parser.add_argument_group('Proxy Scrapper')
    group.add_argument('-Sr', '--scrapper-retries',
                       help=('Maximum number of web request attempts. '
                             'Default: 3.'),
                       default=3,
                       type=int)
    group.add_argument('-Sbf', '--scrapper-backoff-factor',
                       help=('Time factor (in seconds) by which the delay '
                             'until next retry will increase. Default: 0.5.'),
                       default=0.5,
                       type=float)
    group.add_argument('-St', '--scrapper-timeout',
                       help='Connection timeout in seconds. Default: 5.',
                       default=5,
                       type=float)
    group.add_argument('-Sp', '--scrapper-proxy',
                       help=('Use this proxy for webpage scrapping. '
                             'Format: <proto>://[<user>:<pass>@]<ip>:<port> '
                             'Default: None.'),
                       default=None)
    args = parser.parse_args()

    return args


def load_file(filename):
    lines = []

    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            stripped = line.strip()

            # Ignore blank lines and comment lines.
            if len(stripped) == 0 or line.startswith('#'):
                continue

            lines.append(lines)

        log.info('Read %d lines from file %s.', len(lines), filename)

    return lines


def export_file(filename, content):
    with open(filename, 'w', encoding='utf-8') as file:
        file.truncate()
        if isinstance(content, list):
            for line in content:
                file.write(line + '\n')
        else:
            file.write(content)


def parse_azevn(response):
    lines = response.split('\n')
    result = {
        'remote_addr': None,
        'x_unity_version': None,
        'user_agent': None
    }
    try:
        for line in lines:
            if 'REMOTE_ADDR' in line:
                result['remote_addr'] = line.split(' = ')[1]
            if 'X_UNITY_VERSION' in line:
                result['x_unity_version'] = line.split(' = ')[1]
            if 'USER_AGENT' in line:
                result['user_agent'] = line.split(' = ')[1]
    except Exception as e:
        log.warning('Error parsing AZ Environment variables: %s', e)

    return result


def get_local_ip(proxy_judge):
    local_ip = None
    try:
        r = requests.get(proxy_judge)
        test = parse_azevn(r.text)
        local_ip = test['remote_addr']
    except Exception as e:
        log.exception('Failed to connect to proxy judge: %s', e)

    return local_ip


def validate_ip(ip):
    try:
        parts = ip.split('.')
        return len(parts) == 4 and all(0 <= int(part) < 256 for part in parts)
    except ValueError:
        # One of the "parts" is not convertible to integer.
        log.warning('Bad IP: %s', ip)
        return False
    except (AttributeError, TypeError):
        # Input is not even a string.
        log.warning('Weird IP: %s', ip)
        return False


def ip2int(addr):
    return struct.unpack('!I', socket.inet_aton(addr))[0]


def int2ip(addr):
    return socket.inet_ntoa(struct.pack('!I', addr))
