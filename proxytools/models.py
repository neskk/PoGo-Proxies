#!/usr/bin/python
# -*- coding: utf-8 -*-

import hashlib
import logging
import sys

from peewee import (DatabaseProxy, Model, OperationalError, IntegrityError, CompositeKey,
                    CharField, DateTimeField,
                    IntegerField, SmallIntegerField, BigIntegerField)
from playhouse.pool import PooledMySQLDatabase
from playhouse.migrate import migrate, MySQLMigrator

from datetime import datetime, timedelta

from .utils import ip2int, int2ip


log = logging.getLogger(__name__)

# http://docs.peewee-orm.com/en/latest/peewee/database.html#dynamically-defining-a-database
db = DatabaseProxy()
db_schema_version = 3
db_step = 250

# Connect to a MySQL database on network.
def init_database(db_name, db_host, db_port, db_user, db_pass):
    log.info('Connecting to MySQL database on %s:%i...', db_host, db_port)

    database = PooledMySQLDatabase(
        db_name,
        user=db_user,
        password=db_pass,
        host=db_host,
        port=db_port,
        stale_timeout=60,
        max_connections=None,
        charset='utf8mb4')

    # Initialize Database Proxy
    db.initialize(database)

    try:
        verify_database_schema()
        verify_table_encoding(db_name)
    except Exception as e:
        log.exception('Failed to verify database schema: %s', e)
        sys.exit(1)
    return db

# Custom fields
class Utf8mb4CharField(CharField):
    def __init__(self, max_length=191, *args, **kwargs):
        self.max_length = max_length
        super(CharField, self).__init__(*args, **kwargs)


class UBigIntegerField(BigIntegerField):
    field_type = 'bigint unsigned'


class UIntegerField(IntegerField):
    field_type = 'int unsigned'


class USmallIntegerField(SmallIntegerField):
    field_type = 'smallint unsigned'


class BaseModel(Model):
    class Meta:
        database = db

    @classmethod
    def database(cls):
        return cls._meta.database

    @classmethod
    def get_all(cls):
        return [m for m in cls.select().dicts()]


class ProxyProtocol:
    HTTP = 0
    SOCKS4 = 1
    SOCKS5 = 2


class ProxyStatus:
    OK = 0
    UNKNOWN = 1
    ERROR = 2
    TIMEOUT = 3
    BANNED = 4


