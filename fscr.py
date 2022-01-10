import time
import common
import traceback

import selenium.common.exceptions
from selenium import webdriver
# from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
import bs4
from bs4 import BeautifulSoup
import random
from datetime import datetime
import re
import sqlite
import downloader


class Constants:
    HTML_TIMEOUT = 25

    # Credentials
    EMAIL, PW = common.build_tuple('LOGIN_INFO.pv')

    # Variables regarding randomizing the behavior
    # For the same or increasing number of new replies
    MIN_SCANNING_COUNT_PER_SESSION = 100
    MAX_SCANNING_COUNT_PER_SESSION = 420
    PAUSE_IDLE, PAUSE_POWER, PAUSE_MULTIPLIER_THR, PAUSE_MULTIPLIER_SMALL, PAUSE_MULTIPLIER_LARGE\
        = common.build_float_tuple('PAUSE.pv')
    IGNORED_TITLE_PATTERNS = common.build_tuple('IGNORED_TITLE_PATTERNS.pv')
    IGNORED_REPLY_PATTERNS = common.build_tuple('IGNORED_REPLY_PATTERNS.pv')
    HOT_THRESHOLD_SEC = 200


def initiate_browser():
    # A Chrome web driver with headless option
    # service = Service(common.Constants.DRIVER_PATH)
    options = webdriver.ChromeOptions()
    options.add_argument('headless')
    # options.add_argument('disable-gpu')
    driver = webdriver.Chrome(executable_path=common.Constants.DRIVER_PATH, options=options)
    driver.set_page_load_timeout(Constants.HTML_TIMEOUT)
    return driver


def log(message: str, file_name: str = common.Constants.LOG_FILE, has_tst: bool = False):
    common.log(message, log_path=common.Constants.LOG_PATH + file_name, has_tst=has_tst)


def wait_and_retry(wait: WebDriverWait, class_name: str, max_trial: int = 2, presence_of_all: bool = False):
    for i in range(max_trial):
        try:
            if presence_of_all:
                wait.until(expected_conditions.presence_of_element_located((By.CLASS_NAME, class_name)))
            else:
                wait.until(expected_conditions.presence_of_all_elements_located((By.CLASS_NAME, class_name)))
            return True
        except selenium.common.exceptions.TimeoutException:
            log('Warning: Timeout waiting %s' % class_name)
            pass  # It just happens occasionally. Just try again.
        except selenium.common.exceptions.NoSuchElementException:
            log('Warning: Cannot locate %s.' % class_name)
            pass
    return False


def log_page_source(msg: str = None, file_name: str = common.Constants.LOG_FILE):
    try:
        html_source = BeautifulSoup(browser.page_source, common.Constants.HTML_PARSER).prettify()
        formatted_msg = '%s\n\n[Page source]\n%s' % (msg, html_source) if msg else html_source
        log(formatted_msg, file_name)
    except Exception as page_source_exception:
        log('Error: cannot print page source.(%s)' % page_source_exception)


def scan_replies(thread_no: int, scan_count: int = 24, is_new_thread: bool = False):
    # Open the page to scan
    thread_url = common.get_thread_url(thread_no)  # Edit here to debug individual threads. e.g. 'file:///*/main.html'
    browser.get(thread_url)

    is_privileged = check_privilege(browser)
    if not is_privileged:
        # Possibly banned for abuse. Cool down.
        time.sleep(fluctuate(340))
        return
    elif browser.current_url != thread_url:
        browser.get(thread_url)

    is_scan_head_only = True if scan_count == 1 and is_new_thread else False
    if is_scan_head_only:  # Hardly called. A thread with head reply(#1) only detected.
        is_loaded = wait_and_retry(browser_wait, 'th-contents')
        if not is_loaded:
            log('Error: Cannot scan the only reply. (%s)' % thread_url)
            log_page_source(file_name='only-reply-error.pv')
            return  # Cannot load the page, noting to do.
        replies_soup = BeautifulSoup(browser.page_source, common.Constants.HTML_PARSER)
        scan_head(replies_soup, thread_no, thread_url)
    else:  # Need to scan replies as well.
        is_loaded = wait_and_retry(browser_wait, 'thread-reply')
        if not is_loaded:
            log('Error: Cannot scan replies after %.f". (%s)' % (prev_pause, thread_url))
            log_page_source(file_name='replies-error.pv')
        # Get the thread list and the scanning targets(the new replies)
        replies_soup = BeautifulSoup(browser.page_source, common.Constants.HTML_PARSER)
        replies = replies_soup.select('div.thread-reply')

        if not replies or len(replies) < scan_count:  # The #1 needs scanning.
            scan_head(replies_soup, thread_no, thread_url)

        # Now scan the new replies.
        new_replies = replies[-scan_count:]
        for reply in new_replies:
            scan_content(replies_soup, reply, thread_no, thread_url)


