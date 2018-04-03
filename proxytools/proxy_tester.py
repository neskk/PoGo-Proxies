#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import time

from datetime import datetime
from queue import Queue, Empty
from requests_futures.sessions import FuturesSession
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError, ConnectTimeout
from timeit import default_timer
from threading import Event, Lock, Thread

from models import ProxyStatus, Proxy
from utils import export_file, parse_azevn

import requests


log = logging.getLogger(__name__)


class ProxyTester():
    USER_AGENT = 'pokemongo/0 CFNetwork/894 Darwin/17.4.0'
    UNITY_VERSION = '2017.1.2f1'
    POKEMON_HOST = 'sso.pokemon.com'

    CLIENT_HEADERS = {
        'Connection': 'close',
        'Accept': '*/*',
        'User-Agent': USER_AGENT,
        'Accept-Language': 'en-us',
        'Accept-Encoding': 'br, gzip, deflate',
        'X-Unity-Version': UNITY_VERSION
    }

    NIANTIC_URL = 'https://pgorelease.nianticlabs.com/plfe/version'
    NIANTIC_KEYWORD = '0.97.1'

    PTC_LOGIN_URL = ('https://sso.pokemon.com/sso/login?service='
                     'https%3A%2F%2Fsso.pokemon.com%2Fsso%2Foauth2.0%2F'
                     'callbackAuthorize&locale=en_US')
    PTC_LOGIN_KEYWORD = '"execution"'

    PTC_SIGNUP_URL = 'https://club.pokemon.com/us/pokemon-trainer-club'
    PTC_SIGNUP_KEYWORD = 'Pokémon Trainer Club | Pokemon.com'

    STATUS_FORCELIST = [500, 502, 503, 504]
    STATUS_BANLIST = [403, 409]

    def __init__(self, args):

        self.retries = args.tester_retries
        self.backoff_factor = args.tester_backoff_factor
        self.timeout = args.tester_timeout
        self.max_concurrency = args.tester_max_concurrency
        self.disable_anonymity = args.tester_disable_anonymity
        self.notice_interval = args.tester_notice_interval

        self.proxy_judge = args.proxy_judge
        self.local_ip = args.local_ip

        self.running = Event()
        self.work_queue = Queue()
        self.proxy_updates_lock = Lock()
        self.proxy_updates = {}
        self.proxy_tests = []

        self.statistics = {
            'valid': 0,
            'fail': 0
        }

        if self.disable_anonymity:
            self.test_proxy = self.__test_niantic
        else:
            self.test_proxy = self.__test_anonymity

        # Setup asynchronous request pool.
        self.session = FuturesSession(max_workers=self.max_concurrency)

        retries = Retry(
            total=self.retries,
            backoff_factor=self.backoff_factor,
            status_forcelist=self.STATUS_FORCELIST)

        # Mount handler on both HTTP & HTTPS.
        self.session.mount('http://', HTTPAdapter(
            max_retries=retries,
            pool_connections=self.max_concurrency,
            pool_maxsize=self.max_concurrency))
        self.session.mount('https://', HTTPAdapter(
            max_retries=retries,
            pool_connections=self.max_concurrency,
            pool_maxsize=self.max_concurrency))

        # Start proxy manager thread.
        manager = Thread(name='proxy-manager',
                         target=self.__proxy_manager)
        manager.daemon = True
        manager.start()

        # Start proxy tester request validation threads.
        for i in range(args.tester_count):
            tester = Thread(name='proxy-tester-{:02}'.format(i),
                            target=self.__proxy_tester)
            tester.daemon = True
            tester.start()

    # Background handler for completed proxy test requests.
    def __proxy_test_callback(self, sess, resp):
        if resp.status_code in self.STATUS_BANLIST:
            resp.banned = True
        else:
            resp.banned = False

    # Create a new test request and add it to the queue.
    def __test_proxy(self, proxy, test_url, callback, host=True):
        headers = self.CLIENT_HEADERS.copy()
        if host:
            headers['host'] = self.POKEMON_HOST

        future = self.session.get(
            test_url,
            proxies={'http': proxy['url'], 'https': proxy['url']},
            timeout=self.timeout,
            headers=headers,
            background_callback=self.__proxy_test_callback,
            stream=True)

        test_suite = {
            'proxy': proxy,
            'test_url': test_url,
            'future': future,
            'callback': callback,
            'status': ProxyStatus.UNKNOWN,
            'error': None
        }
        self.work_queue.put(test_suite)

    # Check response status and update test suite status.
    # Can return response contents if `get_content` is set to True.
    def __check_response(self, test_suite, get_content=False):
        content = None
        test_suite['status'] = ProxyStatus.ERROR
        try:
            response = test_suite['future'].result()
            if response.banned:
                test_suite['error'] = 'Proxy seems to be banned.'
                test_suite['status'] = ProxyStatus.BANNED
            else:
                test_suite['status'] = ProxyStatus.OK
                if get_content:
                    content = response.content

            response.close()
            # XXX: Memory leaks.
            del response
        except ConnectTimeout:
            test_suite['error'] = 'Connection timed out.'
            test_suite['status'] = ProxyStatus.TIMEOUT
        except ConnectionError:
            test_suite['error'] = 'Failed to connect.'
        except Exception as e:
            test_suite['error'] = e.message

        # XXX: Memory leaks.
        del test_suite['future']
        return content

    def __check_anonymity(self, test_suite):
        content = self.__check_response(test_suite, get_content=True)

        if content:
            result = parse_azevn(content)
            if result['remote_addr'] == self.local_ip:
                test_suite['error'] = 'Non-anonymous proxy.'
                test_suite['status'] = ProxyStatus.ERROR

            elif result['x_unity_version'] != self.UNITY_VERSION:
                test_suite['error'] = 'Bad headers.'
                test_suite['status'] = ProxyStatus.ERROR

            elif result['user_agent'] != self.USER_AGENT:
                test_suite['error'] = 'Bad user-agent.'
                test_suite['status'] = ProxyStatus.ERROR

        # del content
        test_suite['proxy']['anonymous'] = test_suite['status']

    def __check_niantic(self, test_suite):
        content = self.__check_response(test_suite, True)
        if not content:
            test_suite['error'] = 'Unable to validate Niantic response.'
            test_suite['status'] = ProxyStatus.ERROR
        elif self.NIANTIC_KEYWORD not in content:
            test_suite['error'] = 'Retrieved an invalid Niantic response.'
            test_suite['status'] = ProxyStatus.ERROR

        # del content
        test_suite['proxy']['niantic'] = test_suite['status']

    def __check_ptc_login(self, test_suite):
        content = self.__check_response(test_suite, True)
        if not content:
            test_suite['error'] = 'Unable to validate PTC login response.'
            test_suite['status'] = ProxyStatus.ERROR
        elif self.PTC_LOGIN_KEYWORD not in content:
            test_suite['error'] = 'Retrieved an invalid PTC login response.'
            test_suite['status'] = ProxyStatus.ERROR

        # del content
        test_suite['proxy']['ptc_login'] = test_suite['status']

    def __check_ptc_signup(self, test_suite):
        content = self.__check_response(test_suite, True)
        if not content:
            test_suite['error'] = 'Unable to validate PTC sign-up response.'
            test_suite['status'] = ProxyStatus.ERROR
        elif self.PTC_SIGNUP_KEYWORD not in content:
            test_suite['error'] = 'Retrieved an invalid PTC sign-up response.'
            test_suite['status'] = ProxyStatus.ERROR

        # del content
        test_suite['proxy']['ptc_signup'] = test_suite['status']

    # Used by proxy-tester thread(s)...
    def __check_proxy_test(self):
        test_suite = self.work_queue.get()

        # Call respective test callback method.
        test_suite['callback'](test_suite)

        return test_suite

    # Send request to proxy judge.
    def __test_anonymity(self, proxy):
        self.__test_proxy(proxy, self.proxy_judge, self.__check_anonymity,
                          host=False)

    # Send request to Niantic.
    def __test_niantic(self, proxy):
        self.__test_proxy(proxy, self.NIANTIC_URL, self.__check_niantic)

    # Send request to PTC.
    def __test_ptc_login(self, proxy):
        self.__test_proxy(proxy, self.PTC_LOGIN_URL, self.__check_ptc_login)

    # Send request to PTC sign-up website.
    def __test_ptc_signup(self, proxy):
        self.__test_proxy(proxy, self.PTC_SIGNUP_URL, self.__check_ptc_signup,
                          host=False)

    def __proxy_manager(self):
        notice_timer = default_timer()
        loop_counter = 0
        while True:
            now = default_timer()

            # Print statistics regularly.
            if now >= notice_timer + self.notice_interval:
                log.info('Statistics: %d good and %d bad proxies.',
                         self.statistics['valid'], self.statistics['fail'])
                notice_timer = now

            queue_size = self.work_queue.qsize()
            log.info('Proxy manager running: %d tests enqueued.', queue_size)

            try:
                with self.proxy_updates_lock:
                    # Upsert updated proxies into database.
                    if len(self.proxy_updates) > 0:
                        proxies = self.proxy_updates.values()
                        result = False
                        with Proxy.database().atomic():
                            query = Proxy.insert_many(proxies).upsert()
                            result = query.execute()

                        if result:
                            log.info('Upserted %d proxies to database.',
                                     len(proxies))
                        else:
                            log.warning('Failed to upsert %d proxies.',
                                        len(proxies))
                        self.proxy_updates = {}

                    # Request more proxies to test.
                    refill = self.max_concurrency - queue_size

                    loop_counter += 1
                    if loop_counter > 20:
                        log.info('Flushing request pool...')
                        if queue_size > 0:
                            refill = 0
                        else:
                            log.info('Request pool flushed.')
                            loop_counter = 0
                            time.sleep(3)

                    if refill > 0:
                        refill = min(refill, self.max_concurrency)
                        proxylist = Proxy.get_scan(refill, self.proxy_tests)
                        count = 0
                        for proxy in proxylist:
                            self.proxy_tests.append(proxy['hash'])
                            self.test_proxy(proxy)
                            count += 1

                        log.info('Added %d proxies for testing.', count)

            except Exception as e:
                log.exception('Exception in proxy manager: %s.', e)

            if self.running.is_set():
                log.info('Proxy manager shutting down...')
                self.__shutdown()
                break

            time.sleep(5)

    def __update_proxy(self, proxy, valid=False):
        proxy['scan_date'] = datetime.utcnow()
        if valid:
            proxy['fail_count'] = 0
            self.statistics['valid'] += 1
        else:
            proxy['fail_count'] += 1
            self.statistics['fail'] += 1

        proxy = Proxy.db_format(proxy)
        with self.proxy_updates_lock:
            self.proxy_tests.remove(proxy['hash'])
            self.proxy_updates[proxy['hash']] = proxy

    def __proxy_tester(self):
        log.info('Proxy tester started.')

        while True:
            if self.running.is_set():
                log.debug('Proxy tester shutdown.')
                break

            test_suite = self.__check_proxy_test()

            proxy = test_suite['proxy']
            error = test_suite['error']
            # XXX: Memory leaks.
            del test_suite
            fail = False
            if (not self.disable_anonymity and
                    proxy['anonymous'] != ProxyStatus.OK):
                fail = True
            elif proxy['niantic'] == ProxyStatus.UNKNOWN:
                self.__test_niantic(proxy)
            elif proxy['niantic'] != ProxyStatus.OK:
                fail = True
            elif proxy['ptc_login'] == ProxyStatus.UNKNOWN:
                self.__test_ptc_login(proxy)
            elif proxy['ptc_login'] != ProxyStatus.OK:
                fail = True
            elif proxy['ptc_signup'] == ProxyStatus.UNKNOWN:
                self.__test_ptc_signup(proxy)
            elif proxy['ptc_signup'] != ProxyStatus.OK:
                fail = True
            else:
                log.debug('Proxy %s passed all tests.', proxy['url'])
                self.__update_proxy(proxy, valid=True)

            if fail:
                log.debug('Proxy %s failed test: %s', proxy['url'], error)
                self.__update_proxy(proxy)

    def __shutdown(self):
        count = 0
        while True:
            try:
                test_suite = self.work_queue.get_nowait()
                test_suite['future'].cancel()
                count += 1
            except Empty:
                break

        if count:
            log.info('Cancelled %d tests present in work queue.', count)
