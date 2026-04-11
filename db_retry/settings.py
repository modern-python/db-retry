import os


def get_retries_number() -> int:
    return int(os.getenv("DB_RETRY_RETRIES_NUMBER", "3"))
