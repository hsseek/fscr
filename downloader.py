import os
import traceback

import selenium.common.exceptions
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
import requests
from urllib.parse import urlparse
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time


def read_from_file(path: str):
    with open(path) as f:
        return f.read().strip('\n')


LOG_PATH = read_from_file('LOG_PATH.pv')
DRIVER_PATH = read_from_file('DRIVER_PATH.pv')
DESTINATION_PATH = read_from_file('download_destination_path.pv')


def log(message: str):
    with open(LOG_PATH, 'a') as f:
        f.write(message + '\n')
    print(message)


def initiate_browser():
    # A chrome web driver with headless option
    service = Service(DRIVER_PATH)
    options = webdriver.ChromeOptions()
    options.add_experimental_option("prefs", {"download.default_directory": DESTINATION_PATH})
    options.add_argument('headless')
    options.add_argument('disable-gpu')
    # options.add_experimental_option("detach", True)
    driver = webdriver.Chrome(service=service, options=options)
    return driver


def __format_file_name(file_name: str) -> str:
    chunks = __split_on_last_pattern(file_name, '.')
    return chunks[0].strip().replace(' ', '-').replace('.', '-') + '.' + chunks[1]


def wait_downloading():
    seconds = 0
    check_interval = 1
    is_downloading = False
    temp_extension = '.crdownload'
    temp_file_name = ''

    while not is_downloading and seconds < 5:  # Loop up to 5 seconds to locate downloading file.
        for file_name in os.listdir(DESTINATION_PATH):
            if file_name.endswith(temp_extension):
                # A temporary chrome downloading file detected.
                is_downloading = True
                temp_file_name = file_name.replace(' (1)' + temp_extension, temp_extension)
                break
        seconds += check_interval
        time.sleep(check_interval)
    if is_downloading:
        last_file_size = 0
        # TODO: Use async thread.
        while is_downloading and os.path.exists(DESTINATION_PATH + temp_file_name) and seconds < 30:
            current_file_size = os.path.getsize(DESTINATION_PATH + temp_file_name)
            if current_file_size == last_file_size:
                # Download finished, while the file name hasn't been properly changed.
                # (Unless downloading speed is slower than 1 byte/sec.)
                break
            last_file_size = current_file_size  # Update the file size.
            time.sleep(check_interval)
            seconds += check_interval
        # Rename temporary files: Download not finished, duplicated, ...
        for file in os.listdir(DESTINATION_PATH):
            if file.endswith(temp_extension):
                if file.endswith(' (1)' + temp_extension):  # Remove duplicates : filename.gif (1).crdownload
                    os.remove(DESTINATION_PATH + file)
                else:
                    os.rename(DESTINATION_PATH + file, DESTINATION_PATH + file.replace(temp_extension, ''))
    else:
        log("Warning: A .crdownload file not detected.(Too quickly finished?)")


def download(source_url: str, thread_no: int, reply_no: int):
    if not os.path.exists(DESTINATION_PATH):
        os.makedirs(DESTINATION_PATH)  # create folder if it does not exist

    # Set the download target.
    try:
        target = __extract_download_target(source_url, thread_no, reply_no)
        if target is not None:  # If None, a respective error message has been issued in __extract method.
            file_url = target[0]  # The url on the server
            file_name = target[1]  # A file name to store in local
            request = requests.get(file_url, stream=True)
            file_path = os.path.join(DESTINATION_PATH, file_name)
            with open(file_path, 'wb') as f:
                for chunk in request.iter_content(chunk_size=1024 * 8):
                    if chunk:
                        f.write(chunk)
                        f.flush()
                        os.fsync(f.fileno())
            log("Stored as %s" % file_name)
    except Exception as download_exception:
        log("Error: Download failed.(%s)" % download_exception)


