import os
from datetime import datetime


def read_from_file(path: str):
    with open(path) as f:
        return f.read().strip('\n')


def build_tuple(path: str):
    content = read_from_file(path)
    return tuple(content.split('\n'))


def build_float_tuple(path: str):
    content = read_from_file(path)
    float_list = []
    for element in content.split('\n'):
        try:
            float_list.append(float(element))
        except ValueError:
            print('Error: %s is not a number, adding 0.' % element)
            float_list.append(0.0)
    return tuple(float_list)


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


def log(message: str, log_path: str, has_tst: bool = False, has_print: bool = True):
    dir_path = split_on_last_pattern(log_path, '/')[0]
    check_dir_exists(dir_path)

    with open(log_path, 'a') as f_append:
        if has_tst:
            message += '\t(%s)' % get_time_str()
        f_append.write(message + '\n')
    if has_print:
        print(message)


def trim_logs(log_path: str):
    lines_threshold = 120000
    old_lines = 30000

    if not os.path.isfile(log_path):
        print('Warning: The file does not exist.')
        return

    with open(log_path, 'r') as fin:
        data = fin.read().splitlines(True)
        print('%d lines in %s.' % (len(data), log_path))
    if len(data) > lines_threshold:
        with open(log_path, 'w') as f_write:
            f_write.writelines(data[old_lines:])
            print('Trimmed first %d lines.' % old_lines)


class Constants:
    DRIVER_PATH = read_from_file('DRIVER_PATH.pv')
    ROOT_DOMAIN = read_from_file('ROOT_URL.pv')
    LOGIN_PATH = read_from_file('LOGIN_URL.pv')
    LOG_PATH = read_from_file('LOG_PATH.pv')
    LOG_FILE = 'log-fs.pv'
    CAUTION_PATH = '/caution'

    # BeautifulSoup parsing format
    HTML_PARSER = 'html.parser'
