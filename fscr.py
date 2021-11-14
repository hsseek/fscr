import time
import common
import traceback

import selenium.common.exceptions
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
import bs4
from bs4 import BeautifulSoup
import random
import datetime
# Custom scripts
import sqlite
import downloader


class Constants:
    # urls
    DRIVER_PATH = common.read_from_file('DRIVER_PATH.pv')
    ROOT_DOMAIN = common.read_from_file('ROOT_DOMAIN.pv')
    LOGIN_PATH = common.read_from_file('LOGIN_PATH.pv')
    LOG_PATH = common.read_from_file('LOG_PATH.pv')
    CAUTION_PATH = '/caution'
    HTML_TIMEOUT = 5

    # Credentials
    EMAIL = common.read_from_file('EMAIL.pv')
    PW = common.read_from_file('PW.pv')

    # BeautifulSoup parsing format
    HTML_PARSER = 'html.parser'

    # Variables regarding randomizing the behavior
    # For the same or increasing number of new replies
    MIN_SCANNING_COUNT_ON_SESSION = 100
    MAX_SCANNING_COUNT_ON_SESSION = 1000
    PAUSE_IDLE = 600.0
    PAUSE_POWER = 3.5
    PAUSE_MULTIPLIER = 2


def initiate_browser():
    # A chrome web driver with headless option
    service = Service(Constants.DRIVER_PATH)
    options = webdriver.ChromeOptions()
    options.add_argument('headless')
    options.add_argument('disable-gpu')
    # options.add_experimental_option("detach", True)
    driver = webdriver.Chrome(service=service, options=options)
    return driver


def log(message: str, file_name: str = 'log.pv', has_tst: bool = False):
    common.log(message, log_path=Constants.LOG_PATH + file_name, has_tst=has_tst)


def scan_replies(thread_no: int, scan_count: int, is_new_thread: bool):
    try:
        # Open the page to scan
        thread_url = Constants.ROOT_DOMAIN + Constants.CAUTION_PATH + "/" + str(thread_no)
        browser.get(thread_url)

        is_scan_head_only = True if scan_count == 1 and is_new_thread else False
        if is_scan_head_only:  # Hardly called. A thread with head reply(#1) only detected.
            wait.until(expected_conditions.visibility_of_element_located((By.CLASS_NAME, 'th-contents')))
            replies_soup = BeautifulSoup(browser.page_source, Constants.HTML_PARSER)
            head = replies_soup.select_one('div.thread-first-reply')
            links_in_head = head.select('a.link')
            if links_in_head:  # Link(s) present in the head
                log(compose_reply_report(replies_soup, thread_url, head, 1))
                for link in links_in_head:
                    source_url = link['href']
                    downloader.download(source_url, thread_no, 1)
            return
        else:  # Need to scan replies as well.
            try:
                wait.until(expected_conditions.visibility_of_all_elements_located((By.CLASS_NAME, 'thread-reply')))
                # Get the thread list and the scanning targets(the new replies)
                replies_soup = BeautifulSoup(browser.page_source, Constants.HTML_PARSER)
                replies = replies_soup.select('div.thread-reply')

                if not replies or len(replies) < scan_count:  # The #1 needs scanning.
                    head = replies_soup.select_one('div.thread-first-reply')
                    links_in_head = head.select('a.link')
                    if links_in_head:  # Link(s) present in the head
                        log(compose_reply_report(replies_soup, thread_url, head, 1))
                        for link in links_in_head:
                            source_url = link['href']
                            downloader.download(source_url, thread_no, 1)

                new_replies = replies[-scan_count:]

                # Now scan the new replies.
                for reply in new_replies:
                    links_in_reply = reply.select('div.th-contents > a.link')
                    if links_in_reply:  # Link(s) present in the reply
                        # Retrieve the reply information.
                        reply_no_str = reply.select_one('div.reply-info > span.reply-offset').next_element
                        reply_no = int(reply_no_str.strip().replace('#', ''))
                        log(compose_reply_report(replies_soup, thread_url, reply, reply_no))
                        for link in links_in_reply:
                            source_url = link['href']
                            downloader.download(source_url, thread_no, int(reply_no))  # Now refer the source page.
            except Exception as scan_exception:
                log('Error: Cannot scan %i(%s).' % (thread_no, scan_exception), has_tst=True)
                log('Exception: %s\n[Traceback]\n%s' % (scan_exception, traceback.format_exc()), 'scan_exception.pv')
                try:
                    replies_err_soup = BeautifulSoup(browser.page_source, Constants.HTML_PARSER)
                    log('\n\n[Page source]\n' + replies_err_soup.prettify(), str(scan_exception))
                except Exception as scan_exception:
                    log('Error: Failed to load page source %s(%s).' % (thread_no, scan_exception), has_tst=True)
                    log('Exception: %s\n[Traceback]\n%s' % (scan_exception, traceback.format_exc()),
                        'scan_exception.pv')

    except Exception as reply_exception:
        exception_last_line = str(reply_exception).splitlines()[-1]
        log('Error: Reply scanning failed on %i(%s).' % (thread_no, exception_last_line), has_tst=True)
        log('Exception: %s\n[Traceback]\n%s' % (reply_exception, traceback.format_exc()), 'reply_exception.pv')
        try:
            replies_err_soup = BeautifulSoup(browser.page_source, Constants.HTML_PARSER)
            log('\n\n[Page source]\n' + replies_err_soup.prettify(), 'reply_exception.pv')
        except Exception as scan_exception:
            log('Error: Failed to load page source %s(%s)' % (thread_no, scan_exception), has_tst=True)


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
                message += content.contents[-1].strip() + " "
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
    return value * random.uniform(1.0, 1.25) + random.uniform(0.6, 2.4)