def has_specs(reply) -> bool:
    for content in reply.select_one('div.th-contents'):
        if not isinstance(content, bs4.element.Tag):  # Plain text
            if re.search("1[4-8].+[1-9][0-9]", content.text):
                return True
    else:
        return False


def scan_head(replies_soup, thread_no, thread_url):
    global prev_pause, prev_prev_pause
    head = replies_soup.select_one('div.thread-first-reply')
    links_in_head = head.select('a.link')
    spec_present = has_specs(head)
    if links_in_head or spec_present:  # Link(s) present in the head
        log(compose_reply_report(replies_soup, thread_url, head, 1))
        if spec_present:
            log('(Specs present)')

        # Check if the reply contains ignored patterns.
        ignored_pattern = has_ignored_content(head)
        if ignored_pattern:
            log('(Skipping "%s")' % ignored_pattern)
        else:
            for link in links_in_head:
                source_url = link['href']
                downloader.download(source_url, thread_no, 1, prev_pause, prev_prev_pause)


def scan_content(replies_soup, reply, thread_no, thread_url):
    global prev_pause, prev_prev_pause
    links_in_reply = reply.select('div.th-contents > a.link')
    spec_present = has_specs(reply)
    if links_in_reply or spec_present:
        # Retrieve the reply information.
        reply_no_str = reply.select_one('div.reply-info > span.reply-offset').next_element
        reply_no = int(reply_no_str.strip().replace('#', ''))
        log(compose_reply_report(replies_soup, thread_url, reply, reply_no))
        if spec_present:
            log('(Specs present)')

        # Check if the reply contains ignored patterns.
        ignored_pattern = has_ignored_content(reply)
        if ignored_pattern:
            log('(Skipping "%s")' % ignored_pattern)
        else:
            for link in links_in_reply:
                source_url = link['href']
                downloader.download(source_url, thread_no, int(reply_no), prev_pause, prev_prev_pause)


def has_ignored_content(reply):
    for content in reply.select_one('div.th-contents').contents:
        if isinstance(content, bs4.element.Tag):  # The content has a substructure.
            continue
        else:  # A simple text element
            for pattern in Constants.IGNORED_REPLY_PATTERNS:
                if pattern in content:
                    return pattern
    else:
        return None


def compose_reply_report(soup, thread_url, reply, reply_no) -> str:
    double_line = '===================='
    dashed_line = '--------------------'
    thread_title = soup.select_one('div.thread-info > h3.title').next_element
    report = '\n' + double_line + '\n' + \
             '<%s>  #%d\n' % (thread_title, reply_no) + \
             __compose_content_report(reply) + '\n' + \
             '(%s)\n' % thread_url + \
             dashed_line
    return report


def __compose_content_report(reply):
    message = ""
    for content in reply.select_one('div.th-contents').contents:
        if isinstance(content, bs4.element.Tag):  # The content has a substructure.
            if content.has_attr('href'):
                message += content['href'].strip() + " "
            elif 'class' in content.attrs and content.attrs['class'][0] == 'anchor':
                message += content.string.strip() + " "
            elif content == '<br/>' or '<br>':
                message += '\n'
            else:
                message += 'Error: Unknown tag.\n%s\n' % content
        else:  # A simple text element
            message += str(content).strip() + " "
    return message


