import streamlit as st
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from bloom_filter2 import BloomFilter
import json
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

# User-Agent 리스트
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
]

MAX_THREADS = 100
BATCH_SIZE = 1000

@st.cache_resource
def reset_session():
    """세션 초기화 및 재시도 설정"""
    session = requests.Session()
    retries = Retry(
        total=3,  # 최대 3번 재시도
        backoff_factor=1,  # 재시도 간 1초 대기
        status_forcelist=[500, 502, 503, 504],  # 재시도할 HTTP 상태 코드
        allowed_methods=["GET"]  # 재시도 허용 메서드
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def make_request(url, session):
    """HTTP 요청 함수"""
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response
    except requests.exceptions.HTTPError as e:
        st.warning(f"HTTP 오류 (URL: {url}): {e}")
    except requests.exceptions.RequestException as e:
        st.warning(f"요청 실패 (URL: {url}): {e}")
    return None

def crawl_link(url, session, failed_links):
    """링크 내용을 크롤링"""
    response = make_request(url, session)
    if not response:
        failed_links.append(url)
        return {"url": url, "content": None}

    try:
        soup = BeautifulSoup(response.text, "html.parser")
        content = soup.get_text(strip=True)
        return {"url": url, "content": content}
    except Exception as e:
        st.warning(f"파싱 실패 (URL: {url}): {e}")
        failed_links.append(url)
        return {"url": url, "content": None}

def divide_batches(data, batch_size):
    """리스트를 batch_size 단위로 분할"""
    for i in range(0, len(data), batch_size):
        yield data[i:i + batch_size]

def recursive_crawl(base_url, max_depth):
    """재귀적으로 링크를 크롤링"""
    session = reset_session()
    bloom_filter = BloomFilter(max_elements=100000, error_rate=0.01)
    all_data = []
    failed_links = []
    visited_count = 0

    def crawl_recursive(urls, depth):
        nonlocal visited_count
        if depth > max_depth or not urls:
            return []

        next_urls = []
        for batch in divide_batches(urls, BATCH_SIZE):
            with ThreadPoolExecutor(MAX_THREADS) as executor:
                futures = {executor.submit(crawl_link, url, session, failed_links): url for url in batch}
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        visited_count += 1
                        if result["content"]:
                            all_data.append(result)
                    except Exception as e:
                        st.warning(f"스레드 작업 오류: {e}")

            # 내부 링크 추출 (단순화)
            for url in batch:
                response = make_request(url, session)
                if response:
                    soup = BeautifulSoup(response.text, "html.parser")
                    for link in soup.find_all('a', href=True):
                        full_url = urljoin(base_url, link['href'])
                        if full_url not in bloom_filter:
                            bloom_filter.add(full_url)
                            next_urls.append(full_url)

        crawl_recursive(next_urls, depth + 1)

    crawl_recursive([base_url], 1)
    return all_data, failed_links

# Streamlit UI
st.set_page_config(page_title="HTTP 요청 지속 크롤러", layout="centered")

st.title("HTTP 요청 지속 크롤러")
st.markdown("**URL을 입력하고 크롤링 옵션을 설정하세요.**")

base_url = st.text_input("크롤링할 URL을 입력하세요 (HTTP/HTTPS 모두 지원):")
file_type = st.selectbox("저장 형식 선택", ["json", "csv"])

if st.button("크롤링 시작"):
    if base_url:
        progress_bar = st.progress(0)
        try:
            max_depth = 3  # 최대 깊이
            crawled_data, failed_links = recursive_crawl(base_url, max_depth)

            # 결과 저장
            timestamp = int(time.time())
            if file_type == "json":
                file_name = f"crawled_data_{timestamp}.json"
                with open(file_name, "w", encoding="utf-8") as f:
                    json.dump(crawled_data, f, ensure_ascii=False, indent=4)
                st.download_button("결과 다운로드 (JSON)", data=open(file_name, "rb").read(), file_name=file_name)

            # 오류 링크 출력
            if failed_links:
                st.warning(f"실패한 링크 {len(failed_links)}개가 있습니다.")
                st.write(failed_links)
        except Exception as e:
            st.error(f"크롤링 오류: {e}")
    else:
        st.error("URL을 입력하세요!")