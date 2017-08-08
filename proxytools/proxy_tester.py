#!/usr/bin/python
# -*- coding: utf-8 -*-

import requests
import logging
from requests_futures.sessions import FuturesSession
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

log = logging.getLogger('pogo-proxies')

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
def get_proxy_test_status(proxy, future_login, future_niantic, future_ptc):
    # Start by assuming everything is OK.
    check_result = check_result_ok
    proxy_error = None

    # Make sure we don't trip any code quality tools that test scope.
    login_response = None
    niantic_response = None
    ptc_response = None
    # Make sure both requests are completed.
    try:
        login_response = future_login.result()
        niantic_response = future_niantic.result()
        if future_ptc:
            ptc_response = future_ptc.result()
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
    login_status = login_response.status_code
    niantic_status = niantic_response.status_code
    if ptc_response:
        ptc_status = ptc_response.status_code
    else:
        ptc_status = 200

    banned_status_codes = [403, 409]

    if niantic_status == 200 and login_status == 200 and ptc_status == 200:
        log.debug('Proxy %s is good.', proxy)

    elif (login_status in banned_status_codes or
          niantic_status in banned_status_codes or
          ptc_status in banned_status_codes):
        proxy_error = ('Proxy {} is banned - PTC login status code: {}, ' +
                       'Niantic status code: {}, PTC status code: {}.').format(
                            proxy, login_status, niantic_status, ptc_status)
        check_result = check_result_banned
    else:
        proxy_error = ('Proxy {} is bad - PTC login status code: {}, ' +
                       'Niantic status code: {}, PTC status code: {}.').format(
                            proxy, login_status, niantic_status, ptc_status)
        check_result = check_result_wrong

    # Explicitly release connection back to the pool, because we don't need
    # or want to consume the content.
    login_response.close()
    niantic_response.close()
    if ptc_response:
        ptc_response.close()

    return (proxy_error, check_result)


def start_request_ptc_login(session, proxy, timeout):
    proxy_test_ptc_url = 'https://sso.pokemon.com/sso/oauth2.0/authorize?' \
                         'client_id=mobile-app_pokemon-go&redirect_uri=' \
                         'https%3A%2F%2Fwww.nianticlabs.com%2Fpokemongo' \
                         '%2Ferror'

    # Send request to pokemon.com.
    future_ptc = session.get(
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

    return future_ptc


def start_request_niantic(session, proxy, timeout):
    proxy_test_url = 'https://pgorelease.nianticlabs.com/plfe/rpc'

    # Send request to nianticlabs.com.
    future_niantic = session.post(
        proxy_test_url,
        '',
        proxies={'http': proxy, 'https': proxy},
        timeout=timeout,
        headers={'Connection': 'close'},
        background_callback=__proxy_check_completed,
        stream=True)

    return future_niantic


def start_request_ptc(session, proxy, timeout):
    proxy_test_ptc_url = 'https://club.pokemon.com/us/pokemon-trainer-club'

    log.debug('Checking proxy: %s.', proxy)

    # Send request to pokemon.com.
    future_ptc = session.get(
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

    return future_ptc


# Check all proxies and return a working list with proxies.
def check_proxies(args, proxies):
    total_proxies = len(proxies)

    # Store counter per result type.
    check_results = [0] * (check_result_max + 1)

    # If proxy testing concurrency is set to automatic, use max.
    proxy_concurrency = args.max_concurrency

    if args.max_concurrency == 0:
        proxy_concurrency = total_proxies

    log.info('Starting proxy test for %d proxies with %d concurrency.',
             total_proxies, proxy_concurrency)

    # Get persistent session per host.
    login_session = get_async_requests_session(
        args.retries,
        args.backoff_factor,
        proxy_concurrency)
    niantic_session = get_async_requests_session(
        args.retries,
        args.backoff_factor,
        proxy_concurrency)

    if args.kinancity:
        ptc_session = get_async_requests_session(
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

    for proxy in proxies:
        # Start async requests & store futures.
        future_login = start_request_ptc_login(
            login_session,
            proxy,
            args.timeout)

        future_niantic = start_request_ptc_login(
            niantic_session,
            proxy,
            args.timeout)

        if args.kinancity:
            future_ptc = start_request_ptc(
                ptc_session,
                proxy,
                args.timeout)
        else:
            future_ptc = None

        items = (proxy, future_login, future_niantic, future_ptc)
        proxy_queue.append(items)

    # Wait here until all items in proxy_queue are processed.
    # We intentionally start all requests before handling them so they can
    # asynchronously continue in the background, even as we're blocking to
    # wait for one. The double loop is intentional.
    for proxy, future_login, future_niantic, future_ptc in proxy_queue:
        error, result = get_proxy_test_status(proxy,
                                              future_login,
                                              future_niantic,
                                              future_ptc)
        check_results[result] += 1

        if error:
            # Decrease output amount if there are a lot of proxies.
            if show_warnings:
                log.warning(error)
            else:
                log.debug(error)
        else:
            working_proxies.append(proxy)

    del proxy_queue[:]
    other_fails = (check_results[check_result_failed] +
                   check_results[check_result_wrong] +
                   check_results[check_result_exception] +
                   check_results[check_result_empty])
    log.info('Checked %d proxies. Working: %d, banned: %d,'
             + ' timeout: %d, other fails: %d.',
             total_proxies, len(working_proxies),
             check_results[check_result_banned],
             check_results[check_result_timeout],
             other_fails)

    return working_proxies
