import os
from bs4 import BeautifulSoup
import requests
from urllib.parse import urlparse


def download(page_url: str, source_id: str):
    # Set the absolute path to store the downloaded file.
    with open('download_destination_path.pv') as f:
        download_destination_path = f.read().strip('\n')
    if not os.path.exists(download_destination_path):
        os.makedirs(download_destination_path)  # create folder if it does not exist

    # Set the download target.
    target = __extract_download_target(page_url, source_id)
    if target is not None:  # If None, a respective error message has been issued in __extract method.
        file_url = target[0]  # The url on the server
        file_name = target[1]  # A file name to store in local
        r = requests.get(file_url, stream=True)
        file_path = os.path.join(download_destination_path, file_name)
        if r.ok:
            print("saving to", os.path.abspath(file_path))
            with open(file_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024 * 8):
                    if chunk:
                        f.write(chunk)
                        f.flush()
                        os.fsync(f.fileno())
        else:  # HTTP status code 4??/5??
            print("Download failed: status code {}\n{}".format(r.status_code, r.text))


def __extract_download_target(page_url: str, source_id: str) -> []:
    domain = urlparse(page_url).netloc.replace('www', '')
    if domain == 'imgdb.in':
        # TODO: Don't try downloading if the file is not available.
        # TODO: Retrieve the original extension (instead of assuming jpg)
        # TODO: Format to 'a82s-107432.jpg'
        source = requests.get(page_url).text
        soup = BeautifulSoup(source, 'html.parser')
        target_tag = soup.select_one('link')
        if not target_tag:  # Empty
            if '/?err=1";' in soup.select_one('script').text:
                # ?err=1 redirects to "이미지가 삭제된 주소입니다."
                print('이미지가 삭제된 주소입니다.')
            else:
                print('Unknown error with:\n\n' + soup.prettify())
        else:
            if target_tag['href'].split('.')[-1] == 'dn':
                print('삭제된 이미지입니다.jpg')  # Likely to be a file in a wrong format
            else:  # The page available
                target_url = target_tag['href']  # url of the file to download
                target_extension = target_url.split('.')[-1]
                imgdb_id = page_url.split('/')[-1]
                local_name = imgdb_id + '-' + source_id + '.' + target_extension
                return [target_url, local_name]
    else:
        # TODO: Unknown source page. Email the pattern
        print('Unknown source: ' + page_url)
        target_url = page_url.split('/')[-1] + '.jpg'  # Guessing the file url (Hardly works)
        return [target_url, target_url]


def split_on_last_pattern(string: str, pattern: str) -> []:
    last_piece = string.split(pattern)[-1]  # domain.com/image.jpg -> jpg
    leading_chunks = string.split(pattern)[:-1]  # [domain, com/image]
    leading_piece = pattern.join(leading_chunks)  # domain.com/image
    return [leading_piece, last_piece]  # [domain.com/image, jpg]