def fluctuate(value):
    # Large values: The random multiplier dominant
    # Small values: The random increment dominant
    return value * random.uniform(1.0, 1.2) + random.uniform(0.6, 2.4)


# A proper pause in seconds based on the count of new replies
def get_absolute_pause(new_reply_count: int):
    return Constants.PAUSE_IDLE / ((new_reply_count ** Constants.PAUSE_POWER) + 1)


# Get how many replies have been uploaded since the last check.
# If new replies exist, scan the thread.
def __scan_threads(soup) -> int:
    global thread_db
    sum_reply_count_to_scan = 0
    for thread in soup.select('a.thread-list-item'):
        thread_id = int(str(thread['href']).split('/')[-1])
        thread_url = common.Constants.ROOT_DOMAIN + common.Constants.CAUTION_PATH + '/' + str(thread_id)

        # Filter threads.
        # 1. Don't bother if the thread has been finished.
        if thread_id in finished_thread_ids:
            continue  # Skip the thread.
        # 2. Filter by titles.
        thread_title = thread.select_one('span.title').string
        has_pattern = False
        for pattern in Constants.IGNORED_TITLE_PATTERNS:
            if pattern in thread_title:
                has_pattern = True
                break
        if has_pattern:
            continue  # Skip the thread.

        row_count = thread.select_one('span.count').string
        if str(row_count).isdigit():
            count = int(row_count)  # Must be a natural number.
        else:  # The count string is not digit. An irregular row.
            thread_title = thread.select_one('span.title').string
            # Add to finished list, as it does not need scanning further.
            finished_thread_ids.append(thread_id)
            if row_count == '완결':
                log('\n<%s> reached the limit.(%s)' % (thread_title, thread_url))
                count = int(300)
            elif '닫힘' in row_count:
                thread_title = thread.select_one('span.title').string
                log('\n<%s> closed.(%s)' % (thread_title, thread_url), has_tst=True)
                # Try full scanning and copy the page source.
                count = 24
                copy_replies(thread_url)
            else:
                log('Error: Unexpected parameter for reply count(%s) for <%s>.\t(%s)\n(%s)' %
                    (row_count, thread_title, common.get_time_str(), thread_url))
                count = 24
                copy_replies(thread_url)

        # Check if the count has been increased.
        # If so, scan to check if there are links.
        reply_count_to_scan, is_new_thread = thread_db.get_reply_count_not_scanned(thread_id, count)
        if reply_count_to_scan > 0:
            try:  # Finally, scan replies.
                scan_replies(thread_id, reply_count_to_scan, is_new_thread)
                if reply_count_to_scan >= 24:
                    log('\nWarning: Many new replies on %s' % thread_url, has_tst=True)
            except Exception as reply_exception:
                exception_last_line = str(reply_exception).splitlines()[-1]
                log('Error: Reply scanning failed on %i(%s).' % (thread_id, exception_last_line), has_tst=True)
                log('Exception: %s\n[Traceback]\n%s' % (reply_exception, traceback.format_exc()),
                    file_name='exception-reply.pv')
                try:
                    replies_err_soup = BeautifulSoup(browser.page_source, common.Constants.HTML_PARSER)
                    log('\n\n[Page source]\n' + replies_err_soup.prettify(),
                        file_name='exception-reply.pv')
                except Exception as scan_exception:
                    log('Error: Failed to load page source %s(%s)' % (thread_id, scan_exception), has_tst=True)
            sum_reply_count_to_scan += reply_count_to_scan

    return sum_reply_count_to_scan


