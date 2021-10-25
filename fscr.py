import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
from bs4 import BeautifulSoup
import collections
import random
import datetime
# Custom scripts
import sqlite
import downloader


def read_from_file(path: str):
    with open(path) as f:
        return f.read().strip('\n')


# urls
DRIVER_PATH = read_from_file('DRIVER_PATH.pv')
ROOT_DOMAIN = read_from_file('ROOT_DOMAIN.pv')
LOGIN_PATH = read_from_file('LOGIN_PATH.pv')
LOG_PATH = read_from_file('LOG_PATH.pv')
CAUTION_PATH = '/caution'
HTML_TIMEOUT = 5

# Credentials
EMAIL = read_from_file('EMAIL.pv')
PW = read_from_file('PW.pv')

# A chrome web driver with headless option
service = Service(DRIVER_PATH)
options = webdriver.ChromeOptions()
options.add_argument('headless')
options.add_argument('disable-gpu')
# options.add_experimental_option("detach", True)
browser = webdriver.Chrome(service=service, options=options)

# Variables regarding randomizing the behavior
# For the same or increasing number of new replies
MIN_SCANNING_COUNT_ON_SESSION = 100
MAX_SCANNING_COUNT_ON_SESSION = 1000
PAUSE_IDLE = 600.0
PAUSE_POWER = 3.5
# For decreasing number of new replies
sum_new_reply_count_last_time = 0
last_pause = 0


def log(message: str):
    with open(LOG_PATH, 'a') as f:
        f.write(message + '\n')
    print(message)


def __tail(iterable, n: int):
    # tail([A, B, C, D, E], 3) returns [E, F, G]
    return iter(collections.deque(iterable, maxlen=n))


def scan(target_id: int, scan_count: int):
    try:
        # Open the page to scan
        browser.get(ROOT_DOMAIN + CAUTION_PATH + "/" + str(target_id))
        wait.until(expected_conditions.presence_of_element_located((By.CLASS_NAME, 'th-contents')))
        try:
            wait.until(expected_conditions.presence_of_element_located((By.CLASS_NAME, 'thread-reply',)))

            # Get the thread list and the scanning targets(the new replies)
            replies_soup = BeautifulSoup(browser.page_source, 'html.parser')
            replies = replies_soup.select('div.thread-reply > div.th-contents')

            # the new_replies is not a bs4.results but a collection.deque
            # It is iterable, but does not have select method.
            # But its elements are Tags so they have select method.
            # 마지막 n개 자르기 위해 iter 함수 쓰지 않았다면 select 2 번으로 한 줄로 끝냈을 것.
            new_replies = __tail(replies, scan_count)

            # Now scan the new replies.
            for reply in new_replies:
                for links in reply.select('a.link'):
                    page_link_url = links['href']
                    downloader.download(page_link_url, str(target_id))
        except Exception as reply_exception:
            exception_last_line = str(reply_exception).splitlines()[-1]
            log('Reply not present on %i: %s' % (target_id, exception_last_line))
            if not exception_last_line.endswith('start_thread'):  # 'start thread' is Harmless.
                try:
                    replies_err_soup = BeautifulSoup(browser.page_source, 'html.parser')
                    log('Error: html structure\n' + replies_err_soup.prettify())
                except Exception as scan_exception:
                    log('Error: Failed to load page source %s: %s' % (target_id, str(scan_exception)))
    except Exception as scan_exception:
        log('Error: Cannot scan %i: %s' % (target_id, str(scan_exception)))
        try:
            replies_err_soup = BeautifulSoup(browser.page_source, 'html.parser')
            log(replies_err_soup.prettify())
        except Exception as scan_exception:
            log('Error: Failed to load page source %s: %s' % (target_id, str(scan_exception)))


def fluctuate(value):
    # Large values: The random multiplier dominant
    # Small values: The random increment dominant
    return value * random.uniform(1.0, 1.5) + random.uniform(1.2, 3.6)


def get_proper_pause(new_reply_count: int):
    return PAUSE_IDLE / ((new_reply_count ** PAUSE_POWER) + 1)


