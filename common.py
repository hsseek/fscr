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


def log(message: str, log_path: str, has_tst: bool = False):
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
    CAUTION_PATH = '/caution'

    # BeautifulSoup parsing format
    HTML_PARSER = 'html.parser'