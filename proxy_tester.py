#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys
import argparse
import requests
import logging
import time

from requests_futures.sessions import FuturesSession
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

logging.getLogger(
    'requests.packages.urllib3.connectionpool').setLevel(logging.CRITICAL)

logging.basicConfig(
    format='%(asctime)s [%(threadName)15.15s][%(levelname)8.8s] %(message)s',
    level=logging.INFO)
log = logging.getLogger(__name__)


# Proxy check result constants.
check_result_ok = 0
check_result_failed = 1
check_result_banned = 2
check_result_wrong = 3
check_result_timeout = 4
check_result_exception = 5
check_result_empty = 6
check_result_max = 6  # Should be equal to maximal return code.


# Background handler for completed proxy check requests.
# Currently doesn't do anything.
def __proxy_check_completed(sess, resp):
    pass


# Get a future_requests FuturesSession that supports asynchronous workers
# and retrying requests on failure.
# Setting up a persistent session that is re-used by multiple requests can
# speed up requests to the same host, as it'll re-use the underlying TCP
# connection.
def get_async_requests_session(num_retries, backoff_factor, pool_size,
                               status_forcelist=[500, 502, 503, 504]):
    # Use requests & urllib3 to auto-retry.
    # If the backoff_factor is 0.1, then sleep() will sleep for [0.1s, 0.2s,
    # 0.4s, ...] between retries. It will also force a retry if the status
    # code returned is in status_forcelist.
    session = FuturesSession(max_workers=pool_size)

    # If any regular response is generated, no retry is done. Without using
    # the status_forcelist, even a response with status 500 will not be
    # retried.
    retries = Retry(total=num_retries, backoff_factor=backoff_factor,
                    status_forcelist=status_forcelist)

    # Mount handler on both HTTP & HTTPS.
    session.mount('http://', HTTPAdapter(max_retries=retries,
                                         pool_connections=pool_size,
                                         pool_maxsize=pool_size))
    session.mount('https://', HTTPAdapter(max_retries=retries,
                                          pool_connections=pool_size,
                                          pool_maxsize=pool_size))

    return session


# Evaluates the status of PTC and Niantic request futures, and returns the
# result (optionally with an error).
# Warning: blocking! Can only get status code if request has finished.
def get_proxy_test_status(proxy, future_ptc, future_niantic):
    # Start by assuming everything is OK.
    check_result = check_result_ok
    proxy_error = None

    # Make sure we don't trip any code quality tools that test scope.
    ptc_response = None
    niantic_response = None

    # Make sure both requests are completed.
    try:
        ptc_response = future_ptc.result()
        niantic_response = future_niantic.result()
    except requests.exceptions.ConnectTimeout:
        proxy_error = 'Connection timeout for proxy {}.'.format(proxy)
        check_result = check_result_timeout
    except requests.exceptions.ConnectionError:
        proxy_error = 'Failed to connect to proxy {}.'.format(proxy)
        check_result = check_result_failed
    except Exception as e:
        proxy_error = e
        check_result = check_result_exception

    # If we've already encountered a problem, stop here.
    if proxy_error:
        return (proxy_error, check_result)

    # Evaluate response status code.
    ptc_status = ptc_response.status_code
    niantic_status = niantic_response.status_code

    banned_status_codes = [403, 409]

    if niantic_status == 200 and ptc_status == 200:
        log.debug('Proxy %s is ok.', proxy)
    elif (niantic_status in banned_status_codes or
          ptc_status in banned_status_codes):
        proxy_error = ('Proxy {} is banned -'
                       + ' got PTC status code: {}, Niantic status'
                       + ' code: {}.').format(proxy,
                                              ptc_status,
                                              niantic_status)
        check_result = check_result_banned
    else:
        proxy_error = ('Wrong status codes -'
                       + ' PTC: {},'
                       + ' Niantic: {}.').format(ptc_status,
                                                 niantic_status)
        check_result = check_result_wrong

    # Explicitly release connection back to the pool, because we don't need
    # or want to consume the content.
    ptc_response.close()
    niantic_response.close()

    return (proxy_error, check_result)