class Proxy(BaseModel):
    hash = UIntegerField(unique=True)
    ip = UIntegerField()
    port = USmallIntegerField()
    protocol = USmallIntegerField(index=True)
    username = Utf8mb4CharField(null=True, max_length=32)
    password = Utf8mb4CharField(null=True, max_length=32)
    insert_date = DateTimeField(index=True, default=datetime.utcnow)
    scan_date = DateTimeField(index=True, null=True)
    latency = UIntegerField(index=True, null=True)
    fail_count = UIntegerField(index=True, default=0)
    anonymous = USmallIntegerField(index=True, default=ProxyStatus.UNKNOWN)
    niantic = USmallIntegerField(index=True, default=ProxyStatus.UNKNOWN)
    ptc_login = USmallIntegerField(index=True, default=ProxyStatus.UNKNOWN)
    ptc_signup = USmallIntegerField(index=True, default=ProxyStatus.UNKNOWN)

    class Meta:
        primary_key = CompositeKey('ip', 'port')

    @staticmethod
    def db_format(proxy):
        return {
            'hash': proxy['hash'],
            'ip': ip2int(proxy['ip']),
            'port': proxy['port'],
            'protocol': proxy['protocol'],
            'username': proxy['username'],
            'password': proxy['password'],
            'insert_date': proxy.get('insert_date', datetime.utcnow()),
            'scan_date': proxy.get('scan_date', None),
            'latency': proxy.get('latency', None),
            'fail_count': proxy.get('fail_count', 0),
            'anonymous': proxy.get('anonymous', ProxyStatus.UNKNOWN),
            'niantic': proxy.get('niantic', ProxyStatus.UNKNOWN),
            'ptc_login': proxy.get('ptc_login', ProxyStatus.UNKNOWN),
            'ptc_signup': proxy.get('ptc_signup', ProxyStatus.UNKNOWN)}

    @staticmethod
    def generate_hash(proxy):
        # Check if proxy is already formatted for database.
        if isinstance(proxy['ip'], int):
            ip = int2ip(proxy['ip'])
            port = str(proxy['port'])
        else:
            ip = proxy['ip']
            port = proxy['port']

        hasher = hashlib.md5()
        hasher.update(ip.encode('utf-8'))
        hasher.update(port.encode('utf-8'))
        if proxy['username']:
            hasher.update(proxy['username'])
        if proxy['password']:
            hasher.update(proxy['password'])

        # 4 bit * 8 hex chars = 32 bit = 4 bytes
        return int(hasher.hexdigest()[:8], 16)

    @staticmethod
    def url_format(proxy, no_protocol=False):
        proxy_url = '{}:{}'.format(proxy['ip'], proxy['port'])
        if proxy['username']:
            proxy_url = '{}:{}@{}'.format(
                proxy['username'], proxy['password'], proxy_url)

        if not no_protocol:
            if proxy['protocol'] == ProxyProtocol.HTTP:
                protocol = 'http'
            elif proxy['protocol'] == ProxyProtocol.SOCKS4:
                protocol = 'socks4'
            else:
                protocol = 'socks5'

            proxy_url = '{}://{}'.format(protocol, proxy_url)

        return proxy_url

    # Proxychains format: socks5 192.168.67.78 1080 lamer secret
    @staticmethod
    def url_format_proxychains(proxy):
        proxy_url = '{} {}'.format(proxy['ip'], proxy['port'])
        if proxy['username']:
            proxy_url = '{} {} {}'.format(
                proxy_url, proxy['username'], proxy['password'])

        if proxy['protocol'] == ProxyProtocol.HTTP:
            protocol = 'http'
        elif proxy['protocol'] == ProxyProtocol.SOCKS4:
            protocol = 'socks4'
        else:
            protocol = 'socks5'

        proxy_url = '{} {}'.format(protocol, proxy_url)

        return proxy_url

    @staticmethod
    def get_by_ip(ip):
        try:
            query = (Proxy
                     .select_query()
                     .where(Proxy.ip == ip2int(ip))
                     .dicts())
            if len(query) > 0:
                return query[0]

        except OperationalError as e:
            log.exception('Failed to get proxy by IP from database: %s', e)

        return None

    @staticmethod
    def get_valid(limit=1000, anonymous=True, age_secs=3600, protocol=None):
        result = []
        max_age = datetime.utcnow() - timedelta(seconds=age_secs)
        conditions = ((Proxy.scan_date > max_age) &
                      (Proxy.fail_count == 0) &
                      (Proxy.niantic == ProxyStatus.OK) &
                      (Proxy.ptc_login == ProxyStatus.OK) &
                      (Proxy.ptc_signup == ProxyStatus.OK))
        if anonymous:
            conditions &= (Proxy.anonymous == ProxyStatus.OK)

        if protocol is not None:
            conditions &= (Proxy.protocol == protocol)

        try:
            query = (Proxy
                     .select()
                     .where(conditions)
                     .order_by(Proxy.latency.asc())
                     .limit(limit)
                     .dicts())

            for proxy in query:
                proxy['ip'] = int2ip(proxy['ip'])
                proxy['url'] = Proxy.url_format(proxy)
                result.append(proxy)

        except OperationalError as e:
            log.exception('Failed to get valid proxies from database: %s', e)

        return result

    @staticmethod
    def get_scan(limit=1000, exclude=[], age_secs=3600, protocol=None):
        result = []
        min_age = datetime.utcnow() - timedelta(seconds=age_secs)
        conditions = (((Proxy.scan_date < min_age) & (Proxy.fail_count < 5)) |
                      Proxy.scan_date.is_null())
        if exclude:
            conditions &= (Proxy.hash.not_in(exclude))

        if protocol is not None:
            conditions &= (Proxy.protocol == protocol)

        try:
            query = (Proxy
                     .select()
                     .where(conditions)
                     .order_by(Proxy.scan_date.asc(),
                               Proxy.insert_date.asc())
                     .limit(limit)
                     .dicts())

            for proxy in query:
                proxy['ip'] = int2ip(proxy['ip'])
                proxy['url'] = Proxy.url_format(proxy)
                result.append(proxy)

        except OperationalError as e:
            log.exception('Failed to get proxies to scan from database: %s', e)

        return query

    # Filter proxylist and insert only new proxies to the database.
    @staticmethod
    def insert_new(proxylist):
        log.info('Processing %d proxies into the database.', len(proxylist))
        count = 0
        for idx in range(0, len(proxylist), db_step):
            batch = proxylist[idx:idx + db_step]
            proxies = [p['hash'] for p in batch]
            try:
                query = (Proxy
                         .select(Proxy.hash)
                         .where(Proxy.hash << proxies)
                         .dicts())

                db_proxies = [dbp['hash'] for dbp in query]

                new_proxies = [Proxy.db_format(x)
                               for x in batch if x['hash'] not in db_proxies]
                if not new_proxies:
                    continue

                with db.atomic():
                    query = Proxy.insert_many(new_proxies).execute()
                    if query:
                        count += len(new_proxies)
            except IntegrityError as e:
                log.exception('Unable to insert new proxies: %s', e)
            except OperationalError as e:
                log.exception('Failed to insert new proxies: %s', e)

        log.info('Inserted %d new proxies into the database.', count)

    @staticmethod
    def clean_failed():
        rows = 0
        try:
            with db:
                query = (Proxy
                         .delete()
                         .where(Proxy.fail_count >= 5))
                rows = query.execute()
        except OperationalError as e:
            log.exception('Failed to delete failed proxies: %s', e)

        log.info('Deleted %d failed proxies from database.', rows)

    @staticmethod
    def rehash_all():
        rows = 0
        query = Proxy.select().dicts().execute()
        log.info('Re-hashing proxies on the database.')
        for proxy in query:
            try:
                proxy_hash = Proxy.generate_hash(proxy)
                if proxy_hash != proxy['hash']:
                    proxy['hash'] = proxy_hash
                    query = (Proxy
                             .update(hash=proxy_hash)
                             .where((Proxy.ip == proxy['ip']) &
                                    (Proxy.port == proxy['port'])))
                    if query.execute():
                        rows += 1

            except Exception as e:
                log.exception('Failed to re-hash proxy: %s', e)

        log.info('Re-hashed %d proxies on the database.', rows)


