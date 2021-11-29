import common
import glob
import os
import traceback

import selenium.common.exceptions
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
import requests
from urllib.parse import urlparse
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait
from PIL import Image
import time


class Constants:
    DL_LOG_FILE = 'log-dl.pv'
    DESTINATION_PATH = common.read_from_file('DOWNLOAD_DESTINATION_PATH.pv')
    DUMP_PATH = common.read_from_file('DUMP_PATH.pv')
    PASSWORDS = common.build_tuple('PASSWORD_CANDIDATES.pv')


def log(message: str, file_name: str = common.Constants.LOG_FILE, has_tst: bool = False):
    common.log(message, log_path=common.Constants.LOG_PATH + file_name, has_tst=has_tst)


def initiate_browser():
    # A chrome web driver with headless option
    service = Service(common.Constants.DRIVER_PATH)
    options = webdriver.ChromeOptions()
    options.add_experimental_option("prefs", {
        "download.default_directory": Constants.DESTINATION_PATH,
        "download.prompt_for_download": False
    })
    options.add_argument('headless')
    options.add_argument('disable-gpu')
    # options.add_experimental_option("detach", True)
    driver = webdriver.Chrome(service=service, options=options)
    return driver


def __get_url_index(url: str) -> ():
    url_index = []  # for example, url_index = [3, 5, 1, 9] (a list of int)
    str_index = common.split_on_last_pattern(url, '/')[-1]  # 'a3Fx' from 'https://domain.com/a3Fx'
    with open('SEQUENCE.pv', 'r') as file:
        sequence = file.read().split('\n')

    for char in str_index:  # a -> 3 -> F -> x
        for n, candidates in enumerate(sequence):
            if char == candidates:
                url_index.append(n)  # Found the matching index
                break
    return tuple(url_index)


def __format_url_index(url_index: ()) -> str:
    formatted_index = ''
    for index in url_index:
        formatted_index += '%02d' % index
    return formatted_index  # '19092307'


def __format_file_name(file_name: str) -> str:
    chunks = common.split_on_last_pattern(file_name, '.')
    return chunks[0].strip().replace(' ', '-').replace('.', '-') + '.' + chunks[1]


def __convert_webp_to_png(stored_dir, filename):
    ext = 'png'
    stored_path = os.path.join(stored_dir, filename)
    img = Image.open(stored_path).convert("RGB")
    new_filename = common.split_on_last_pattern(filename, '.')[0] + '.' + ext
    new_path = os.path.join(stored_dir, new_filename)
    img.save(new_path, ext)
    os.remove(stored_path)


def wait_for_downloading(file_name_tag):
    seconds = 0
    check_interval = 1
    is_downloading = False
    temp_extension = '.crdownload'
    file_name = None

    if file_name_tag:  # The file name has been specified.
        while not is_downloading and seconds < 5:  # Loop up to 5 seconds to locate downloading file.
            file_name = file_name_tag.string
            if os.path.exists(Constants.DESTINATION_PATH + file_name + temp_extension):
                is_downloading = True
                break
            seconds += check_interval
            time.sleep(check_interval)
    else:  # Search the file.
        while not is_downloading and seconds < 3:  # Loop up to 5 seconds to locate downloading file.
            for file in os.listdir(Constants.DESTINATION_PATH):
                if file.endswith(temp_extension):
                    # A temporary chrome downloading file detected.
                    is_downloading = True
                    file_name = file.replace(' (1)', '').replace(temp_extension, '')
                    break
            seconds += check_interval
            time.sleep(check_interval)

    if is_downloading:
        last_file_size = 0
        # TODO: Use async thread.
        temp_file_name = file_name + temp_extension
        while is_downloading and os.path.exists(Constants.DESTINATION_PATH + temp_file_name) and seconds < 25:
            current_file_size = os.path.getsize(Constants.DESTINATION_PATH + temp_file_name)
            if current_file_size == last_file_size:
                # Download finished, while the file name hasn't been properly changed.
                # (Unless downloading speed is slower than 1 byte/sec.)
                break
            last_file_size = current_file_size  # Update the file size.
            time.sleep(check_interval)
            seconds += check_interval
        # Rename temporary files: Download not finished, duplicated, ...
        for file in os.listdir(Constants.DESTINATION_PATH):
            if file.endswith(temp_extension):
                if file.endswith(' (1)' + temp_extension):  # Remove duplicates : filename.gif (1).crdownload
                    os.remove(Constants.DESTINATION_PATH + file)
                else:
                    os.rename(Constants.DESTINATION_PATH + file,
                              Constants.DESTINATION_PATH + file.replace(temp_extension, ''))
    return file_name


