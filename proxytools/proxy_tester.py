#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import requests
import time

from datetime import datetime
from queue import Queue, Empty

from requests.adapters import HTTPAdapter
from requests.packages import urllib3
from requests.exceptions import ConnectionError, ConnectTimeout
from timeit import default_timer
from threading import Event, Lock, Thread

from models import ProxyStatus, Proxy
from utils import export_file, parse_azevn


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
        self.debug = args.verbose
        self.timeout = args.tester_timeout
        self.max_concurrency = args.tester_max_concurrency
        self.disable_anonymity = args.tester_disable_anonymity
        self.notice_interval = args.tester_notice_interval

        self.proxy_judge = args.proxy_judge
        self.local_ip = args.local_ip

        self.running = Event()
        self.test_queue = Queue()
        self.test_hashes = []
        self.proxy_updates_lock = Lock()
        self.proxy_updates = {}

        self.statistics = {
            'valid': 0,
            'fail': 0
        }

        urllib3.disable_warnings()
        self.retries = urllib3.Retry(
            total=args.tester_retries,
            backoff_factor=args.tester_backoff_factor,
            status_forcelist=self.STATUS_FORCELIST)

        # Start proxy manager thread.
        manager = Thread(name='proxy-manager',
                         target=self.__proxy_manager)
        manager.daemon = True
        manager.start()

        # Start proxy tester request validation threads.
        for i in range(args.tester_max_concurrency):
            tester = Thread(name='proxy-tester-{:03}'.format(i),
                            target=self.__proxy_tester)
            tester.daemon = True
            tester.start()

    # Make HTTP request using selected proxy.
    def __test_proxy(self, session, proxy, test_url, callback, host=False):
        result = {
            'status': ProxyStatus.UNKNOWN,
            'message': None
        }

        headers = self.CLIENT_HEADERS.copy()
        if host:
            headers['host'] = self.POKEMON_HOST

        response = None
        try:
            response = session.get(
                test_url,
                headers=headers,
                timeout=self.timeout,
                verify=False)

            if response.status_code in self.STATUS_BANLIST:
                result['status'] = ProxyStatus.BANNED
                result['message'] = 'Proxy seems to be banned.'

        except ConnectTimeout:
            result['status'] = ProxyStatus.TIMEOUT
            result['message'] = 'Connection timed out.'
        except ConnectionError:
            result['status'] = ProxyStatus.ERROR
            result['message'] = 'Failed to connect.'
        except Exception as e:
            result['status'] = ProxyStatus.ERROR
            result['message'] = e.message

        if response:
            # This needs to be here for callback to update proxy status.
            callback(proxy, result, response.content)
            response.close()

        if result['status'] != ProxyStatus.OK:
            if self.debug:
                log.error('Proxy %s failed: %s',
                          proxy['url'], result['message'])
            return False
        else:
            log.info('Proxy %s is valid: %s', proxy['url'], result['message'])
            return True

    def __check_anonymity(self, proxy, result, content):
        if not content:
            result['status'] = ProxyStatus.ERROR
            result['message'] = 'Unable to validate proxy anonymity response.'
        else:
            azenv = parse_azevn(content)
            if azenv['remote_addr'] == self.local_ip:
                result['status'] = ProxyStatus.ERROR
                result['message'] = 'Non-anonymous proxy.'
            elif azenv['x_unity_version'] != self.UNITY_VERSION:
                result['status'] = ProxyStatus.ERROR
                result['message'] = 'Bad headers.'
                export_file('anonymity_response.txt', content)
            elif azenv['user_agent'] != self.USER_AGENT:
                result['status'] = ProxyStatus.ERROR
                result['message'] = 'Bad user-agent.'
                export_file('anonymity_response.txt', content)
            else:
                result['status'] = ProxyStatus.OK
                result['message'] = 'Passed anonymity test.'

        proxy['anonymous'] = result['status']

    def __check_niantic(self, proxy, result, content):
        if not content:
            result['status'] = ProxyStatus.ERROR
            result['message'] = 'Unable to validate Niantic response.'
        elif self.NIANTIC_KEYWORD not in content:
            result['status'] = ProxyStatus.ERROR
            result['message'] = 'Retrieved an invalid Niantic response.'
            export_file('niantic_response.txt', content)
        else:
            result['status'] = ProxyStatus.OK
            result['message'] = 'Passed Niantic test.'

        proxy['niantic'] = result['status']

    def __check_ptc_login(self, proxy, result, content):
        if not content:
            result['status'] = ProxyStatus.ERROR
            result['message'] = 'Unable to validate PTC login response.'
        elif self.PTC_LOGIN_KEYWORD not in content:
            result['status'] = ProxyStatus.ERROR
            result['message'] = 'Retrieved an invalid PTC login response.'
            export_file('ptc_login_response.txt', content)
        else:
            result['status'] = ProxyStatus.OK
            result['message'] = 'Passed PTC login test.'

        proxy['ptc_login'] = result['status']

    def __check_ptc_signup(self, proxy, result, content):
        if not content:
            result['status'] = ProxyStatus.ERROR
            result['message'] = 'Unable to validate PTC sign-up response.'
        elif self.PTC_SIGNUP_KEYWORD not in content:
            result['status'] = ProxyStatus.ERROR
            result['message'] = 'Retrieved an invalid PTC sign-up response.'
            export_file('ptc_signup_response.txt', content)
        else:
            result['status'] = ProxyStatus.OK
            result['message'] = 'Passed PTC sign-up test.'

        proxy['ptc_signup'] = result['status']

    def __proxy_manager(self):
        notice_timer = default_timer()
        while True:
            now = default_timer()

            # Print statistics regularly.
            if now >= notice_timer + self.notice_interval:
                log.info('Statistics: %d good and %d bad proxies.',
                         self.statistics['valid'], self.statistics['fail'])
                notice_timer = now

            queue_size = self.test_queue.qsize()
            log.info('%d proxy tests running and %d tests enqueued.',
                     len(self.test_hashes), queue_size)

            try:
                with self.proxy_updates_lock:
                    # Upsert updated proxies into database.
                    if len(self.proxy_updates) > 10:
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

                    if refill > 0:
                        refill = min(refill, self.max_concurrency)
                        proxylist = Proxy.get_scan(refill, self.test_hashes)
                        count = 0
                        for proxy in proxylist:
                            self.test_queue.put(proxy)
                            self.test_hashes.append(proxy['hash'])
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
            self.test_hashes.remove(proxy['hash'])
            self.proxy_updates[proxy['hash']] = proxy

    def __run_tests(self, proxy):
        result = True

        session = requests.Session()

        session.mount('http://', HTTPAdapter(max_retries=self.retries))
        session.mount('https://', HTTPAdapter(max_retries=self.retries))

        session.proxies = {'http': proxy['url'], 'https': proxy['url']}

        # Send request to proxy judge.
        if not self.disable_anonymity:
            result = self.__test_proxy(
                session, proxy, self.proxy_judge, self.__check_anonymity)

        # Send request to Niantic.
        if result:
            result = self.__test_proxy(
                session, proxy, self.NIANTIC_URL, self.__check_niantic,
                host=True)

        # Send request to PTC.
        if result:
            result = self.__test_proxy(
                session, proxy, self.PTC_LOGIN_URL, self.__check_ptc_login,
                host=True)

        # Send request to PTC sign-up website.
        if result:
            result = self.__test_proxy(
                session, proxy, self.PTC_SIGNUP_URL, self.__check_ptc_signup)

        self.__update_proxy(proxy, valid=result)
        session.close()
        return result

    def __proxy_tester(self):
        log.info('Proxy tester started.')

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
            start = default_timer()
            self.__run_tests(proxy)
            log.debug('Took %.3f seconds to test proxy: %s',
                      default_timer() - start, proxy['url'])

    def __shutdown(self):
        count = 0
        while True:
            try:
                self.test_queue.get_nowait()
                count += 1
            except Empty:
                break

        if count:
            log.info('Cancelled %d tests present in work queue.', count)
