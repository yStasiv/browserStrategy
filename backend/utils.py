import logging

import colorlog
from passlib.context import CryptContext

# Ініціалізуємо контекст для хешування з використанням bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:

    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Create handler via colorlog
    console_handler = colorlog.StreamHandler()
    console_handler.setLevel(logging.DEBUG)

    # Set log format
    console_formatter = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s:%(levelname)s - %(filename)s:%(lineno)d %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        log_colors={
            "DEBUG": "white",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold_red",
        },
    )
    console_handler.setFormatter(console_formatter)

    # Create file hendler
    file_handler = logging.FileHandler("game.log")
    file_handler.setLevel(logging.DEBUG)

    # Set formatters for file
    file_formatter = logging.Formatter(
        "%(asctime)s:%(levelname)s - %(filename)s:%(lineno)d %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)

    # Add handlers to the logger
    logger.addHandler(console_handler)
    # logger.addHandler(file_handler)

    return logger


# def setup_logger_wo_colorlog(name: str) -> logging.Logger:
#     logger = logging.getLogger(name)
#     logger.setLevel(logging.INFO)

#     #  Create handlers
#     file_handler = logging.FileHandler('game.log')
#     stream_handler = logging.StreamHandler()

#     # Set formatters
#     formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
#     file_handler.setFormatter(formatter)
#     stream_handler.setFormatter(formatter)

#     # Add handlers to the logger
#     logger.addHandler(file_handler)
#     logger.addHandler(stream_handler)

#     return logger