# A proper pause in seconds based on the count of new replies
def get_absolute_pause(new_reply_count: int):
    return Constants.PAUSE_IDLE / ((new_reply_count ** Constants.PAUSE_POWER) + 1)


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
            if str(row_count).isdigit():
                count = int(row_count)  # A natural number (타래 세울 때 1)
            else:
                thread_title = thread.select_one('span.title').string
                thread_url = Constants.ROOT_DOMAIN + Constants.CAUTION_PATH + '/' + str(thread_id)
                # Add to finished list.
                finished_thread_ids.append(thread_id)
                if row_count == '완결':
                    log('\n<%s> reached the limit.(%s)' % (thread_title, thread_url))
                    count = int(300)
                elif row_count == '닫힘':
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
                scan_replies(thread_id, reply_count_to_scan, is_new_thread)
                sum_reply_count_to_scan += reply_count_to_scan

    return sum_reply_count_to_scan


def copy_replies(url: str):
    browser.get(url)
    wait.until(expected_conditions.visibility_of_all_elements_located((By.CLASS_NAME, 'thread-reply')))
    # Get the thread list and the scanning targets(the new replies)
    replies_soup = BeautifulSoup(browser.page_source, Constants.HTML_PARSER)
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
    file_name = common.split_on_last_pattern(url, '/')[1] + '.pv'  # log_path/101020.pv
    log(report_head + report_body, file_name)


# For decreasing number of new replies
sum_new_reply_count_last_time = 0
last_pause = 0

