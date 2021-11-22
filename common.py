import os
from datetime import datetime


def read_from_file(path: str):
    with open(path) as f:
        return f.read().strip('\n')


def get_time_str():
    return str(datetime.now()).split('.')[0]


def get_elapsed_sec(start_time) -> float:
    return (datetime.now() - start_time).total_seconds()


def split_on_last_pattern(string: str, pattern: str) -> ():
    last_piece = string.split(pattern)[-1]  # domain.com/image.jpg -> jpg
    leading_chunks = string.split(pattern)[:-1]  # [domain, com/image]
    leading_piece = pattern.join(leading_chunks)  # domain.com/image
    return leading_piece, last_piece  # [domain.com/image, jpg]


def get_thread_url(thread_no):
    thread_url = Constants.ROOT_DOMAIN + Constants.CAUTION_PATH + '/' + str(thread_no)
    return thread_url


def check_dir_exists(dir_path: str):
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
        return False  # Didn't exist, but created one.
    else:
        return True  # Already exists.


def log(message: str, log_path: str, has_tst: bool = False):
    dir_path = split_on_last_pattern(log_path, '/')[0]
    check_dir_exists(dir_path)

    with open(log_path, 'a') as f:
        if has_tst:
            message += '\t(%s)' % get_time_str()
        f.write(message + '\n')
    print(message)


class Constants:
    DRIVER_PATH = read_from_file('DRIVER_PATH.pv')
    ROOT_DOMAIN = read_from_file('ROOT_DOMAIN.pv')
    LOGIN_PATH = read_from_file('LOGIN_PATH.pv')
    LOG_PATH = read_from_file('LOG_PATH.pv')
    LOG_FILE = 'log-fs.pv'
    CAUTION_PATH = '/caution'

    # BeautifulSoup parsing format
    HTML_PARSER = 'html.parser'
