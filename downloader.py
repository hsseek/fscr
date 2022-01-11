import common
from glob import glob
from shutil import copyfile
import os
import traceback

import selenium.common.exceptions
from selenium import webdriver
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
    DL_DESTINATION_PATH, DL_TMP_PATH = common.build_tuple('DL_DESTINATION_PATH.pv')
    DL_BACKUP_PATH = common.read_from_file('DL_BACKUP_PATH.pv')
    DUMP_PATH = common.read_from_file('DUMP_PATH.pv')
    PASSWORDS = common.build_tuple('PASSWORD_CANDIDATES.pv')


def log(message: str, file_name: str = common.Constants.LOG_FILE, has_tst: bool = False):
    common.log(message, log_path=common.Constants.LOG_PATH + file_name, has_tst=has_tst)


def initiate_browser():
    # A Chrome web driver with headless option
    # service = Service(common.Constants.DRIVER_PATH)
    options = webdriver.ChromeOptions()
    options.add_experimental_option("prefs", {
        "download.default_directory": Constants.DL_TMP_PATH,
        "download.prompt_for_download": False
    })
    options.add_argument('headless')
    # options.add_argument('disable-gpu')
    driver = webdriver.Chrome(executable_path=common.Constants.DRIVER_PATH, options=options)
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


def __check_tmp_download(dir_path: str) -> bool:
    tmp_extension = 'crdownload'
    for file_name in os.listdir(dir_path):
        if tmp_extension in file_name:
            return True
    else:
        return False


def wait_finish_downloading(temp_dir_path: str, timeout: int):
    seconds = 0
    check_interval = 2

    last_size = 0
    consecutive_stalling = 0

    while seconds <= timeout:
        current_size = sum(os.path.getsize(f) for f in glob(temp_dir_path + '*') if os.path.isfile(f))
        if current_size == last_size:
            if current_size > 0 and not __check_tmp_download(temp_dir_path):
                # Size not increasing because the download has been finished.
                return True
            elif consecutive_stalling < 12:  # .crdownload file exists.
                print('Downloading stalled. (%d/%d)' % (seconds, timeout))
                consecutive_stalling += 1
            else:
                log('Warning: Download progress stopped.')
                return False
        # Report
        if current_size != last_size:
            print('%.1f -> %.1f MB' % (last_size / 1000000, current_size / 1000000))
        # Wait
        time.sleep(check_interval)
        seconds += check_interval
        if last_size != current_size:
            last_size = current_size
    log('Download timeout reached.')
    return False  # Timeout


def download(source_url: str, thread_no: int, reply_no: int, prev_pause: float, prev_prev_pause: float):
    thread_url = common.get_thread_url(thread_no)
    common.check_dir_exists(Constants.DL_DESTINATION_PATH)

    # Set the download target.
    try:
        target = __extract_download_target(source_url, thread_no, reply_no, prev_pause, prev_prev_pause)
        if target is not None:  # If None, a respective error message has been issued in __extract method.
            file_url, file_name = target
            request = requests.get(file_url, stream=True)
            file_path = os.path.join(Constants.DL_DESTINATION_PATH, file_name)
            with open(file_path, 'wb') as f:
                for chunk in request.iter_content(chunk_size=1024 * 8):
                    if chunk:
                        f.write(chunk)
                        f.flush()
                        os.fsync(f.fileno())
            log("%s" % (Constants.DUMP_PATH + file_name), has_tst=True)
            log('[ V ] <- %.f" \t<- %.f"\t: %s #%d  \t->  \t%s' %
                (prev_pause, prev_prev_pause, thread_url, reply_no, source_url),
                file_name=Constants.DL_LOG_FILE)

            # Convert a webp file.
            if file_name.endswith('.webp'):
                __convert_webp_to_png(Constants.DL_DESTINATION_PATH, file_name)

    except Exception as download_exception:
        log("Error: Download failed.(%s)" % download_exception, has_tst=True)
        log('Download failure traceback\n\n' + traceback.format_exc(), file_name='exception-dl.pv', has_tst=True)
        print(traceback.format_exc())


def restore_img(int_index: str, reply_no: int, thread_no: int, file_name_format: str) -> str:
    for file_name in os.listdir(Constants.DL_BACKUP_PATH):
        if file_name.startswith(int_index):
            extension = file_name.split('.')[-1]
            formatted_file_name = file_name_format % (int_index, reply_no, thread_no, extension)
            copyfile(Constants.DL_BACKUP_PATH + file_name, Constants.DL_DESTINATION_PATH + formatted_file_name)
            return formatted_file_name


