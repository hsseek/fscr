import time
import traceback

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
import bs4
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


def initiate_browser():
    # A chrome web driver with headless option
    service = Service(DRIVER_PATH)
    options = webdriver.ChromeOptions()
    options.add_argument('headless')
    options.add_argument('disable-gpu')
    # options.add_experimental_option("detach", True)
    driver = webdriver.Chrome(service=service, options=options)
    return driver


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


def __get_elapsed_time(start_time) -> float:
    return (datetime.datetime.now() - start_time).total_seconds()


def scan_replies(thread_no: int, scan_count: int):
    try:
        # Open the page to scan
        browser.get(ROOT_DOMAIN + CAUTION_PATH + "/" + str(thread_no))
        wait.until(expected_conditions.presence_of_element_located((By.CLASS_NAME, 'th-contents')))
        try:
            wait.until(expected_conditions.presence_of_element_located((By.CLASS_NAME, 'thread-reply',)))

            # Get the thread list and the scanning targets(the new replies)
            replies_soup = BeautifulSoup(browser.page_source, 'html.parser')
            replies = replies_soup.select('div.thread-reply')

            # the new_replies is not a bs4.results but a collection.deque
            # It is iterable, but does not have Tag.select method.
            # But its elements are Tags so they have select method.
            # 마지막 n개 자르기 위해 iter 함수 쓰지 않았다면 select 2 번으로 한 줄로 끝냈을 것.
            new_replies = __tail(replies, scan_count)

            # Now scan the new replies.
            for reply in new_replies:
                links_in_reply = reply.select('div.th-contents > a.link')
                if links_in_reply:  # Link(s) present in the reply
                    # Retrieve the reply information.
                    reply_no_str = reply.select_one('div.reply-info > span.reply-offset').next_element
                    reply_no = int(reply_no_str.strip().replace('#', ''))
                    separator = '--------------------'
                    thread_title = replies_soup.select_one('div.thread-info > h3.title').next_element
                    report = '%s\n<%s> %s #%d\n' % (separator, thread_title, thread_no, reply_no)  # Report head
                    report += compose_reply_report(reply) + '\n' + separator  # Concatenate the report content.
                    log(report)
                    for link in links_in_reply:
                        source_url = link['href']
                        downloader.download(source_url, thread_no, int(reply_no))  # Now refer the source page.
        except Exception as reply_exception:
            exception_last_line = str(reply_exception).splitlines()[-1]
            log('Warning: Reply scanning failed on %i(%s)' % (thread_no, exception_last_line))
            try:
                replies_err_soup = BeautifulSoup(browser.page_source, 'html.parser')
                try:
                    if str(replies_err_soup.find('span', {'class': 'info-txt reply-count'}).contents[0]).strip() != '1':
                        # if 1: No replies present (likely te be "start thread" exception)
                        log('Error: html structure\n' + replies_err_soup.prettify())
                except Exception as reply_count_exception:
                    log('Error: reply count not available(%s).' % reply_count_exception)
            except Exception as scan_exception:
                log('Error: Failed to load page source %s(%s)' % (thread_no, str(scan_exception)))
    except Exception as scan_exception:
        log('Error: Cannot scan %i(%s)' % (thread_no, str(scan_exception)))
        try:
            replies_err_soup = BeautifulSoup(browser.page_source, 'html.parser')
            log(replies_err_soup.prettify())
        except Exception as scan_exception:
            log('Error: Failed to load page source %s: %s' % (thread_no, str(scan_exception)))


def compose_reply_report(reply):
    message = ""
    for content in reply.select_one('div.th-contents').contents:
        if isinstance(content, bs4.element.Tag):  # The content has a substructure.
            if content.has_attr('href'):
                message += content['href'].strip() + " "
            elif 'class' in content.attrs and content.attrs['class'][0] == 'anchor':
                message += content.contents[-1].strip() + " "
            elif content == '<br/>' or '<br>':
                message += '\n'
            else:
                message += 'Error: Unknown tag: %s\n' % content
        else:  # A simple text element
            message += str(content).strip()
    return message


def fluctuate(value):
    # Large values: The random multiplier dominant
    # Small values: The random increment dominant
    return value * random.uniform(1.0, 1.5) + random.uniform(1.2, 3.6)


def get_proper_pause(new_reply_count: int):
    return PAUSE_IDLE / ((new_reply_count ** PAUSE_POWER) + 1)


def scan_threads(soup) -> int:
    global thread_id
    global thread_db
    sum_reply_count_to_scan = 0
    for thread in soup.select('a.thread-list-item'):
        # Get how many threads have been uploaded since the last check.
        thread_id = int(str(thread['href']).split('/')[-1])
        # Don't bother if the thread has been finished.
        if thread_id not in finished_thread_ids:
            row_count = thread.select_one('span.count').string
            if row_count == '완결':
                thread_title = thread.select_one('span.title').string
                log('<%s> reached the limit: %s' % (thread_title, ROOT_DOMAIN + CAUTION_PATH + '/' + str(thread_id)))
                count = int(300)
                # Add to finished list.
                finished_thread_ids.append(thread_id)
            else:
                count = int(row_count)  # A natural number (타래 세울 때 1)

            # Check if the count has been increased.
            # If so, scan to check if there are links.
            reply_count_to_scan = thread_db.get_reply_count_not_scanned(thread_id, count)
            if reply_count_to_scan > 0:
                scan_replies(thread_id, reply_count_to_scan)
                sum_reply_count_to_scan += reply_count_to_scan
    return sum_reply_count_to_scan


