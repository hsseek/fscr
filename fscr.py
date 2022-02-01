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
    MAX_REPLIES_VISIBLE = 24
    MAX_REPLIES_POSSIBLE = 300

    # Credentials
    EMAIL, PW = common.build_tuple('LOGIN_INFO.pv')

    # Reply log
    REPLY_LOG_FILE = 'log-re.pv'

    # Variables regarding randomizing the behavior
    # For the same or increasing number of new replies
    MIN_SCANNING_COUNT_PER_SESSION = 100
    MAX_SCANNING_COUNT_PER_SESSION = 420
    PAUSE_IDLE, PAUSE_POWER, PAUSE_MULTIPLIER_THR, PAUSE_MULTIPLIER_SMALL, PAUSE_MULTIPLIER_LARGE \
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


def log(message: str, file_name: str = common.Constants.LOG_FILE, has_tst: bool = False, has_print=True):
    common.log(message, log_path=common.Constants.LOG_PATH + file_name, has_tst=has_tst, has_print=has_print)


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


def scan_thread(thread_no: int, last_reply_count: int, head_only: bool):
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

    if head_only:  # Hardly called. A thread with the head reply(#1) only.
        # Do not wait for 'thread-reply' which doesn't exist yet.
        is_loaded = wait_and_retry(browser_wait, 'th-contents')
        if not is_loaded:
            log('Error: Cannot scan the only reply. (%s)' % thread_url)
            log_page_source(file_name='exception-only-reply.pv')
        head_reply_soup = BeautifulSoup(browser.page_source, common.Constants.HTML_PARSER)
        thread_db.update_thread(thread_no, 1)
        scan_head(head_reply_soup, thread_no, thread_url)
    else:
        is_loaded = wait_and_retry(browser_wait, 'thread-reply')
        if not is_loaded:
            log('Error: Cannot scan replies after %.f". (%s)' % (prev_pause, thread_url))
            log_page_source(file_name='exception-replies.pv')
        # Get the thread list and the scanning targets(the new replies)
        replies_soup = BeautifulSoup(browser.page_source, common.Constants.HTML_PARSER)
        reply_count_class_name = 'reply-count'
        reply_count_str = replies_soup.select_one('span.%s' % reply_count_class_name).text
        if reply_count_str.isdigit():
            asserted_reply_count = int(reply_count_str)
        else:
            # An unexpected value for reply count. Prevent further scanning.
            asserted_reply_count = Constants.MAX_REPLIES_POSSIBLE
            thread_title = replies_soup.select_one('div.thread-info > h3.title').next_element
            if '완결' in reply_count_str:
                log('\n<%s> reached the limit.(%s)' % (thread_title, thread_url))
            elif '닫힘' in reply_count_str:
                log('\n<%s> has been blocked.(%s)' % (thread_title, thread_url), has_tst=True)
            else:
                log('Error: The reply count has an unexpected content(%s).\n(%s)' %
                    (reply_count_str, thread_url), has_tst=True)
        try:
            last_reply_no = replies_soup.select('span.reply-offset')[-1].text.strip().strip('#')
            current_reply_count = int(last_reply_no)
        except Exception as last_reply_no_exception:
            log('Error: The last reply number cannot be retrieved(%s).' % last_reply_no_exception)
            log_page_source(file_name='exception-last-reply-no.pv')
            current_reply_count = asserted_reply_count
        if asserted_reply_count != Constants.MAX_REPLIES_POSSIBLE and current_reply_count != asserted_reply_count:
            log('\nWarning: The last reply no(%d) != The reply count on the head(%d).(%s)' %
                (current_reply_count, asserted_reply_count, thread_url), has_tst=True)

        current_count_to_scan = current_reply_count - last_reply_count
        thread_db.update_thread(thread_no, current_reply_count)
        replies = replies_soup.select('div.thread-reply')

        if not replies or len(replies) < current_count_to_scan:  # The #1 needs scanning.
            scan_head(replies_soup, thread_no, thread_url)

        # Now scan the new replies.
        new_replies = replies[-current_count_to_scan:]
        for reply in new_replies:
            scan_content(replies_soup, reply, thread_no, thread_url)


def has_specs(reply) -> bool:
    col_pt = 0
    content_str = ''
    for content in reply.select_one('div.th-contents'):
        if not isinstance(content, bs4.element.Tag):  # Plain text
            content_str += content.text + '\n'
    if re.search("(^|[^0-9])[6-9][0|5].{0,8}[a-kA-K]", content_str):
        return True
    if re.search("[1-9][0-9].{0,4}[a-kA-K]([^a-zA-Z].*|$)", content_str):
        return True
    if re.search("(^|[^0-9])1[4-7][0-9noxNOX]([^0-9시분초개대번~]|$)", content_str):
        col_pt += 1
    if re.search("(^|[^0-9])[1-3][0-9noxNOX]([^0-9시분초개대번~]|$)", content_str):
        col_pt += 1
    if re.search("(^|[^0-9])[4-6][0-9noxNOX]([^0-9시분초개대번~]|$)", content_str):
        col_pt += 1
    if col_pt >= 2:
        return True
    else:
        return False


