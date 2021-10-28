import os
from bs4 import BeautifulSoup
import requests
from urllib.parse import urlparse


def read_from_file(path: str):
    with open(path) as f:
        return f.read().strip('\n')


LOG_PATH = read_from_file('LOG_PATH.pv')


def log(message: str):
    with open(LOG_PATH, 'a') as f:
        f.write(message + '\n')
    print(message)


def download(source_url: str, thread_no: int, reply_no: int):
    # Set the absolute path to store the downloaded file.
    with open('download_destination_path.pv') as f:
        download_destination_path = f.read().strip('\n')
    if not os.path.exists(download_destination_path):
        os.makedirs(download_destination_path)  # create folder if it does not exist

    # Set the download target.
    target = __extract_download_target(source_url, thread_no, reply_no)
    if target is not None:  # If None, a respective error message has been issued in __extract method.
        file_url = target[0]  # The url on the server
        file_name = target[1]  # A file name to store in local
        r = requests.get(file_url, stream=True)
        file_path = os.path.join(download_destination_path, file_name)
        if r.ok:
            with open(file_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024 * 8):
                    if chunk:
                        f.write(chunk)
                        f.flush()
                        os.fsync(f.fileno())
            log("Stored to " + str(os.path.abspath(file_path)))
        else:  # HTTP status code 4??/5??
            log("Download failed: status code {}\n{}".format(r.status_code, r.text))


def __extract_download_target(page_url: str, source_id: int, reply_no: int) -> []:
    domain = urlparse(page_url).netloc.replace('www', '')
    if domain == 'imgdb.in':
        source = requests.get(page_url).text
        soup = BeautifulSoup(source, 'html.parser')
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
                log('삭제된 이미지입니다(A gentle error: image.dn)')  # Likely to be a file in a wrong format
            else:
                local_name = '%s-%03d-%s.%s' % (int_index, reply_no, source_id, target_extension)
                return [target_url, local_name]

    # Unusual sources: Consider parsing if used often.
    elif domain == 'tmpfiles.org':
        log('Error: Unusual upload on %s: tmpfiles.org' % source_id)
    elif domain == 'tmpstorage.com':
        log('Error: Unusual upload on %s: tmpstorage.org' % source_id)
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