def __get_formatted_time():
    return str(datetime.datetime.now()).split('.')[0]


# The main loop
while True:
    session_start_time = datetime.datetime.now()  # The session timer
    session_pause = 0  # Pause for the following session
    finished_thread_ids = []  # Threads to be removed from the db

    # Connect to the database
    thread_db = sqlite.ThreadDb()
    log('MySQL connection opened.\t%s' % __get_formatted_time())
    thread_id = 0  # For debugging: if thread_id = 0, it has never been assigned.

    # Initiate the browser
    browser = initiate_browser()

    # Online process starts.
    # Login and scan the thread list -> replies on each thread.
    try:
        # Open the browser
        browser.get(ROOT_DOMAIN + LOGIN_PATH)

        # Input the credentials and login
        browser.find_element(By.XPATH, '//*[@id="app"]/div/form/input[1]').send_keys(EMAIL)
        browser.find_element(By.XPATH, '//*[@id="app"]/div/form/input[2]').send_keys(PW)
        browser.find_element(By.XPATH, '//*[@id="app"]/div/form/input[3]').click()

        wait = WebDriverWait(browser, HTML_TIMEOUT)
        wait.until(expected_conditions.presence_of_element_located((By.CLASS_NAME, 'user-email')))
        log('Login successful.\t\t%s' % __get_formatted_time())

        # A random cycle number n
        sufficient_cycle_number = random.randint(MIN_SCANNING_COUNT_ON_SESSION, MAX_SCANNING_COUNT_ON_SESSION)
        current_cycle_number = 0
        is_hot = True

        # Scan n times on the same login session.
        while current_cycle_number < sufficient_cycle_number or is_hot:
            # Reset the reply count.
            sum_new_reply_count = 0

            # Start the timer.
            scan_start_time = datetime.datetime.now()

            # Get the thread list.
            browser.get(ROOT_DOMAIN + CAUTION_PATH)
            wait.until(expected_conditions.presence_of_all_elements_located((By.CLASS_NAME, 'thread-list-item')))
            threads_soup = BeautifulSoup(browser.page_source, 'html.parser')

            # Scan thread list and accumulate the number of new replies.
            sum_new_reply_count += scan_threads(threads_soup)

            # Print the time elapsed for scanning.
            scan_end_time = datetime.datetime.now()
            # thread-list 든 reply-list 든 로딩 시간 거의 동일하며 이 로딩이 RDS (~ 0.7s/page)
            elapsed_for_scanning = __get_elapsed_time(scan_start_time)

            # Impose a proper pause.
            proposed_pause = last_pause * random.uniform(1.5, 3.2)
            pause = min(proposed_pause, get_proper_pause(sum_new_reply_count))
            session_pause = pause
            fluctuated_pause = fluctuate(pause)

            current_session_span = elapsed_for_scanning + last_pause
            log('%.1f(%.1f)\t' % (current_session_span, elapsed_for_scanning)  # Actual pause(Time spent on scanning)
                + str(sum_new_reply_count) + ' new\t'
                + '(H: %.1f)\t' % (100 * sum_new_reply_count / current_session_span / (pause + 0.0001))
                + '-> %1.f(%1.f) \t' % (pause, fluctuated_pause)  # A proper pose(Fluctuated pause)
                + '%s' % __get_formatted_time())

            # Store for the next use.
            last_pause = fluctuated_pause
            sum_new_reply_count_last_time = sum_new_reply_count

            # Sleep to show random behavior.
            time.sleep(fluctuated_pause)

            # Cycling
            current_cycle_number += 1
            is_hot = True if pause < 90 else False
        # Sufficient cycles have been conducted and pause is large: Finish the session.
        session_elapsed_minutes = __get_elapsed_time(session_start_time) / 60
        log('%dth cycle finished in %d minutes. Close the browser session.' %
            (current_cycle_number, int(session_elapsed_minutes)))
    except TimeoutError:
        log('Error: Timeout.\t%s' % __get_formatted_time())
    except Exception as main_loop_exception:
        log('Error: Cannot retrieve thread list(%s).\t%s\n%s' %
            (main_loop_exception, __get_formatted_time(), traceback.format_exc()))
        try:
            err_soup = BeautifulSoup(browser.page_source, 'html.parser')
            side_pane_elements = err_soup.select('div.user-info > a.btn')
            for element in side_pane_elements:
                if element['href'] == '/login':
                    print('logged out')
                    # Possibly banned for abuse. Cool down.
                    time.sleep(300 * random.uniform(1, 2))
                    break
                else:
                    log(err_soup.prettify())
        except Exception as e:
            log('Error: Failed to thread list page source(%s)' % e)

    # Delete the finished threads from the db.
    for finished in finished_thread_ids:
        thread_db.delete_thread(finished)

    browser.quit()  # Close the browser.
    thread_db.close_connection()  # Close connection to the db.
    log('MySQL connection closed.\t%s' % __get_formatted_time())
    # Pause again.
    time.sleep(fluctuate(session_pause))