def __extract_download_target(page_url: str, source_id: int, reply_no: int) -> []:
    domain = urlparse(page_url).netloc.replace('www', '')
    html_parser = 'html.parser'
    if domain == 'imgdb.in':
        source = requests.get(page_url).text
        soup = BeautifulSoup(source, html_parser)
        target_tag = soup.select_one('link')
        # id's
        int_index = __format_url_index(__get_url_index(page_url))
        if not target_tag:  # Empty
            if '/?err=1";' in soup.select_one('script').text:
                # ?err=1 redirects to "이미지가 삭제된 주소입니다."
                log('Error: Cannot download %s quoted in %s #%s(이미지가 삭제된 주소입니다.)'
                    % (int_index, source_id, reply_no))
            else:
                log('Error: Unknown structure on ' + domain + '\n\n' + soup.prettify())
        else:  # <link> tag present
            target_url = target_tag['href']  # url of the file to download
            target_extension = target_url.split('.')[-1]
            if target_extension == 'dn':
                log('삭제된 이미지입니다.(A gentle error: image.dn)')  # Likely to be a file in a wrong format
            else:
                local_name = '%s-%03d-%s.%s' % (int_index, reply_no, source_id, target_extension)
                return [target_url, local_name]

    # Unusual sources: Consider parsing if used often.
    elif domain == 'tmpstorage.com':  # Returns None: download directly from the chrome driver.
        browser = initiate_browser()
        try:
            browser.get(page_url)
            browser.find_element(By.XPATH, '/html/body/div[2]/div/p/a').send_keys(Keys.ALT, Keys.ENTER)
            download_soup = BeautifulSoup(browser.page_source, html_parser)
            file_name = download_soup.select_one('div#download > h1.filename').string
            wait_downloading()  # Wait for seconds.

            local_name = '%s-%s-%03d-%s' % (
                domain.strip('.com'), source_id, reply_no, __format_file_name(file_name))
            os.rename(DESTINATION_PATH + file_name,
                      DESTINATION_PATH + local_name)
            log("Stored as %s." % local_name)
        except selenium.common.exceptions.NoSuchElementException:
            err_soup = BeautifulSoup(browser.page_source, html_parser)
            if err_soup.select_one('div#expired > p.notice'):
                log('Error: The file has been deleted.')
            else:
                log('Error: Cannot locate the download button(The file might have been deleted).')
        except FileNotFoundError as file_exception:
            log('Error: The file not found.\n%s' % file_exception)
        except Exception as tmpstorage_exception:
            log('Error: Cannot retrieve tempstroage source(%s).\n[Traceback]\n%s' %
                (tmpstorage_exception, traceback.format_exc()))
        finally:
            browser.quit()

    elif domain == 'tmpfiles.org':
        log('Error: Unusual upload on %s: tmpfiles.org' % source_id)
    elif domain == 'https://sendvid.com/':
        log('Error: Unusual upload on %s: sendvid.org' % source_id)
    else:
        log('Error: Unknown source on %s: %s' % (source_id, page_url))


def __get_url_index(url: str) -> []:
    url_index = []  # for example, url_index = [3, 5, 1, 9] (a list of int)
    str_index = __split_on_last_pattern(url, '/')[-1]  # 'a3Fx' from 'https://domain.com/a3Fx'
    with open('SEQUENCE.pv', 'r') as file:
        sequence = file.read().split('\n')

    for char in str_index:  # a -> 3 -> F -> x
        for n, candidates in enumerate(sequence):
            if char == candidates:
                url_index.append(n)  # Found the matching index
                break
    return url_index


def __format_url_index(url_index: []) -> str:
    formatted_index = ''
    for index in url_index:
        formatted_index += '%02d' % index
    return formatted_index  # '19092307'


def __split_on_last_pattern(string: str, pattern: str) -> []:
    last_piece = string.split(pattern)[-1]  # domain.com/image.jpg -> jpg
    leading_chunks = string.split(pattern)[:-1]  # [domain, com/image]
    leading_piece = pattern.join(leading_chunks)  # domain.com/image
    return [leading_piece, last_piece]  # [domain.com/image, jpg]
