#!/usr/bin/env python3
"""First-run setup for local test; creates random secrets, never overwrites .env."""
from pathlib import Path
import secrets

project = Path(__file__).resolve().parents[1]
path = project / '.env'
if path.exists():
    print('.env existe déjà. Rien à modifier.')
    raise SystemExit(0)
admin = secrets.token_urlsafe(32)
robot = secrets.token_urlsafe(32)
db = secrets.token_urlsafe(32)
content = (project / '.env.example').read_text(encoding='utf-8')
content = content.replace('REPLACE_WITH_LONG_RANDOM_ADMIN_PASSWORD', admin)
content = content.replace('REPLACE_WITH_LONG_RANDOM_ROBOT_SECRET', robot)
content = content.replace('REPLACE_WITH_LONG_RANDOM_DATABASE_PASSWORD', db)
content += '\n# Mode local : stockage SQLite (Docker remplace DATABASE_URL par PostgreSQL)\nDATABASE_URL=sqlite:///./data/lifeai.sqlite3\nDATA_DIR=./data\n'
path.write_text(content,encoding='utf-8')
try: path.chmod(0o600)
except OSError: pass
print('Configuration locale créée : .env')
print('Compte administrateur : admin')
print('Mot de passe administrateur :',admin)
print('Clé du simulateur :',robot)
print('Conserve ces informations en lieu sûr ; elles ne seront pas affichées automatiquement ensuite.')