# Requests to send for testing, which returns futures for Niantic and PTC.
def start_request_futures(ptc_session, niantic_session, proxy, timeout):
    # URLs for proxy testing.
    proxy_test_url = 'https://pgorelease.nianticlabs.com/plfe/rpc'
    proxy_test_ptc_url = 'https://sso.pokemon.com/sso/oauth2.0/authorize?' \
                         'client_id=mobile-app_pokemon-go&redirect_uri=' \
                         'https%3A%2F%2Fwww.nianticlabs.com%2Fpokemongo' \
                         '%2Ferror'

    log.debug('Checking proxy: %s.', proxy)

    # Send request to pokemon.com.
    future_ptc = ptc_session.get(
        proxy_test_ptc_url,
        proxies={'http': proxy, 'https': proxy},
        timeout=timeout,
        headers={'User-Agent': ('pokemongo/1 '
                                'CFNetwork/811.4.18 '
                                'Darwin/16.5.0'),
                 'Host': 'sso.pokemon.com',
                 'X-Unity-Version': '5.5.1f1',
                 'Connection': 'close'},
        background_callback=__proxy_check_completed,
        stream=True)

    # Send request to nianticlabs.com.
    future_niantic = niantic_session.post(
        proxy_test_url,
        '',
        proxies={'http': proxy, 'https': proxy},
        timeout=timeout,
        headers={'Connection': 'close'},
        background_callback=__proxy_check_completed,
        stream=True)

    # Return futures.
    return (future_ptc, future_niantic)


# Load proxies and return a list.
def load_proxies(args):
    proxies = []

    # Load proxies from the file. Override args.proxy if specified.
    if args.proxy_file:
        log.info('Loading proxies from file.')

        with open(args.proxy_file) as f:
            for line in f:
                stripped = line.strip()

                # Ignore blank lines and comment lines.
                if len(stripped) == 0 or line.startswith('#'):
                    continue

                proxies.append(stripped)

        log.info('Loaded %d proxies.', len(proxies))

        if len(proxies) == 0:
            log.error('Proxy file was configured but ' +
                      'no proxies were loaded. Aborting.')
            sys.exit(1)
    else:
        log.error('No proxy file supplied. Aborting.')
        sys.exit(1)

    return proxies


# Check all proxies and return a working list with proxies.
def check_proxies(args, proxies):
    total_proxies = len(proxies)

    # Store counter per result type.
    check_results = [0] * (check_result_max + 1)

    # If proxy testing concurrency is set to automatic, use max.
    proxy_concurrency = args.max_threads

    if args.max_threads == 0:
        proxy_concurrency = total_proxies

    log.info("Starting proxy test for %d proxies with %d concurrency.",
             total_proxies, proxy_concurrency)

    # Get persistent session per host.
    ptc_session = get_async_requests_session(
        args.retries,
        args.backoff_factor,
        proxy_concurrency)
    niantic_session = get_async_requests_session(
        args.retries,
        args.backoff_factor,
        proxy_concurrency)

    # List to hold background workers.
    proxy_queue = []
    working_proxies = []
    show_warnings = total_proxies <= 10

    log.info('Checking %d proxies...', total_proxies)
    if not show_warnings:
        log.info('Enable -v to see proxy testing details.')

    # Start async requests & store futures.
    for proxy in proxies:
        future_ptc, future_niantic = start_request_futures(
            ptc_session,
            niantic_session,
            proxy,
            args.timeout)

        proxy_queue.append((proxy, future_ptc, future_niantic))

    # Wait here until all items in proxy_queue are processed, so we have a list
    # of working proxies. We intentionally start all requests before handling
    # them so they can asynchronously continue in the background, even as we're
    # blocking to wait for one. The double loop is intentional.
    for proxy, future_ptc, future_niantic in proxy_queue:
        error, result = get_proxy_test_status(proxy,
                                              future_ptc,
                                              future_niantic)

        check_results[result] += 1

        if error:
            # Decrease output amount if there are a lot of proxies.
            if show_warnings:
                log.warning(error)
            else:
                log.debug(error)
        else:
            working_proxies.append(proxy)

    other_fails = (check_results[check_result_failed] +
                   check_results[check_result_wrong] +
                   check_results[check_result_exception] +
                   check_results[check_result_empty])
    log.info('Proxy check completed. Working: %d, banned: %d,'
             + ' timeout: %d, other fails: %d of total %d configured.',
             len(working_proxies), check_results[check_result_banned],
             check_results[check_result_timeout],
             other_fails,
             total_proxies)

    return working_proxies


