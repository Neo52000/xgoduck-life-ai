"""Invoke one daily bounded curiosity cycle against the *local* Life AI service.

Use from a host cron entry or `docker compose exec -T app python -m lifeai.run_cycle`.
Credentials are read from env / .env, never printed or placed in CLI flags.
"""
import os
import sys
import httpx
from dotenv import load_dotenv


def main():
    load_dotenv()
    url = os.environ.get('LIFEAI_INTERNAL_URL', 'http://127.0.0.1:8000').rstrip('/')
    if not url.startswith(('http://127.0.0.1:', 'http://localhost:', 'http://app:')):
        raise ValueError('LIFEAI_INTERNAL_URL doit viser un service privé/local')
    password = os.environ.get('ADMIN_PASSWORD', '')
    user = os.environ.get('ADMIN_USER', 'admin')
    if not password:
        print('ADMIN_PASSWORD manquant', file=sys.stderr)
        return 1
    try:
        with httpx.Client(timeout=45) as client:
            response = client.post(url + '/api/learning/cycle', auth=(user, password))
            response.raise_for_status()
            payload = response.json()
            print('cycle:', payload.get('status'), 'processed:', payload.get('processed'))
            return 0
    except (httpx.HTTPError, ValueError) as exc:
        print('Erreur de cycle:', type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