def copy_replies(url: str):
    browser.get(url)
    is_loaded = wait_and_retry(browser_wait, 'thread-reply', presence_of_all=True)
    if not is_loaded:
        log('Error: Cannot scan the replies while trying to copy them. (%s)' % url)
        log_page_source(file_name='copy-replies-error.pv')
        return  # Cannot load the page, noting to do.
    # Get the thread list and the scanning targets(the new replies)
    replies_soup = BeautifulSoup(browser.page_source, common.Constants.HTML_PARSER)
    replies = replies_soup.select('div.thread-reply')

    # Compose the report.
    thread_title = replies_soup.select_one('div.thread-info > h3.title').next_element
    report_head = '<%s>\n' % thread_title
    report_body = ''
    # Now scan the replies.
    for reply in replies:
        # Retrieve the reply information.
        reply_no_str = reply.select_one('div.reply-info > span.reply-offset').next_element
        reply_no = int(reply_no_str.strip().replace('#', ''))
        dashed_line = '--------------------'
        report_body += '\n#%d%s\n' % (reply_no, dashed_line) + __compose_content_report(reply) + '\n'
    # Log to a file.
    file_name = url.split('/')[-1] + '.pv'  # log_path/101020.pv
    log(report_head + report_body, file_name)


def check_privilege(driver: webdriver.Chrome):
    timeout = 20
    logged_in_class_name = 'user-email'
    soup = BeautifulSoup(driver.page_source, common.Constants.HTML_PARSER)
    if soup.select_one('.%s' % logged_in_class_name):
        return True
    else:
        log('Warning: login required.', has_tst=True)
        driver.get(common.Constants.ROOT_DOMAIN + common.Constants.LOGIN_PATH)
        # Input the credentials and login
        try:
            driver.find_element(By.XPATH, '//*[@id="app"]/div/form/input[1]').send_keys(Constants.EMAIL)
            driver.find_element(By.XPATH, '//*[@id="app"]/div/form/input[2]').send_keys(Constants.PW)
            driver.find_element(By.XPATH, '//*[@id="app"]/div/form/input[3]').click()
            WebDriverWait(driver, timeout).\
                until(expected_conditions.presence_of_element_located((By.CLASS_NAME, logged_in_class_name)))
            log('Login successful.\t', has_tst=True)
            return True
        except Exception as login_exception:
            log('Error: login failed.(%s)' % login_exception)
            return False


def load_thread_list():
    thread_list_url = common.Constants.ROOT_DOMAIN + common.Constants.CAUTION_PATH
    # Get the thread list.
    browser.get(thread_list_url)
    is_privileged = check_privilege(browser)
    if not is_privileged:
        # Possibly banned for abuse. Cool down.
        time.sleep(fluctuate(340))
        return
    elif browser.current_url != thread_list_url:
        browser.get(thread_list_url)

    # Reset the reply count.
    new_reply_count = 0

    is_threads_loaded = wait_and_retry(browser_wait, 'thread-list-item', presence_of_all=True)
    if not is_threads_loaded:
        log('Error: Cannot load thread list after pause of %d".' % prev_pause, has_tst=True)
        log('Page source\n\n' + browser.page_source, file_name='thread-list-err.pv')
        # Cool down and loop again.
        time.sleep(fluctuate(12))
        return 
    threads_soup = BeautifulSoup(browser.page_source, common.Constants.HTML_PARSER)

    # Scan thread list and accumulate the number of new replies.
    new_reply_count += __scan_threads(threads_soup)
    return new_reply_count


def impose_pause(new_reply_count: int, elapsed_sec: float):
    recurrence_pause = prev_pause * Constants.PAUSE_MULTIPLIER_SMALL\
        if new_reply_count > Constants.PAUSE_MULTIPLIER_THR\
        else prev_pause * Constants.PAUSE_MULTIPLIER_LARGE
    pause = min(recurrence_pause, get_absolute_pause(new_reply_count))
    fluctuated_pause = fluctuate(pause)
    pause_status_str = '%1.f(%1.f)' % (pause, fluctuated_pause)
    pause_status_str += '\t' if pause >= 100 else '\t\t'  # For visual alignment
    current_session_span = elapsed_sec + prev_pause
    print('%1.f\t= %.1f +\t(%1.f)\t' % (current_session_span, elapsed_sec, prev_pause)
          + str(new_reply_count) + ' new -> \t'
          + '%s' % pause_status_str
          + '%s' % common.get_time_str())
    return pause, fluctuated_pause


