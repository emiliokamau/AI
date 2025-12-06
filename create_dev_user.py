#!/usr/bin/env python
"""Create a 'dev' user in the local `chats.db` for admin access.

Usage:
  python create_dev_user.py --username admin --password 'Secret123!'

If you omit --password the script will prompt you.
"""
import argparse
import getpass
import sqlite3
from datetime import datetime
from passlib.hash import pbkdf2_sha256

DB = 'chats.db'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--username', '-u', required=True)
    p.add_argument('--password', '-p', help='password for the dev user')
    p.add_argument('--db', default=DB, help='path to chats.db')
    args = p.parse_args()

    password = args.password
    if not password:
        password = getpass.getpass('Password for new dev user: ')

    if not password:
        print('Password required')
        return

    pw_hash = pbkdf2_sha256.hash(password)

    conn = sqlite3.connect(args.db)
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                    (args.username, pw_hash, 'dev', datetime.utcnow().isoformat()))
        conn.commit()
        print('Created dev user:', args.username)
    except sqlite3.IntegrityError as e:
        print('Error: username already exists')
    except Exception as e:
        print('Error:', e)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