def download(source_url: str, thread_no: int, reply_no: int, pause: float):
    thread_url = common.get_thread_url(thread_no)
    common.check_dir_exists(Constants.DESTINATION_PATH)

    # Set the download target.
    try:
        target = __extract_download_target(source_url, thread_no, reply_no, pause)
        if target is not None:  # If None, a respective error message has been issued in __extract method.
            file_url, file_name = target
            request = requests.get(file_url, stream=True)
            file_path = os.path.join(Constants.DESTINATION_PATH, file_name)
            with open(file_path, 'wb') as f:
                for chunk in request.iter_content(chunk_size=1024 * 8):
                    if chunk:
                        f.write(chunk)
                        f.flush()
                        os.fsync(f.fileno())
            global download_count
            download_count += 1
            log("#%d\t%s" % (download_count, Constants.DUMP_PATH + file_name), has_tst=True)
            if download_count > 10000:
                download_count = 0
            log('[ V ] after %.1f" \t: %s #%d  \t->  \t%s' % (pause, thread_url, reply_no, source_url),
                file_name=Constants.DL_LOG_FILE)

            # Convert a webp file.
            if file_name.endswith('.webp'):
                __convert_webp_to_png(Constants.DESTINATION_PATH, file_name)

    except Exception as download_exception:
        log("Error: Download failed.(%s)" % download_exception, has_tst=True)
        log('Download failure traceback\n\n' + traceback.format_exc(), file_name=Constants.DL_LOG_FILE, has_tst=True)
        print(traceback.format_exc())