def loop_scanning():
    # A random cycle number n
    sufficient_cycle_number = random.randint(
        Constants.MIN_SCANNING_COUNT_PER_SESSION, Constants.MAX_SCANNING_COUNT_PER_SESSION)
    current_cycle_number = 0
    last_cycled_time = datetime.now()
    is_hot = True
    global prev_pause, prev_prev_pause
    # Scan n times on the same login session.
    try:
        while current_cycle_number < sufficient_cycle_number or is_hot:
            # Scan thread list and the new replies.
            scan_start_time = datetime.now()  # Start the timer.
            sum_new_reply_count = load_thread_list()
            if sum_new_reply_count is None:
                continue  # Something went wrong. Skip the cycle and retry.

            # Impose a proper pause.
            elapsed_for_scanning = common.get_elapsed_sec(scan_start_time)
            cycle_pause, fluctuated_cycle_pause = impose_pause(sum_new_reply_count, elapsed_for_scanning)

            # Store for the next use.
            prev_prev_pause = prev_pause
            prev_pause = fluctuated_cycle_pause

            # Sleep to implement random behavior.
            time.sleep(fluctuated_cycle_pause)

            # Cycling
            current_cycle_number += 1
            is_hot = True if cycle_pause < Constants.HOT_THRESHOLD_SEC else False
            last_cycled_time = datetime.now()
        # Sufficient cycles have been conducted and pause is large: Finish the session.
        session_elapsed_minutes = common.get_elapsed_sec(session_start_time) / 60
        log('\n%d cycles finished in %d minutes. Close the browser session.' %
            (current_cycle_number, int(session_elapsed_minutes)))
        # Trim the database.
        deleted_count = thread_db.delete_old_threads()
        if not deleted_count:
            log('%d threads have been deleted from database.' % deleted_count, has_tst=True)
    except selenium.common.exceptions.TimeoutException:
        log('Error: Timeout in %.1f min.' % (common.get_elapsed_sec(last_cycled_time) / 60), has_tst=True)
        log(traceback.format_exc(), 'Selenium-Timeout.pv')


if __name__ == "__main__":
    # For decreasing number of new replies
    prev_pause = 0.0
    prev_prev_pause = 0.0

    # The main loop
    while True:
        session_start_time = datetime.now()  # The session timer

        # Connect to the database
        thread_db = sqlite.ThreadDatabase()
        finished_thread_ids = thread_db.fetch_finished()
        log('SQL connection opened.', has_tst=True)

        # Initiate the browser
        browser = initiate_browser()
        browser_wait = WebDriverWait(browser, Constants.HTML_TIMEOUT)

        # Online process starts.
        # Login and scan the thread list -> replies on each thread.
        try:
            loop_scanning()
        except selenium.common.exceptions.WebDriverException as e:
            log('Error: Cannot operate WebDriver(WebDriverException).', has_tst=True)
            log(traceback.format_exc(), 'exception-webdriver.pv')
            time.sleep(fluctuate(210))  # Assuming the server is not operating.
        except Exception as main_loop_exception:
            log('Error: Cannot retrieve thread list(%s).' % main_loop_exception, has_tst=True)
            log('Exception:%s\n%s' % (main_loop_exception, traceback.format_exc()), 'main-loop-error.pv')
        finally:
            browser.quit()
            log('Driver session terminated.', has_tst=True)
            thread_db.close_connection()
            log('SQL connection closed.', has_tst=True)

        session_pause = Constants.HOT_THRESHOLD_SEC * random.uniform(0.46, 1.2)
        log('Pause for %.1f min.\t(%s)\n' % (session_pause/60, common.get_time_str()))
        time.sleep(session_pause)