while True:
    # Connect to the database
    thread_db = sqlite.ThreadDb()
    log('MySQL connection opened.')
    thread_id = 0  # For debugging: if thread_id = 0, it has never been assigned.

    try:
        # Open the browser
        browser.get(ROOT_DOMAIN + LOGIN_PATH)

        # Input the credentials and login
        browser.find_element(By.XPATH, '//*[@id="app"]/div/form/input[1]').send_keys(EMAIL)
        browser.find_element(By.XPATH, '//*[@id="app"]/div/form/input[2]').send_keys(PW)
        browser.find_element(By.XPATH, '//*[@id="app"]/div/form/input[3]').click()
        # browser.get('file:///home/sun/Downloads/threads.html')

        wait = WebDriverWait(browser, HTML_TIMEOUT)
        # <a class = "btn logout" ...> 구조가 존재하지만 By.CLASS_NAME, 'btn logout' 은 작동하지 않음.
        wait.until(expected_conditions.presence_of_element_located((By.CLASS_NAME, 'user-email')))
        log('Login successful.')

        # A random cycle number n
        cycle_number = random.randint(MIN_SCANNING_COUNT_ON_SESSION, MAX_SCANNING_COUNT_ON_SESSION)

        # Scan n times on the same login session.
        for i in range(cycle_number):
            # Reset the reply count.
            sum_new_reply_count = 0

            # Start the timer.
            scan_start_time = datetime.datetime.now()

            # Get the thread list.
            browser.get(ROOT_DOMAIN + CAUTION_PATH)
            wait.until(expected_conditions.presence_of_all_elements_located((By.CLASS_NAME, 'thread-list-item')))
            soup = BeautifulSoup(browser.page_source, 'html.parser')

            # On a thread, dealing replies
            for element in soup.select('a.thread-list-item'):
                # Get how many threads have been uploaded since the last check.
                # thread_id = int(str(element['href']).strip('/caution/'))
                thread_id = int(str(element['href']).split('/')[-1])
                row_count = element.select_one('span.count').string
                if row_count == '완결':
                    # TODO: Delete the row from DB and notify
                    count = int(300)
                else:
                    count = int(row_count)  # A natural number (타래 세울 때 1)

                # Check if the count has been increased.
                # If so, scan to check if there are links.
                reply_count_to_scan = thread_db.get_reply_count_not_scanned(thread_id, count)
                if reply_count_to_scan > 0:
                    scan(thread_id, reply_count_to_scan)
                    sum_new_reply_count += reply_count_to_scan

            # Print the time elapsed for scanning.
            scan_end_time = datetime.datetime.now()
            # 한성 노트북에서 새로운 페이지 1개 당 로딩 0.7초 소요
            # thread-list 든 reply-list 든 로딩 시간 동일하며 이 로딩이 RDS
            elapsed_for_scanning = (scan_end_time - scan_start_time).total_seconds()

            proposed_pause = last_pause * 2
            pause = min(proposed_pause, get_proper_pause(sum_new_reply_count))
            fluctuated_pause = fluctuate(pause)

            log('%.1f(%.1f)\t' % (elapsed_for_scanning + last_pause, elapsed_for_scanning)
                # Actual pause(Time spent on scanning)
                + str(sum_new_reply_count) + ' new\t'
                # New reply count on refresh the thread list page+
                + ': %.1f\t' % (10 * sum_new_reply_count / (elapsed_for_scanning + last_pause))
                + '-> %1.f(%1.f) \t' % (pause, fluctuated_pause)  # A proper pose(Fluctuated pause)
                + str(datetime.datetime.now()).split('.')[0])  # Timestamp

            # Store for the next use.
            last_pause = fluctuated_pause
            sum_new_reply_count_last_time = sum_new_reply_count

            # Sleep to show random behavior.
            time.sleep(fluctuated_pause)
    except Exception as main_loop_exception:
        log('(%s) Error on %d: %s ' % (datetime.datetime.now(), thread_id, main_loop_exception))
        try:
            err_soup = BeautifulSoup(browser.page_source, 'html.parser')
            log(err_soup.prettify())
        except Exception as e:
            log('Failed to thread list page source: %s' % e)

    # Close connection to the db
    thread_db.close_connection()
    log('MySQL connection closed.')
    time.sleep(3)