def scan_head(replies_soup, thread_no, thread_url):
    global prev_pause, prev_prev_pause
    head = replies_soup.select_one('div.thread-first-reply')
    links_in_head = head.select('a.link')
    spec_present = has_specs(head)

    report = compose_reply_report(replies_soup, thread_url, head, 1)
    if spec_present:
        report += '\n(Specs present)'
    # Log every reply.
    log(report, Constants.REPLY_LOG_FILE, has_tst=True)

    if links_in_head or spec_present:  # Link(s) present in the head
        # Log a meaningful reply.
        log(report, has_print=False)
        # Check if the reply contains ignored patterns.
        ignored_pattern = has_ignored_content(head)
        if ignored_pattern:
            log('(Skipping "%s")' % ignored_pattern)
        else:
            for link in links_in_head:
                source_url = link['href']
                downloader.download(source_url, thread_no, 1, prev_pause, prev_prev_pause)


def scan_content(replies_soup, reply: bs4.element.Tag, thread_no, thread_url):
    try:
        global prev_pause, prev_prev_pause
        links_in_reply = reply.select('div.th-contents > a.link')
        spec_present = has_specs(reply)

        # Retrieve the reply information.
        reply_no_str = reply.select_one('div.reply-info > span.reply-offset').text
        reply_no = int(reply_no_str.strip().replace('#', ''))
        report = compose_reply_report(replies_soup, thread_url, reply, reply_no)
        if spec_present:
            report += '\n(Specs present)'
        # Log every reply.
        log(report, Constants.REPLY_LOG_FILE, has_tst=True)

        if links_in_reply or spec_present:
            # Log a meaningful reply.
            log(report, has_print=False)

            # Check if the reply contains ignored patterns.
            ignored_pattern = has_ignored_content(reply)
            if ignored_pattern:
                log('(Skipping "%s")' % ignored_pattern)
            else:
                for link in links_in_reply:
                    source_url = link['href']
                    downloader.download(source_url, thread_no, int(reply_no), prev_pause, prev_prev_pause)
    except Exception as reply_exception:
        log_file_name = 'exception-reply.pv'
        log('Error: Reply scanning failed on %s.' % thread_url, has_tst=True)
        log('Exception: %s\n[Traceback]\n%s' % (reply_exception, traceback.format_exc()), file_name=log_file_name)
        log('\n\n[Reply source]\n' + reply.prettify(), file_name=log_file_name)


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
    user_id_tag = reply.select_one('span.user-id')
    user_name_tag = reply.select_one('span.name')
    both_filled = False

    if user_id_tag:
        user_id = user_id_tag.text
        if user_name_tag:
            both_filled = True
    elif user_name_tag:
        user_id = user_name_tag.text
    else:
        user_id = ''
        log('Error: Unknown user_id structure.(%s)' % thread_url)
        log('\n\n[Reply source]\n' + reply.prettify(),
            file_name='error-reply-user-id.pv')
    header = '\n' + double_line + '\n' + '<%s>  #%d  %s  (%s)' % (thread_title, reply_no, user_id, thread_url)
    if both_filled:
        header += '%s <- Name specified' % user_name_tag.text
    report = header + '\n' + __format_reply_content(reply) + '\n' + dashed_line
    return report


