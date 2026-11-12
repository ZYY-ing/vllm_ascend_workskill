"""Optional paid smoke request to a user-selected Chat Completions judge; no key output."""
import os
import sys
import json
from urllib.parse import urlsplit


def main():
    if '--help' in sys.argv:
        print('Set HALLUSION_JUDGE_BASE_URL/MODEL/API_KEY, then run this script. '
              'Sends one real API request; use only when authorized. Exit: '
              '0=nonempty reply, 2=config, 11=auth, 12=API/model/quota, 13=connection/SDK, 14=empty reply.')
        return 0
    required = ('HALLUSION_JUDGE_BASE_URL', 'HALLUSION_JUDGE_MODEL', 'HALLUSION_JUDGE_API_KEY')
    if any(not os.environ.get(k) for k in required):
        print('AUTH_CONFIG_ERROR: required private environment variables are missing')
        return 2
    url = urlsplit(os.environ[required[0]])
    if url.scheme not in ('http', 'https') or not url.netloc or url.username or url.password or url.query:
        print('AUTH_CONFIG_ERROR: use a base URL without embedded credentials or query parameters')
        return 2
    try:
        from openai import OpenAI, APIStatusError
    except ImportError:
        print('AUTH_CONNECTION_ERROR: install the modern OpenAI SDK in the selected judge environment')
        return 13
    try:
        client = OpenAI(api_key=os.environ[required[2]], base_url=os.environ[required[0]],
                        timeout=40, max_retries=0)
        # No sampling, thinking or max_tokens override: some judge models reject short output limits.
        response = client.chat.completions.create(model=os.environ[required[1]],
                                                  messages=[{'role': 'user', 'content': 'Reply OK.'}])
        if not response.choices or not response.choices[0].message.content:
            print('AUTH_EMPTY_REPLY: inspect model response fields before scoring')
            return 14
        print('AUTH_OK: nonempty message.content received')
        return 0
    except APIStatusError as exc:
        # Do not print response bodies: gateways may echo headers, URLs or account identifiers.
        print(json.dumps({'status': exc.status_code, 'error': 'API request rejected'}))
        return 11 if exc.status_code == 401 else 12
    except Exception as exc:
        print('AUTH_CONNECTION_ERROR:', type(exc).__name__)
        return 13


if __name__ == '__main__':
    raise SystemExit(main())
