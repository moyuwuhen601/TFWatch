import argparse
from getpass import getpass

from cryptography.fernet import Fernet
from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select

from .config import Config
from .db import database
from .models import User
from .security import passwords


def main():
    parser = argparse.ArgumentParser(prog="tfwatch")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("key")
    admin = commands.add_parser("create-admin")
    admin.add_argument("email")
    args = parser.parse_args()
    if args.command == "key":
        print(Fernet.generate_key().decode())
        return

    try:
        email = validate_email(args.email, check_deliverability=False).normalized.lower()
    except EmailNotValidError as error:
        parser.error(str(error))

    with database(Config().database_url)() as session:
        if session.scalar(select(User.id).where(User.email == email)) is not None:
            parser.error("该邮箱已被使用。请使用新的管理员邮箱。")
        password = getpass("管理员密码: ")
        if not 10 <= len(password) <= 128 or password != getpass("确认密码: "):
            parser.error("密码需为 10–128 个字符，且两次输入必须一致。")
        session.add(User(email=email, password_hash=passwords.hash(password), is_admin=True))
        session.commit()
    print("管理员已创建。")


if __name__ == "__main__":
    main()
