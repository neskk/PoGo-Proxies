#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

from queue import Queue, Empty
from requests_futures.sessions import FuturesSession
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError, ConnectTimeout
from timeit import default_timer
from threading import Thread, Event

from models import ProxyStatus, Proxy
from utils import parse_azevn

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
    NIANTIC_KEYWORD = '0.95.0'

    PTC_LOGIN_URL = ('https://sso.pokemon.com/sso/login?service='
                     'https%3A%2F%2Fsso.pokemon.com%2Fsso%2Foauth2.0%2F'
                     'callbackAuthorize&locale=en_US')
    PTC_LOGIN_KEYWORD = '"execution"'

    PTC_SIGNUP_URL = 'https://club.pokemon.com/us/pokemon-trainer-club'
    PTC_SIGNUP_KEYWORD = 'Pokémon Trainer Club | Pokemon.com'

    STATUS_FORCELIST = [500, 502, 503, 504]

    def __init__(self, args):
        self.retries = args.tester_retries
        self.backoff_factor = args.tester_backoff_factor
        self.timeout = args.tester_timeout
        self.max_concurrency = args.tester_max_concurrency
        self.disable_anonymity = args.tester_disable_anonymity
        self.notice_interval = args.tester_notice_interval

        self.proxy_judge = args.proxy_judge
        self.local_ip = args.local_ip

        self.work_queue = Queue()
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

        # Start continuous proxy tester thread.
        self.tester = Thread(name='proxy-tester', target=self.__proxy_tester)
        self.tester.daemon = True
        self.tester.start()
        self.running = Event()

    # Background handler for completed proxy test requests.
    def __proxy_test_callback(self, sess, resp):
        banned_status_codes = [403, 409]
        if resp.status_code in banned_status_codes:
            resp.banned = True
        else:
            resp.banned = False

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
            # del response
        except ConnectTimeout:
            test_suite['error'] = 'Connection timed out.'
            test_suite['status'] = ProxyStatus.TIMEOUT
        except ConnectionError:
            test_suite['error'] = 'Failed to connect.'
        except Exception as e:
            test_suite['error'] = e.message

        # XXX: Futures are a source of memory leakage.
        # del test_suite['future']
        return content

    def __check_anonymity(self, test_suite):
        content = self.__check_response(test_suite, get_content=True)

        if content:
            # Let's check the content.
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
            test_suite['error'] = 'Unable to validate PTC login response.'
            test_suite['status'] = ProxyStatus.ERROR
        elif self.NIANTIC_KEYWORD not in content:
            test_suite['error'] = 'Retrieved an invalid PTC login response.'
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

    # Used by consumer thread...
    def __check_proxy_test(self):
        test_suite = self.work_queue.get()

        # Call respective test callback method.
        test_suite['callback'](test_suite)

        return test_suite

    # Send request to proxy judge.
    def test_anonymity(self, proxy):
        self.__test_proxy(proxy, self.proxy_judge, self.__check_anonymity,
                          host=False)

    # Send request to Niantic.
    def test_niantic(self, proxy):
        self.__test_proxy(proxy, self.NIANTIC_URL, self.__check_niantic)

    # Send request to PTC.
    def test_ptc_login(self, proxy):
        self.__test_proxy(proxy, self.PTC_LOGIN_URL, self.__check_ptc_login)

    # Send request to PTC.
    def test_ptc_signup(self, proxy):
        self.__test_proxy(proxy, self.PTC_SIGNUP_URL, self.__check_ptc_signup,
                          host=False)

    def __proxy_tester(self):
        valid_count = 0
        fail_count = 0
        notice_timer = default_timer()

        log.info('Proxy tester started.')
        while True:
            if self.running.is_set():
                log.info('Proxy tester shutting down...')
                self.shutdown()
                break

            test_suite = self.__check_proxy_test()

            proxy = test_suite['proxy']
            fail = False
            if (not self.disable_anonymity and
                    proxy['anonymous'] != ProxyStatus.OK):
                fail = True
            elif proxy['niantic'] == ProxyStatus.UNKNOWN:
                self.test_niantic(proxy)
            elif proxy['niantic'] != ProxyStatus.OK:
                fail = True
            elif proxy['ptc_login'] == ProxyStatus.UNKNOWN:
                self.test_ptc_login(proxy)
            elif proxy['ptc_login'] != ProxyStatus.OK:
                fail = True
            elif proxy['ptc_signup'] == ProxyStatus.UNKNOWN:
                self.test_ptc_signup(proxy)
            elif proxy['ptc_signup'] != ProxyStatus.OK:
                fail = True
            else:
                log.debug('Proxy %s passed all tests.', proxy['url'])
                proxy['fail_count'] = 0
                Proxy.upsert(proxy)
                valid_count += 1

            if fail:
                log.debug('Proxy %s failed test: %s',
                          proxy['url'], test_suite['error'])
                proxy['fail_count'] += 1
                Proxy.upsert(proxy)
                fail_count += 1

            # del test_suite
            now = default_timer()
            if now >= notice_timer + self.notice_interval:
                log.info('Proxy checker statistics from last %d seconds: '
                         '%d good and %d bad proxies.',
                         self.notice_interval, valid_count, fail_count)
                # Reset statistics to make sure they don't overflow.
                valid_count = 0
                fail_count = 0
                notice_timer = now

    def shutdown(self):
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
