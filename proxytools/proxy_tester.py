#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import requests
import time

from datetime import datetime
from queue import Queue

from requests.adapters import HTTPAdapter
from requests.packages import urllib3
from requests.exceptions import ConnectionError, ConnectTimeout
from timeit import default_timer
from threading import Event, Lock, Thread

from .ip2location import IP2LocationDatabase
from .models import ProxyStatus, Proxy
from .utils import export_file, parse_azevn


log = logging.getLogger(__name__)


class ProxyTester():
    USER_AGENT = 'pokemongo/0 CFNetwork/897.1 Darwin/17.5.0'
    UNITY_VERSION = '2017.1.2f1'

    BASE_HEADERS = {
        'Connection': 'close',
        'Accept': '*/*',
        'User-Agent': USER_AGENT,
        'Accept-Language': 'en-us',
        'Accept-Encoding': 'br, gzip, deflate',
        'X-Unity-Version': UNITY_VERSION
    }

    POGO_HEADERS = BASE_HEADERS.copy()
    POGO_HEADERS['host'] = 'sso.pokemon.com'

    NIANTIC_URL = 'https://pgorelease.nianticlabs.com/plfe/version'

    PTC_LOGIN_URL = ('https://sso.pokemon.com/sso/login?service='
                     'https%3A%2F%2Fsso.pokemon.com%2Fsso%2Foauth2.0%2F'
                     'callbackAuthorize&locale=en_US')
    PTC_LOGIN_KEYWORD = '"execution"'

    PTC_SIGNUP_URL = 'https://club.pokemon.com/us/pokemon-trainer-club'
    PTC_SIGNUP_KEYWORD = 'Pokémon Trainer Club | Pokemon.com'

    STATUS_FORCELIST = [500, 502, 503, 504]
    STATUS_BANLIST = [403, 409]

    def __init__(self, args):
        self.debug = args.verbose
        self.download_path = args.download_path
        self.timeout = args.tester_timeout
        self.max_concurrency = args.tester_max_concurrency
        self.disable_anonymity = args.tester_disable_anonymity
        self.notice_interval = args.tester_notice_interval
        self.pogo_version = args.tester_pogo_version

        self.scan_interval = args.proxy_scan_interval
        self.ignore_country = args.proxy_ignore_country

        self.proxy_judge = args.proxy_judge
        self.local_ip = args.local_ip

        self.ip2location = IP2LocationDatabase(args)

        self.running = Event()
        self.test_queue = Queue()
        self.test_hashes = []
        self.proxy_updates_lock = Lock()
        self.proxy_updates = {}

        self.stats = {
            'valid': 0,
            'fail': 0,
            'total_valid': 0,
            'total_fail': 0
        }

        # Making unverified HTTPS requests prints warning messages
        # https://urllib3.readthedocs.io/en/latest/advanced-usage.html#ssl-warnings
        urllib3.disable_warnings()
        # logging.captureWarnings(True)

        self.retries = urllib3.Retry(
            total=args.tester_retries,
            backoff_factor=args.tester_backoff_factor,
            status_forcelist=self.STATUS_FORCELIST)

    def launch(self):
        # Start proxy manager thread.
        manager = Thread(name='proxy-manager',
                         target=self.__test_manager)
        manager.daemon = True
        manager.start()

        # Start proxy tester request validation threads.
        for i in range(self.max_concurrency):
            tester = Thread(name='proxy-tester-{:03}'.format(i),
                            target=self.__proxy_tester)
            tester.daemon = True
            tester.start()

    def validate_responses(self):
        content = self.__test_response(
            self.NIANTIC_URL, self.POGO_HEADERS)
        if not content:
            log.error('Request to Niantic failed.')
            return False
        if self.pogo_version not in content:
            self.__export_response('response_niantic.txt', content)
            log.error('Unable to find "%s" in Niantic response.',
                      self.pogo_version)
            return False

        content = self.__test_response(
            self.PTC_LOGIN_URL, self.POGO_HEADERS)
        if not content:
            log.error('Request to PTC log-in failed.')
            return False
        if self.PTC_LOGIN_KEYWORD not in content:
            self.__export_response('response_ptc_login.txt', content)
            log.error('Unable to find "%s" in PTC log-in response.',
                      self.PTC_LOGIN_KEYWORD)
            return False

        content = self.__test_response(
            self.PTC_SIGNUP_URL, self.BASE_HEADERS)
        if not content:
            log.error('Request to PTC sign-up failed.')
            return False
        if self.PTC_SIGNUP_KEYWORD not in content:
            self.__export_response('response_ptc_signup.txt', content)
            log.error('Unable to find "%s" in PTC sign-up response.',
                      self.PTC_SIGNUP_KEYWORD)
            return False

        return True

    def __test_response(self, url, headers):
        content = None
        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=self.timeout)
            if response.status_code in self.STATUS_BANLIST:
                log.error('Request was refused by: %s.', url)
            elif not response.text:
                log.error('Unable to parse response from: %s', url)
            else:
                content = response.text
        except Exception as e:
            log.exception('Unable to fetch content from: %s - %s.',
                          url, e)

        return content

    # Make HTTP request using selected proxy.
    def __test_proxy(self, session, target_url, headers, parser=None):
        result = {
            'status': ProxyStatus.UNKNOWN,
            'message': None,
            'latency': 0,
        }

        try:
            response = session.get(
                target_url,
                headers=headers,
                timeout=self.timeout,
                verify=False)

            if response.status_code in self.STATUS_BANLIST:
                result['status'] = ProxyStatus.BANNED
                result['message'] = 'Proxy seems to be banned.'
            elif not response.text:
                result['status'] = ProxyStatus.ERROR
                result['message'] = 'No content in response.'
            else:
                result['latency'] = response.elapsed.total_seconds()
                if parser:
                    parser(result, response.text)

            response.close()
        except ConnectTimeout:
            result['status'] = ProxyStatus.TIMEOUT
            result['message'] = 'Connection timed out.'
        except ConnectionError:
            result['status'] = ProxyStatus.ERROR
            result['message'] = 'Failed to connect.'
        except Exception as e:
            result['status'] = ProxyStatus.ERROR
            result['message'] = str(e)

        return result

    def __parse_anonymity(self, result, content):
        azenv = parse_azevn(content)
        debug_response = False
        if azenv['remote_addr'] == self.local_ip:
            result['status'] = ProxyStatus.ERROR
            result['message'] = 'Non-anonymous proxy.'
        elif azenv['x_unity_version'] != self.UNITY_VERSION:
            result['status'] = ProxyStatus.ERROR
            result['message'] = 'Bad headers.'
            debug_response = True
        elif azenv['user_agent'] != self.USER_AGENT:
            result['status'] = ProxyStatus.ERROR
            result['message'] = 'Bad user-agent.'
            debug_response = True
        else:
            result['status'] = ProxyStatus.OK
            result['message'] = 'Passed test.'

        if debug_response and self.debug:
            self.__export_response('response_anonymity.txt', content)

    def __parse_niantic(self, result, content):
        if self.pogo_version not in content:
            result['status'] = ProxyStatus.ERROR
            result['message'] = 'Invalid response.'
        else:
            result['status'] = ProxyStatus.OK
            result['message'] = 'Passed test.'

    def __parse_ptc_login(self, result, content):
        if self.PTC_LOGIN_KEYWORD not in content:
            result['status'] = ProxyStatus.ERROR
            result['message'] = 'Invalid response.'
        else:
            result['status'] = ProxyStatus.OK
            result['message'] = 'Passed test.'

    def __parse_ptc_signup(self, result, content):
        if self.PTC_SIGNUP_KEYWORD not in content:
            result['status'] = ProxyStatus.ERROR
            result['message'] = 'Invalid response.'
        else:
            result['status'] = ProxyStatus.OK
            result['message'] = 'Passed test.'

    def __test_anonymity(self, proxy, session):
        result = self.__test_proxy(
            session,
            self.proxy_judge,
            self.BASE_HEADERS,
            self.__parse_anonymity)

        proxy['anonymous'] = result['status']
        log.debug('%s anonymous test: %s', proxy['url'], result['message'])

        return result

    def __test_niantic(self, proxy, session):
        result = self.__test_proxy(
            session,
            self.NIANTIC_URL,
            self.POGO_HEADERS,
            self.__parse_niantic)

        proxy['niantic'] = result['status']
        log.debug('%s Niantic test: %s', proxy['url'], result['message'])

        return result

    def __test_ptc_login(self, proxy, session):
        result = self.__test_proxy(
            session,
            self.PTC_LOGIN_URL,
            self.POGO_HEADERS,
            self.__parse_ptc_login)

        proxy['ptc_login'] = result['status']
        log.debug('%s PTC log-in test: %s', proxy['url'], result['message'])

        return result

    def __test_ptc_signup(self, proxy, session):
        result = self.__test_proxy(
            session,
            self.PTC_SIGNUP_URL,
            self.BASE_HEADERS,
            self.__parse_ptc_signup)

        proxy['ptc_signup'] = result['status']
        log.debug('%s PTC sign-up test: %s', proxy['url'], result['message'])

        return result

    def __update_proxy(self, proxy, valid=False):
        proxy['scan_date'] = datetime.utcnow()
        if valid:
            proxy['fail_count'] = 0
            self.stats['valid'] += 1
            self.stats['total_valid'] += 1
        else:
            proxy['fail_count'] += 1
            self.stats['fail'] += 1
            self.stats['total_fail'] += 1

        proxy = Proxy.db_format(proxy)
        with self.proxy_updates_lock:
            self.test_hashes.remove(proxy['hash'])
            self.proxy_updates[proxy['hash']] = proxy

    def __run_tests(self, proxy):
        result = True

        session = requests.Session()

        session.mount('http://', HTTPAdapter(max_retries=self.retries))
        session.mount('https://', HTTPAdapter(max_retries=self.retries))

        session.proxies = {'http': proxy['url'], 'https': proxy['url']}

        latency = []
        valid = False
        # Send request to proxy judge.
        if not self.disable_anonymity:
            result = self.__test_anonymity(proxy, session)
        # Send request to Niantic (PoGo).
        if result['status'] == ProxyStatus.OK:
            latency.append(result['latency'])
            result = self.__test_niantic(proxy, session)
        # Send request to PTC log-in (PoGo).
        if result['status'] == ProxyStatus.OK:
            latency.append(result['latency'])
            result = self.__test_ptc_login(proxy, session)
        # Send request to PTC sign-up.
        if result['status'] == ProxyStatus.OK:
            latency.append(result['latency'])
            result = self.__test_ptc_signup(proxy, session)

        if result['status'] == ProxyStatus.OK:
            latency.append(result['latency'])
            valid = True
            # Compute average latency (response time).
            latency_total = sum(latency)
            proxy['latency'] = int(latency_total * 1000 / len(latency))

            country = self.ip2location.lookup_country(proxy['ip'])
            log.info('%s (%dms - %s) passed all tests.',
                     proxy['url'], proxy['latency'], country)

            for ignore_country in self.ignore_country:
                if ignore_country in country:
                    result = False
                    log.warning('%s discarded because country %s is ignored.',
                                proxy['url'], country)
                    break

        self.__update_proxy(proxy, valid=valid)
        session.close()
        return valid

    def __test_manager(self):
        notice_timer = default_timer()
        while True:
            now = default_timer()

            # Print statistics regularly.
            if now >= notice_timer + self.notice_interval:
                log.info('Tested a total of %d good and %d bad proxies.',
                         self.stats['total_valid'], self.stats['total_fail'])
                log.info('Tested %d good and %d bad proxies in last %ds.',
                         self.stats['valid'], self.stats['fail'],
                         self.notice_interval)

                notice_timer = now
                self.stats['valid'] = 0
                self.stats['fail'] = 0

            try:
                with self.proxy_updates_lock:
                    queue_size = self.test_queue.qsize()
                    log.debug('%d proxy tests running...',
                              len(self.test_hashes) - queue_size)

                    # Upsert updated proxies into database.
                    updates_count = len(self.proxy_updates)
                    if updates_count > 10:
                        proxies = list(self.proxy_updates.values())
                        result = False
                        with Proxy.database().atomic():
                            result = Proxy.insert_many(proxies).on_conflict_replace().execute()

                        if result:
                            log.info('Updated %d proxies to database.',
                                     updates_count)
                        else:
                            log.warning('Failed to upsert %d proxies.',
                                        updates_count)
                        self.proxy_updates = {}

                    # Request more proxies to test.
                    refill = self.max_concurrency - queue_size

                    if refill > 0:
                        refill = min(refill, self.max_concurrency)
                        proxylist = Proxy.get_scan(
                            refill, self.test_hashes, self.scan_interval)
                        count = 0
                        for proxy in proxylist:
                            self.test_queue.put(proxy)
                            self.test_hashes.append(proxy['hash'])
                            count += 1

                        log.debug('Enqueued %d proxies for testing.', count)

            except Exception as e:
                log.exception('Exception in proxy manager: %s.', e)

            if self.running.is_set():
                log.debug('Proxy manager shutting down...')
                break

            time.sleep(5)

    def __proxy_tester(self):
        """Main function for proxy tester threads"""
        log.debug('Proxy tester started.')

        while True:
            if self.running.is_set():
                log.debug('Proxy tester shutdown.')
                break

            proxy = self.test_queue.get()

            # Reset proxy statuses.
            proxy.update({
                'anonymous': ProxyStatus.UNKNOWN,
                'niantic': ProxyStatus.UNKNOWN,
                'ptc-login': ProxyStatus.UNKNOWN,
                'ptc-signup': ProxyStatus.UNKNOWN
            })
            self.__run_tests(proxy)

    def __export_response(self, filename, content):
        filename = '{}/{}'.format(self.download_path, filename)

        export_file(filename, content)
        log.debug('Response content saved to: %s', filename)