# Thread function for periodical proxy updating.
def proxies_refresher(args):
    while True:
        # Wait before refresh, because initial refresh is done at startup.
        time.sleep(args.proxy_refresh)

        try:
            proxies = load_proxies(args)

            if not args.proxy_skip_check:
                proxies = check_proxies(args, proxies)

            # If we've arrived here, we're guaranteed to have at least one
            # working proxy. check_proxies stops the process if no proxies
            # are left.

            args.proxy = proxies
            log.info('Regular proxy refresh complete.')
        except Exception as e:
            log.exception('Exception while refreshing proxies: %s.', e)


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose",
                        help="Run in the verbose mode.",
                        action='store_true')
    parser.add_argument("-f", "--proxy-file",
                        help="Filename of proxy list to verify.",
                        required=True)
    parser.add_argument("-o", "--output-file",
                        help="Output filename for working proxies.",
                        default="working_proxies.txt")
    parser.add_argument("-r", "--retries",
                        help="Number of attempts to check each proxy.",
                        default=5,
                        type=int)
    parser.add_argument("-t", "--timeout",
                        help="Connection timeout. Default is 5 seconds.",
                        default=5,
                        type=float)
    parser.add_argument("-bf", "--backoff-factor",
                        help=('Factor (in seconds) by which the delay ' +
                              'until next retry will increase.'),
                        default=0.25,
                        type=float)
    parser.add_argument("-mt", "--max-threads",
                        help="Maximum concurrent proxy testing threads.",
                        default=100,
                        type=int)
    parser.add_argument("--proxychains",
                        help="Output in proxychains-ng format.",
                        action='store_true')
    parser.add_argument("--kinan",
                        help="Output in Kinan City format.",
                        action='store_true')
    args = parser.parse_args()

    return args


def export_proxies(filename, proxies):
    with open(filename, "w") as file:
        file.truncate()
        for proxy in proxies:
            file.write(proxy + "\n")


def export_proxies_proxychains(filename, proxies):
    with open(filename, "w") as file:
        file.truncate()
        for proxy in proxies:
            # Split the protocol
            protocol, address = proxy.split("://", 2)
            # address = proxy.split("://")[1]
            # Split the port
            ip, port = address.split(":", 2)
            # Write to file
            file.write(protocol + " " + ip + " " + port + "\n")


def export_proxies_kinan(filename, proxies):
    with open(filename, "w") as file:
        file.truncate()
        file.write("[")
        for proxy in proxies:
            file.write(proxy + ",")

        file.seek(-1, 1)
        file.write("]\n")


if __name__ == "__main__":
    log.setLevel(logging.INFO)

    args = get_args()
    working_proxies = []

    if args.verbose:
        log.setLevel(logging.DEBUG)
        log.debug("Running in verbose mode (-v).")

    proxies = load_proxies(args)

    working_proxies = check_proxies(args, proxies)

    output_file = args.output_file
    log.info('Writing final proxy list to: %s', output_file)

    if args.proxychains:
        export_proxies_proxychains(output_file, working_proxies)
    elif args.kinan:
        export_proxies_kinan(output_file, working_proxies)
    else:
        export_proxies(output_file, working_proxies)

    sys.exit(0)
