import os
import requests
from urllib.parse import urlparse


def download(url: str, source_id: str):
    # Set the absolute path to store the downloaded file.
    with open('download_destination_path.pv') as f:
        download_destination_path = f.read().strip('\n')
    if not os.path.exists(download_destination_path):
        os.makedirs(download_destination_path)  # create folder if it does not exist

    # Set the download target.
    file_url = __get_file_url(url)
    r = requests.get(file_url, stream=True)
    # TODO: Format to 'j8Gs-107432.jpg'
    filename = source_id + '-' + file_url.split('/')[-1].replace(" ", "_")  # be careful with file names
    file_path = os.path.join(download_destination_path, filename)
    if r.ok:
        print("saving to", os.path.abspath(file_path))
        with open(file_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024 * 8):
                if chunk:
                    f.write(chunk)
                    f.flush()
                    os.fsync(f.fileno())
    else:  # HTTP status code 4XX/5XX
        print("Download failed: status code {}\n{}".format(r.status_code, r.text))


def __get_file_url(page_url: str) -> str:
    domain = urlparse(page_url).netloc.replace('www', '')
    if domain == 'imgdb.in':
        return page_url + '.jpg'
    else:
        # TODO: email the pattern
        return page_url + '.jpg'
