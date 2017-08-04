#!/usr/bin/python
# -*- coding: utf-8 -*-

import argparse


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose',
                        help='Run in the verbose mode.',
                        action='store_true')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('-f', '--proxy-file',
                        help='Filename of proxy list to verify.')
    parser.add_argument('-o', '--output-file',
                        help='Output filename for working proxies.',
                        default='working_proxies.txt')
    parser.add_argument('-r', '--retries',
                        help='Number of attempts to check each proxy.',
                        default=5,
                        type=int)
    parser.add_argument('-t', '--timeout',
                        help='Connection timeout. Default is 5 seconds.',
                        default=5,
                        type=float)
    parser.add_argument('-bf', '--backoff-factor',
                        help=('Factor (in seconds) by which the delay ' +
                              'until next retry will increase.'),
                        default=0.25,
                        type=float)
    parser.add_argument('-mt', '--max-threads',
                        help='Maximum concurrent proxy testing threads.',
                        default=100,
                        type=int)
    parser.add_argument('-rw', '--restart-work',
                        help=('Restart work cycle after a period of time ' +
                              'specified in seconds. (0 to disable).'),
                        type=int, default=0)
    parser.add_argument('-ic', '--ignore-country',
                        help='Ignore proxies from countries in this list.',
                        action='append', default=['china'])
    parser.add_argument('--proxychains',
                        help='Output in proxychains-ng format.',
                        action='store_true')
    parser.add_argument('--kinan',
                        help='Output in Kinan City format.',
                        action='store_true')
    args = parser.parse_args()

    return args
