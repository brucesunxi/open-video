"""Single shared demo account; password hashes and expiring signed sessions."""
import hashlib
import hmac
import os
import secrets
import time

COOKIE = 'studio_session'


def password_hash(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600_000).hex()
    return f'pbkdf2_sha256$600000${salt}${digest}'


def check_password(password, encoded):
    try:
        algorithm, rounds, salt, expected = encoded.split('$')
        if algorithm != 'pbkdf2_sha256' or int(rounds) != 600_000:
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), int(rounds)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def account_enabled():
    return bool(os.getenv('APP_PASSWORD_HASH'))


def required():
    return account_enabled() or bool(os.getenv('APP_TOKEN'))


def signing_key():
    return (os.environ.get('APP_TOKEN', '') + ':' + os.environ.get('APP_PASSWORD_HASH', '')).encode()


def make_session():
    value = f'{int(time.time()) + 8 * 3600}.{secrets.token_hex(16)}'
    return value + '.' + hmac.new(signing_key(), value.encode(), hashlib.sha256).hexdigest()


def valid_session(value):
    try:
        expiry, nonce, signature = value.split('.')
        if int(expiry) <= time.time() or int(expiry) > time.time() + 8 * 3600 + 60:
            return False
        expected = hmac.new(signing_key(), f'{expiry}.{nonce}'.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)
    except (ValueError, TypeError):
        return False