def __extract_download_target(source_url: str, thread_no: int, reply_no: int,
                              prev_pause: float, prev_prev_pause: float) -> ():
    thread_url = common.get_thread_url(thread_no)  # The url of the thread quoting the source
    try:
        source_category, source_extension = retrieve_content_type(source_url)
        if source_category == 'image':
            return source_url, '%d-%03d.%s' % (thread_no, reply_no, source_extension)
    except Exception as header_exception:
        log('Error: The source has a wrong header.(%s)' % header_exception)

    domain = urlparse(source_url).netloc.replace('www', '')

    if domain == 'imgdb.in':
        source = requests.get(source_url).text
        soup = BeautifulSoup(source, common.Constants.HTML_PARSER)
        target_tag = soup.select_one('link')
        file_name_format = '%s-%03d-%d.%s'
        # id's
        int_index = __format_url_index(__get_url_index(source_url))
        if not target_tag:  # Empty
            if '/?err=1";' in soup.select_one('script').text:
                # ?err=1 redirects to "이미지가 삭제된 주소입니다."
                # It's too late. Mark failure log.
                log('[ - ] <- %.f" \t<- %.f"\t: %s #%d  \t-!->\t%s' %
                    (prev_pause, prev_prev_pause, thread_url, reply_no, int_index),
                    file_name=Constants.DL_LOG_FILE, has_tst=True)
                # Try restoring.
                restored_file_name = restore_img(int_index, reply_no, thread_no, file_name_format)
                if restored_file_name:
                    log("(Restored) %s" % (Constants.DUMP_PATH + restored_file_name), has_tst=True)
                else:
                    log('Sorry, cannot download %s quoted at #%d.' % (int_index, reply_no), has_tst=True)
            else:
                log('Error: Unknown structure on ' + domain + '\n\n' + soup.prettify(), file_name=str(thread_no))
        else:  # <link> tag present
            target_url = target_tag['href']  # url of the file to download
            imgdb_link_category, imgdb_link_extension = retrieve_content_type(target_url)
            if imgdb_link_category != 'image':
                log('Error: %s is not an image(quoted at #%d).' % (source_url, reply_no), has_tst=True)
            local_name = file_name_format % (int_index, reply_no, thread_no, imgdb_link_extension)
            return target_url, local_name

    elif domain == 'tmpstorage.com':  # Returns None: download directly from the chrome driver.
        if source_url.strip('/').endswith(domain):
            return  # Referring the website itself, instead of a downloadable source.
        elif (domain + '/success' in source_url) or (domain + '/delete' in source_url):
            return  # Not a downloadable link.

        download_btn_xpath = '/html/body/div[2]/div/p/a'
        submit_btn_xpath = '/html/body/div[1]/div/form/p/input'
        pw_input_id = 'password'
        tmp_browser = initiate_browser()
        password_timeout = 3

        def element_exists(element_id: str):
            try:
                tmp_browser.find_element(By.ID, element_id)
            except selenium.common.exceptions.NoSuchElementException:
                return False
            return True

        try:
            tmp_browser.get(source_url)
            if element_exists(pw_input_id):
                wait = WebDriverWait(tmp_browser, password_timeout)
                for password in Constants.PASSWORDS:
                    tmp_browser.find_element(By.ID, pw_input_id).clear()
                    tmp_browser.find_element(By.ID, pw_input_id).send_keys(password)
                    tmp_browser.find_element(By.XPATH, submit_btn_xpath).click()
                    try:
                        wait.until(expected_conditions.presence_of_element_located((By.XPATH, download_btn_xpath)))
                        log('%s: Password matched.' % password)
                        break
                    except selenium.common.exceptions.TimeoutException:
                        print('Error: Incorrect password %s.' % password)
                    except Exception as e:
                        print('Error: Incorrect password %s(%s).' % (password, e))
            common.check_dir_exists(Constants.DL_TMP_PATH)
            tmp_browser.find_element(By.XPATH, download_btn_xpath).click()
            is_dl_successful = wait_finish_downloading(Constants.DL_TMP_PATH, 280)
            if is_dl_successful:
                for file_name in os.listdir(Constants.DL_TMP_PATH):
                    formatted_file_name = '%s-%s-%03d-%s' %\
                                          (domain.strip('.com'), thread_no, reply_no, __format_file_name(file_name))
                    os.rename(Constants.DL_TMP_PATH + file_name, Constants.DL_DESTINATION_PATH + formatted_file_name)
                    log("%s" % (Constants.DUMP_PATH + formatted_file_name), has_tst=True)
                    log('[ V ] <- %.f" \t<- %.f"\t: %s #%d  \t->  \t%s'
                        % (prev_pause, prev_prev_pause, thread_url, reply_no, source_url),
                        file_name=Constants.DL_LOG_FILE)
        except selenium.common.exceptions.NoSuchElementException:
            err_soup = BeautifulSoup(tmp_browser.page_source, common.Constants.HTML_PARSER)
            if err_soup.select_one('div#expired > p.notice'):
                log('Sorry, the link has been expired.', has_tst=True)
                log('[ - ] <- %.f" \t<- %.f"\t: %s #%d  \t-!->\t%s' %
                    (prev_pause, prev_prev_pause, thread_url, reply_no, source_url),
                    file_name=Constants.DL_LOG_FILE, has_tst=True)
            elif err_soup.select_one('div#delete > p.delete'):
                log('Error: Cannot locate the download button(삭제하시겠습니까?).', has_tst=True)
            else:
                log('Error: Cannot locate the download button.', has_tst=True)
                log('Error: Cannot locate the download button.\n[Page source]\n' + err_soup.prettify(), str(thread_no))
        except FileNotFoundError as file_exception:
            log('Error: The local file not found.\n%s' % file_exception)
        except Exception as tmpstorage_exception:
            file_name = 'exception-tmpstorage.pv'
            log('Error: Cannot retrieve tmpstorage source(%s).' % tmpstorage_exception, has_tst=True)
            log('Exception: %s\n\n[Traceback]\n%s' %
                (tmpstorage_exception, traceback.format_exc()), file_name)
            err_soup = BeautifulSoup(tmp_browser.page_source, common.Constants.HTML_PARSER)
            log('\n\n[Page source]\n' + err_soup.prettify(), file_name)
        finally:
            tmp_browser.quit()
            common.check_dir_exists(Constants.DL_TMP_PATH)
            for file_name in os.listdir(Constants.DL_TMP_PATH):  # Clear the tmp directory.
                os.rename(Constants.DL_TMP_PATH + file_name, Constants.DL_DESTINATION_PATH + file_name)
                log("%s" % (Constants.DUMP_PATH + file_name), has_tst=True)
                log('[ / ] <- %.f" \t<- %.f"\t: %s #%d  \t->  \t%s' %
                    (prev_pause, prev_prev_pause, thread_url, reply_no, source_url),
                    file_name=Constants.DL_LOG_FILE)

    elif domain == 'ibb.co':
        source = requests.get(source_url).text
        soup = BeautifulSoup(source, common.Constants.HTML_PARSER)
        target_tag = soup.select_one('div#image-viewer-container > img')
        if not target_tag:  # An empty tag, returning None.
            if soup.select_one('div.page-not-found'):
                log('Error: Cannot download imgbb link quoted at #%d.' % reply_no, has_tst=True)
            else:
                log('Error: Unknown structure on ' + domain + '\n\n' + soup.prettify(), str(thread_no))
        else:  # The image link tag present
            # Try retrieving the link.
            target_url = target_tag['src']
            file_name = common.split_on_last_pattern(target_url, '/')[-1]

            local_name = '%s-%s-%02d-%s' % ('ibb', thread_no, reply_no, __format_file_name(file_name))
            return target_url, local_name

    elif domain == 'tmpfiles.org':
        log('Warning: Unusual upload at #%d: tmpfiles.org.' % reply_no)
    elif domain == 'sendvid.com':
        log('Warning: Unusual upload at #%d: sendvid.org.' % reply_no)
    elif domain == 'freethread.net':
        print('%s quoted at #%d.' % (source_url, reply_no))
    elif domain == 'image.kilho.net':
        print("'image.kilho.net' quoted at #%d." % reply_no)
    else:
        log('Warning: Unknown source at #%d.(%s)' % (reply_no, source_url))


def retrieve_content_type(target_url):
    session = requests.Session()
    headers = session.get(target_url).headers['Content-Type'].split('/')
    session.close()
    return headers
