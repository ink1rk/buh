import json
import urllib.error
import urllib.request


class TelegramError(Exception):
    def __init__(self, code, retry_after=0):
        self.code = code
        self.retry_after = retry_after
        super().__init__(f'Telegram API error {code}')


class Telegram:
    def __init__(self, token):
        self._base = 'https://api.telegram.org/bot' + token + '/'

    def call(self, method, **payload):
        request = urllib.request.Request(self._base + method, data=json.dumps(payload).encode(),
                                         headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=35) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            try:
                data = json.loads(exc.read())
            except (ValueError, OSError):
                raise TelegramError(exc.code) from None
        except (OSError, ValueError):
            # The request URL contains a credential: never log exception text.
            raise TelegramError(0) from None
        if not data.get('ok'):
            raise TelegramError(data.get('error_code', 0), data.get('parameters', {}).get('retry_after', 0))
        return data['result']

    def fetch(self, file_id, max_bytes=2_000_000):
        info = self.call('getFile', file_id=file_id)
        path = info.get('file_path') or ''
        if not path or path.startswith('/') or '..' in path.split('/'):
            raise TelegramError(400)
        if (info.get('file_size') or 0) > max_bytes:
            raise TelegramError(400)
        url = self._base.replace('https://api.telegram.org/bot', 'https://api.telegram.org/file/bot', 1) + path
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = response.read(max_bytes + 1)
        except urllib.error.HTTPError as exc:
            raise TelegramError(exc.code) from None
        except (OSError, ValueError):
            raise TelegramError(0) from None
        if not data or len(data) > max_bytes:
            raise TelegramError(400)
        return data