def __format_reply_content(reply):
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
            message += str(content).strip()
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
def scan_threads(soup) -> int:
    global thread_db
    sum_reply_count_to_scan = 0
    for thread in soup.select('a.thread-list-item'):
        thread_id = int(str(thread['href']).split('/')[-1])
        thread_url = common.Constants.ROOT_DOMAIN + common.Constants.CAUTION_PATH + '/' + str(thread_id)
        thread_title = thread.select_one('span.title').string
        reply_count = None

        reply_count_str = thread.select_one('span.count').string
        # The count value is an estimate at this stage.
        # Difference by 1~2 might occur due to the newly posted replies while scanning.
        if reply_count_str.isdigit():
            reply_count = int(reply_count_str)
        elif '닫힘' in reply_count_str:
            consecutive_digits = re.search("[1-9][0-9].{0,2}", reply_count_str)
            if consecutive_digits:
                reply_count = consecutive_digits
        # No clues of reply count.
        if reply_count is None:
            reply_count = Constants.MAX_REPLIES_POSSIBLE

        # Check if the count has been increased.
        # If so, scan to check if there are links.
        last_reply_count = thread_db.get_reply_count(thread_id)
        new_count = reply_count - last_reply_count
        if new_count > 0:
            # Accumulate the counts to estimate a proper pause at this stage.
            sum_reply_count_to_scan += new_count
            # Filter by titles.
            for pattern in Constants.IGNORED_TITLE_PATTERNS:
                if pattern in thread_title:
                    log('\n<%s> ignored.(%s)' % (thread_title, thread_url), Constants.REPLY_LOG_FILE, True)
                    # Update DB without actually scanning replies.
                    # For the non-filtered threads, the reply count will be updated just before scanning.
                    thread_db.update_thread(thread_id, reply_count)
                    break
            else:  # No pattern matched. Scan replies of the thread.
                try:
                    if new_count >= Constants.MAX_REPLIES_VISIBLE:
                        log('\n%d new replies on %s' % (new_count, thread_url), has_tst=True)
                    scan_thread(thread_id, last_reply_count, reply_count == 1)
                except Exception as thread_exception:
                    log_file_name = 'exception-thread.pv'
                    exception_last_line = str(thread_exception).splitlines()[-1]
                    log('Error: Thread scanning failed on %i(%s).' % (thread_id, exception_last_line), has_tst=True)
                    log('Exception: %s\n[Traceback]\n%s' % (thread_exception, traceback.format_exc()),
                        file_name=log_file_name)
                    log_page_source(file_name=log_file_name)
    return sum_reply_count_to_scan


def check_privilege(driver: webdriver.Chrome):
    timeout = 20
    logged_in_class_name = 'user-email'
    soup = BeautifulSoup(driver.page_source, common.Constants.HTML_PARSER)
    if soup.select_one('.%s' % logged_in_class_name):
        return True
    else:
        log('Login required.', has_tst=True)
        driver.get(common.Constants.ROOT_DOMAIN + common.Constants.LOGIN_PATH)
        # Input the credentials and login
        try:
            driver.find_element(By.XPATH, '//*[@id="app"]/div/form/input[1]').send_keys(Constants.EMAIL)
            driver.find_element(By.XPATH, '//*[@id="app"]/div/form/input[2]').send_keys(Constants.PW)
            driver.find_element(By.XPATH, '//*[@id="app"]/div/form/input[3]').click()
            WebDriverWait(driver, timeout). \
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
    new_reply_count += scan_threads(threads_soup)
    return new_reply_count


def impose_pause(new_reply_count: int, elapsed_sec: float):
    recurrence_pause = prev_pause * Constants.PAUSE_MULTIPLIER_SMALL \
        if new_reply_count > Constants.PAUSE_MULTIPLIER_THR \
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

            is_hot = True if cycle_pause < Constants.HOT_THRESHOLD_SEC else False
            if current_cycle_number >= sufficient_cycle_number and not is_hot:
                break

            # Sleep to implement random behavior.
            time.sleep(fluctuated_cycle_pause)

            # Cycling
            current_cycle_number += 1
            last_cycled_time = datetime.now()

        # Sufficient cycles have been conducted and pause is large: Finish the session.
        session_elapsed_minutes = common.get_elapsed_sec(session_start_time) / 60
        log('\n%d cycles finished in %d minutes. Close the browser session.' %
            (current_cycle_number, int(session_elapsed_minutes)))
        trim_after_session()
    except selenium.common.exceptions.TimeoutException:
        log('Error: Timeout in %.1f min.' % (common.get_elapsed_sec(last_cycled_time) / 60), has_tst=True)
        log(traceback.format_exc(), 'Selenium-Timeout.pv')


def trim_after_session():
    # Trim the database.
    deleted_count = thread_db.delete_old_threads()
    if not deleted_count:
        log('%d threads have been deleted from database.' % deleted_count, has_tst=True)

    # Trim long log files.
    common.trim_logs(common.Constants.LOG_PATH + Constants.REPLY_LOG_FILE)
    common.trim_logs(common.Constants.LOG_PATH + common.Constants.LOG_FILE)
    common.trim_logs(common.Constants.LOG_PATH + downloader.Constants.DL_LOG_FILE)


if __name__ == "__main__":
    # For decreasing number of new replies
    prev_pause = 0.0
    prev_prev_pause = 0.0

    # The main loop
    while True:
        session_start_time = datetime.now()  # The session timer

        # Connect to the database
        thread_db = sqlite.ThreadDatabase()
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
        log('Pause for %.1f min.\t(%s)\n' % (session_pause / 60, common.get_time_str()))
        time.sleep(session_pause)