def __extract_download_target(source_url: str, thread_no: int, reply_no: int, pause: float) -> ():
    thread_url = common.get_thread_url(thread_no)
    domain = urlparse(source_url).netloc.replace('www', '')

    if domain == 'imgdb.in':
        source = requests.get(source_url).text
        soup = BeautifulSoup(source, common.Constants.HTML_PARSER)
        target_tag = soup.select_one('link')
        # id's
        int_index = __format_url_index(__get_url_index(source_url))
        if not target_tag:  # Empty
            if '/?err=1";' in soup.select_one('script').text:
                # ?err=1 redirects to "이미지가 삭제된 주소입니다."
                log('Sorry, cannot download %s quoted at #%s.' % (int_index, reply_no), has_tst=True)
                log('[ - ] after %.1f" \t: %s #%d  \t-!->\t%s' %
                    (pause, thread_url, reply_no, int_index), file_name=Constants.DL_LOG_FILE, has_tst=True)
            else:
                log('Error: Unknown structure on ' + domain + '\n\n' + soup.prettify(), file_name=str(thread_no))
        else:  # <link> tag present
            target_url = target_tag['href']  # url of the file to download
            category, extension = requests.session().get(target_url).headers['Content-Type'].split('/')
            if category != 'image':
                log('Error: %s is not an image(quoted at #%s).' % (source_url, reply_no), has_tst=True)
            local_name = '%s-%03d-%s.%s' % (int_index, reply_no, thread_no, extension)
            return target_url, local_name

    # Unusual sources: Consider parsing if used often.
    elif domain == 'tmpstorage.com':  # Returns None: download directly from the chrome driver.
        if source_url.strip('/').endswith(domain):
            return  # Referring the website itself, instead of a downloadable source.
        download_btn_xpath = '/html/body/div[2]/div/p/a'
        submit_btn_xpath = '/html/body/div[1]/div/form/p/input'
        pw_input_id = 'password'
        browser = initiate_browser()
        password_timeout = 3

        def element_exists(element_id: str):
            try:
                browser.find_element(By.ID, element_id)
            except selenium.common.exceptions.NoSuchElementException:
                return False
            return True

        try:
            browser.get(source_url)
            if element_exists(pw_input_id):
                wait = WebDriverWait(browser, password_timeout)
                for password in Constants.PASSWORDS:
                    browser.find_element(By.ID, pw_input_id).clear()
                    browser.find_element(By.ID, pw_input_id).send_keys(password)
                    browser.find_element(By.XPATH, submit_btn_xpath).click()
                    try:
                        wait.until(expected_conditions.presence_of_element_located((By.XPATH, download_btn_xpath)))
                        log('%s: Password matched.' % password)
                        break
                    except selenium.common.exceptions.TimeoutException:
                        print('Error: Incorrect password %s.' % password)
                    except Exception as e:
                        print('Error: Incorrect password %s(%s).' % (password, e))
            # browser.find_element(By.XPATH, download_btn_xpath).send_keys(Keys.ALT, Keys.ENTER)
            browser.find_element(By.XPATH, download_btn_xpath).click()
            download_soup = BeautifulSoup(browser.page_source, common.Constants.HTML_PARSER)
            file_name_tag = download_soup.select_one('div#download > h1.filename')
            file_name = wait_for_downloading(file_name_tag)  # Wait for seconds.
            if not file_name:
                # Get the second latest file (the first latest is always the log file).
                second_latest_file = sorted(glob.iglob(Constants.DESTINATION_PATH + '*'), key=os.path.getctime)[-2]
                file_name = common.split_on_last_pattern(second_latest_file, '/')[-1]
                log('Error: Cannot retrieve tmpstorage file name, assuming %s as the file.' % file_name)
            local_name = '%s-%s-%03d-%s' % (
                domain.strip('.com'), thread_no, reply_no, __format_file_name(file_name))
            os.rename(Constants.DESTINATION_PATH + file_name,
                      Constants.DESTINATION_PATH + local_name)

            # Log the change.
            global download_count
            download_count += 1
            log("#%d\t%s" % (download_count, Constants.DUMP_PATH + local_name), has_tst=True)
            if download_count > 10000:
                log('Download count reached 10,000. Reset it.')
                download_count = 0
            log('[ V ] after %.1f" \t: %s #%d  \t->  \t%s' % (pause, thread_url, reply_no, source_url),
                file_name=Constants.DL_LOG_FILE)
        except selenium.common.exceptions.NoSuchElementException:
            err_soup = BeautifulSoup(browser.page_source, common.Constants.HTML_PARSER)
            if err_soup.select_one('div#expired > p.notice'):
                log('Sorry, the link has been expired.', has_tst=True)
                log('[ - ] after %.1f" \t: %s #%d  \t-!->\t%s' %
                    (pause, thread_url, reply_no, source_url), file_name=Constants.DL_LOG_FILE, has_tst=True)
            elif err_soup.select_one('div#delete > p.delete'):
                log('Error: Cannot locate the download button(삭제하시겠습니까?).', has_tst=True)
            else:
                log('Error: Cannot locate the download button.', has_tst=True)
                log('Error: Cannot locate the download button.\n[Page source]\n' + err_soup.prettify(), str(thread_no))
        except FileNotFoundError as file_exception:
            log('Error: The local file not found.\n%s' % file_exception)
        except Exception as tmpstorage_exception:
            log('Error: Cannot retrieve tmpstorage source(%s).' % tmpstorage_exception, has_tst=True)
            log('Exception: %s\n\n[Traceback]\n%s' %
                (tmpstorage_exception, traceback.format_exc()), 'tmpstorage_exception.pv')
            err_soup = BeautifulSoup(browser.page_source, common.Constants.HTML_PARSER)
            log('\n\n[Page source]\n' + err_soup.prettify(), 'tmpstorage_exception.pv')
        finally:
            browser.quit()

    elif domain == 'ibb.co':
        source = requests.get(source_url).text
        soup = BeautifulSoup(source, common.Constants.HTML_PARSER)
        target_tag = soup.select_one('div#image-viewer-container > img')
        if not target_tag:  # An empty tag, returning None.
            if soup.select_one('div.page-not-found'):
                log('Error: Cannot download imgbb link quoted in %s #%s.' % (thread_no, reply_no), has_tst=True)
            else:
                log('Error: Unknown structure on ' + domain + '\n\n' + soup.prettify(), str(thread_no))
        else:  # The image link tag present
            # Try retrieving the link.
            target_url = target_tag['src']
            file_name = common.split_on_last_pattern(target_url, '/')[-1]

            # Try retrieving the views.
            view_tag = soup.select_one('div.content-width > div.header > div.header-content-right > div')
            view = int(view_tag.next_element) if view_tag else 0

            local_name = '%s-%s-%03d-%02d-%s' % (
                'ibb', thread_no, reply_no, view, __format_file_name(file_name))
            return target_url, local_name

    elif domain == 'tmpfiles.org':
        log('Warning: Unusual upload on %s: tmpfiles.org.' % thread_url)
    elif domain == 'sendvid.com':
        log('Warning: Unusual upload on %s: sendvid.org.' % thread_url)
    elif domain == 'freethread.net':
        log('%s quoted in %s.' % (source_url, thread_url))
    elif domain == 'image.kilho.net':
        log("Warning: 'image.kilho.net' quoted in %s." % thread_url)
    else:
        log('Warning: Unknown source on %s.(%s)' % (thread_url, source_url))


download_count = 0