class Version(BaseModel):
    key = Utf8mb4CharField()
    val = SmallIntegerField()

    class Meta:
        primary_key = False

MODELS = [Proxy, Version]

def create_tables():
    with db:
        for table in MODELS:
            if not table.table_exists():
                log.info('Creating database table: %s', table.__name__)
                db.create_tables([table], safe=True)
            else:
                log.debug('Skipping database table %s, it already exists.',
                          table.__name__)


def drop_tables():
    with db:
        db.execute_sql('SET FOREIGN_KEY_CHECKS=0;')
        for table in MODELS:
            if table.table_exists():
                log.info('Dropping database table: %s', table.__name__)
                db.drop_tables([table], safe=True)

        db.execute_sql('SET FOREIGN_KEY_CHECKS=1;')


def migrate_database_schema(old_ver):
    log.info('Detected database version %i, updating to %i...',
             old_ver, db_schema_version)

    with db:
        # Update database schema version.
        query = (Version
                 .update(val=db_schema_version)
                 .where(Version.key == 'schema_version'))
        query.execute()

    # Perform migrations here.
    migrator = MySQLMigrator(db)

    if old_ver < 2:
        # Remove hash field unique index.
        migrate(migrator.drop_index('proxy', 'proxy_hash'))
        # Reset hash field in all proxies.
        Proxy.update(hash=1).execute()
        # Modify column type.
        db.execute_sql(
            'ALTER TABLE `proxy` '
            'CHANGE COLUMN `hash` `hash` INT UNSIGNED NOT NULL;'
        )
        # Re-hash all proxies.
        Proxy.rehash_all()
        # Recreate hash field unique index.
        migrate(migrator.add_index('proxy', ('hash',), True))

    if old_ver < 3:
        # Add response time field.
        migrate(
            migrator.add_column('proxy', 'latency',
                                UIntegerField(index=True, null=True))
        )

    # Always log that we're done.
    log.info('Schema upgrade complete.')
    return True


def verify_database_schema():
    if not Version.table_exists():
        log.info('Database schema is not created, initializing...')
        create_tables()
        Version.insert(key='schema_version', val=db_schema_version).execute()
    else:
        db_ver = Version.get(Version.key == 'schema_version').val

        if db_ver < db_schema_version:
            if not migrate_database_schema(db_ver):
                log.error('Error migrating database schema.')
                sys.exit(1)

        elif db_ver > db_schema_version:
            log.error('Your database version (%i) seems to be newer than '
                      'the code supports (%i).', db_ver, db_schema_version)
            log.error('Upgrade your code base or drop the database.')
            sys.exit(1)


def verify_table_encoding(db_name):
    with db:
        cmd_sql = '''
            SELECT table_name FROM information_schema.tables WHERE
            table_collation != "utf8mb4_unicode_ci"
            AND table_schema = "%s";''' % db_name
        change_tables = db.execute_sql(cmd_sql)

        cmd_sql = 'SHOW tables;'
        tables = db.execute_sql(cmd_sql)

        if change_tables.rowcount > 0:
            log.info('Changing collation and charset on %s tables.',
                     change_tables.rowcount)

            if change_tables.rowcount == tables.rowcount:
                log.info('Changing whole database, this might a take while.')

            db.execute_sql('SET FOREIGN_KEY_CHECKS=0;')
            for table in change_tables:
                log.debug('Changing collation and charset on table %s.',
                          table[0])
                cmd_sql = '''
                    ALTER TABLE %s CONVERT TO CHARACTER SET utf8mb4
                    COLLATE utf8mb4_unicode_ci;''' % str(table[0])
                db.execute_sql(cmd_sql)
            db.execute_sql('SET FOREIGN_KEY_CHECKS=1;')
