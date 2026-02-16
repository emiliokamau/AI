#!/usr/bin/env python
"""Create a 'dev' user in the MySQL database for admin access.

Usage:
  python create_dev_user.py --username admin --password 'Secret123!'

If you omit --password the script will prompt you.
"""
import argparse
import getpass
import os
from db import db_connect, IntegrityError
from datetime import datetime
from passlib.hash import pbkdf2_sha256

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "medical_ai")


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--username', '-u', required=True)
    p.add_argument('--password', '-p', help='password for the dev user')
    p.add_argument('--db-host', default=DB_HOST)
    p.add_argument('--db-port', type=int, default=DB_PORT)
    p.add_argument('--db-user', default=DB_USER)
    p.add_argument('--db-password', default=DB_PASSWORD)
    p.add_argument('--db-name', default=DB_NAME)
    args = p.parse_args()

    password = args.password
    if not password:
        password = getpass.getpass('Password for new dev user: ')

    if not password:
        print('Password required')
        return

    pw_hash = pbkdf2_sha256.hash(password)

    os.environ["DB_HOST"] = args.db_host
    os.environ["DB_PORT"] = str(args.db_port)
    os.environ["DB_USER"] = args.db_user
    os.environ["DB_PASSWORD"] = args.db_password
    os.environ["DB_NAME"] = args.db_name
    conn = db_connect()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users (username, password_hash, role, created_at) VALUES (%s, %s, %s, %s)",
                    (args.username, pw_hash, 'dev', datetime.utcnow()))
        conn.commit()
        print('Created dev user:', args.username)
    except IntegrityError:
        print('Error: username already exists')
    except Exception as e:
        print('Error:', e)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