# The main loop
while True:
    session_start_time = datetime.datetime.now()  # The session timer
    last_cycled_time = datetime.datetime.now()  # The scan cycling log
    session_pause = 0  # Pause for the following session

    # Connect to the database
    thread_db = sqlite.ThreadDatabase()
    finished_thread_ids = thread_db.fetch_finished()
    log('SQL connection opened.', has_tst=True)
    thread_id = 0  # For debugging: if thread_id = 0, it has never been assigned.

    # Initiate the browser
    browser = initiate_browser()

    # Online process starts.
    # Login and scan the thread list -> replies on each thread.
    try:
        # Open the browser
        browser.get(Constants.ROOT_DOMAIN + Constants.LOGIN_PATH)

        # Input the credentials and login
        browser.find_element(By.XPATH, '//*[@id="app"]/div/form/input[1]').send_keys(Constants.EMAIL)
        browser.find_element(By.XPATH, '//*[@id="app"]/div/form/input[2]').send_keys(Constants.PW)
        browser.find_element(By.XPATH, '//*[@id="app"]/div/form/input[3]').click()

        wait = WebDriverWait(browser, Constants.HTML_TIMEOUT)
        wait.until(expected_conditions.presence_of_element_located((By.CLASS_NAME, 'user-email')))
        log('Login successful.\t', has_tst=True)

        # A random cycle number n
        sufficient_cycle_number = random.randint(
            Constants.MIN_SCANNING_COUNT_ON_SESSION, Constants.MAX_SCANNING_COUNT_ON_SESSION)
        current_cycle_number = 0
        is_hot = True

        # Scan n times on the same login session.
        while current_cycle_number < sufficient_cycle_number or is_hot:
            # Reset the reply count.
            sum_new_reply_count = 0

            # Start the timer.
            scan_start_time = datetime.datetime.now()

            # Get the thread list.
            browser.get(Constants.ROOT_DOMAIN + Constants.CAUTION_PATH)
            wait.until(expected_conditions.presence_of_all_elements_located((By.CLASS_NAME, 'thread-list-item')))
            threads_soup = BeautifulSoup(browser.page_source, Constants.HTML_PARSER)

            # Scan thread list and accumulate the number of new replies.
            sum_new_reply_count += scan_threads(threads_soup)

            # Print the time elapsed for scanning.
            scan_end_time = datetime.datetime.now()
            elapsed_for_scanning = common.get_elapsed_sec(scan_start_time)

            # Impose a proper pause.
            recurrence_pause = last_pause * Constants.PAUSE_MULTIPLIER
            pause = min(recurrence_pause, get_absolute_pause(sum_new_reply_count))
            session_pause = pause  # Update to use it out from the loop.
            fluctuated_pause = fluctuate(pause)

            pause_status_str = '%1.f(%1.f)' % (pause, fluctuated_pause)
            pause_status_str += '\t' if pause >= 100 else ' \t'  # For visual alignment

            current_session_span = elapsed_for_scanning + last_pause
            print('%1.f\t= %.1f\t+ (%1.f)\t' % (current_session_span, elapsed_for_scanning, last_pause)
                  + str(sum_new_reply_count) + ' new\t'
                  + '(H: %.1f)\t' % (100 * sum_new_reply_count / current_session_span / (pause + 0.0001))
                  + '-> %s' % pause_status_str
                  + '%s' % common.get_time_str())

            # Store for the next use.
            last_pause = fluctuated_pause
            sum_new_reply_count_last_time = sum_new_reply_count

            # Sleep to show random behavior.
            time.sleep(fluctuated_pause)

            # Cycling
            current_cycle_number += 1
            is_hot = True if pause < 90 else False
            last_cycled_time = datetime.datetime.now()

        # Sufficient cycles have been conducted and pause is large: Finish the session.
        session_elapsed_minutes = common.get_elapsed_sec(session_start_time) / 60
        log('\n%dth cycle finished in %d minutes. Close the browser session.' %
            (current_cycle_number, int(session_elapsed_minutes)))

        # Trim the database.
        deleted_count = thread_db.delete_old_threads()
        if not deleted_count:
            log('%d threads have been deleted from database.' % deleted_count, has_tst=True)

    except selenium.common.exceptions.TimeoutException:
        log('Error: Timeout in %.1f min.' % (common.get_elapsed_sec(last_cycled_time) / 60), has_tst=True)
        log(traceback.format_exc(), 'Selenium-Timeout.pv')
    except selenium.common.exceptions.WebDriverException as e:
        log('Error: Cannot operate WebDriver(WebDriverException).', has_tst=True)
        log(traceback.format_exc(), 'WebDriverException.pv')
        time.sleep(fluctuate(210))  # Assuming the server is not operating.
    except Exception as main_loop_exception:
        log('Error: Cannot retrieve thread list(%s).' % main_loop_exception, has_tst=True)
        log(traceback.format_exc(), 'main-loop-exception.pv')
        try:
            err_soup = BeautifulSoup(browser.page_source, Constants.HTML_PARSER)
            side_pane_elements = err_soup.select('div.user-info > a.btn')
            for element in side_pane_elements:
                if element['href'] == '/login':
                    cool_down = fluctuate(340)
                    print('The session requires login. Retry after %ds.' % int(cool_down))
                    # Possibly banned for abuse. Cool down.
                    time.sleep(cool_down)
                    break
                else:
                    log('\n\n[Page source]\n' + err_soup.prettify(), str(main_loop_exception))
        except Exception as e:
            log('Error: Failed to thread list page source(%s)' % e)
        finally:
            time.sleep(fluctuate(90))

    browser.quit()  # Close the browser.
    thread_db.close_connection()  # Close connection to the db.
    log('SQL connection closed.', has_tst=True)
    # Pause again.
    session_pause = fluctuate(session_pause)
    log('Pause for %.1f min.\t(%s)\n' % ((session_pause / 60), common.get_time_str()))
    time.sleep(session_pause)
