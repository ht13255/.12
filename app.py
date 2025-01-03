import streamlit as st
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from bloom_filter2 import BloomFilter
import json
import csv
import os
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

# User-Agent 리스트
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
]

# 제외할 링크 키워드와 도메인
EXCLUDE_KEYWORDS = [
    "ad", "ads", "google", "facebook", "twitter", "instagram", "mail", "bet", "community", "login", "youtube",
    "pinterest", "linkedin", "tumblr", "reddit", "tiktok", ".jpg", ".png", ".gif", ".mp4", ".mov", ".avi", ".webm"
]
EXCLUDE_DOMAINS = [
    "google.com", "facebook.com", "twitter.com", "instagram.com", "youtube.com",
    "pinterest.com", "linkedin.com", "tumblr.com", "reddit.com", "tiktok.com"
]

# 제외할 HTML 요소 패턴
EXCLUDE_PATTERNS = ["cookie", "banner", "popup", "guide", "ad", "subscribe", "footer", "header"]

# 멀티스레드 개수 고정
MAX_THREADS = 300
BATCH_SIZE = 2000  # 한 번에 처리할 최대 링크 수

# 초기화 세션 정보
@st.cache_resource
def reset_session():
    """세션 초기화 및 재시도 설정"""
    session = requests.Session()
    retries = Retry(
        total=5,  # 총 재시도 횟수
        backoff_factor=0.5,  # 재시도 간 대기 시간 증가
        status_forcelist=[429, 500, 502, 503, 504],  # 재시도할 HTTP 상태 코드
        allowed_methods=["GET"]  # 재시도 허용 메서드
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

# 링크 필터링 함수
def is_excluded_link(url):
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.lower()

    # 도메인 기반 필터링
    if any(excluded_domain in domain for excluded_domain in EXCLUDE_DOMAINS):
        return True

    # 키워드 기반 필터링
    for keyword in EXCLUDE_KEYWORDS:
        if keyword in url.lower():
            return True

    return False

# 리스트를 배치로 나누기
def divide_batches(data, batch_size):
    """리스트를 batch_size 단위로 분할"""
    for i in range(0, len(data), batch_size):
        yield data[i:i + batch_size]

# 요청 보내기 함수
@st.cache_data
def make_request(url, _session):
    """HTTP 요청 함수"""
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        response = _session.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        st.warning(f"요청 오류: {url} - {e}")
    return None

# HTML에서 제외할 요소 제거
def clean_html(soup):
    """HTML에서 불필요한 요소 제거"""
    for pattern in EXCLUDE_PATTERNS:
        for element in soup.find_all(class_=lambda value: value and pattern in value.lower()):
            element.decompose()
        for element in soup.find_all(id=lambda value: value and pattern in value.lower()):
            element.decompose()
    return soup

# 내부 링크 추출
def extract_internal_links(base_url, session, bloom_filter):
    """내부 링크를 추출"""
    response = make_request(base_url, session)
    if not response:
        return []

    try:
        soup = BeautifulSoup(response.text, 'html.parser')
        soup = clean_html(soup)  # 불필요한 요소 제거

        internal_links = set()
        for link in soup.find_all('a', href=True):
            url = urljoin(base_url, link['href'])

            # 필터링 조건 확인
            if url in bloom_filter or is_excluded_link(url):
                continue

            internal_links.add(url)
            bloom_filter.add(url)

        return list(internal_links)
    except Exception as e:
        st.error(f"내부 링크 추출 오류: {e}")
        return []

# 링크 내용 크롤링
def crawl_link(url, session, failed_links):
    """링크 내용을 크롤링"""
    response = make_request(url, session)
    if not response:
        failed_links.append(url)
        return {"url": url, "content": None}

    try:
        soup = BeautifulSoup(response.text, 'html.parser')
        soup = clean_html(soup)  # 불필요한 요소 제거
        content = soup.get_text(strip=True)
        return {"url": url, "content": content}
    except Exception as e:
        st.error(f"링크 크롤링 오류: {e}")
        failed_links.append(url)
        return {"url": url, "content": None}

# 재귀적으로 크롤링
def recursive_crawl(base_url, max_depth, progress_callback=None):
    """재귀적으로 링크를 크롤링"""
    session = reset_session()  # 세션 초기화
    bloom_filter = BloomFilter(max_elements=1000000, error_rate=0.01)
    all_data = []
    failed_links = []  # 오류 발생 링크 저장
    visited_count = 0  # Progress tracking

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
                        if progress_callback:
                            progress_callback(visited_count, len(urls))
                        if result["content"]:
                            all_data.append(result)
                    except Exception as e:
                        st.warning(f"스레드 작업 오류: {e}")

            # 내부 링크 추출 (다음 깊이로 이동)
            for url in batch:
                links = extract_internal_links(url, session, bloom_filter)
                next_urls.extend(links)

        return crawl_recursive(next_urls, depth + 1)

    crawl_recursive([base_url], 1)
    return all_data, failed_links

# 작업 저장
def save_to_file(data, filename, file_type='json'):
    """결과를 파일에 저장"""
    try:
        os.makedirs("output", exist_ok=True)
        filepath = os.path.join("output", filename)

        if file_type == 'json':
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        elif file_type == 'csv':
            with open(filepath, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["URL", "Content"])
                for entry in data:
                    writer.writerow([entry["url"], entry["content"]])

        return filepath
    except Exception as e:
        st.error(f"파일 저장 오류: {e}")
        return None

# Streamlit UI
st.set_page_config(page_title="HTTP 요청 지속 크롤러", layout="centered")

st.title("HTTP 요청 지속 크롤러")
st.markdown("**URL을 입력하고 크롤링 옵션을 설정하세요.**")

base_url = st.text_input("크롤링할 URL을 입력하세요 (HTTP/HTTPS 모두 지원):")
file_type = st.selectbox("저장 형식 선택", ["json", "csv"])

if st.button("크롤링 시작"):
    if base_url:
        progress_bar = st.progress(0)
        status_text = st.empty()

        def progress_callback(current, total):
            progress_bar.progress(min(current / total, 1.0))
            status_text.text(f"진행 중: {current}/{total} 링크 처리")

        try:
            max_depth = 10  # 최대 깊이
            crawled_data, failed_links = recursive_crawl(base_url, max_depth, progress_callback)

            # 파일 저장
            timestamp = int(time.time())
            filename = f"crawled_data_{timestamp}.{file_type}"
            filepath = save_to_file(crawled_data, filename, file_type)

            if filepath:
                st.success("크롤링 완료!")
                with open(filepath, "rb") as f:
                    st.download_button("결과 다운로드", data=f.read(), file_name=filename)

            # 오류 발생 링크 표시
            if failed_links:
                st.warning(f"오류가 발생한 링크 {len(failed_links)}개가 있습니다.")
                st.write(failed_links)

        except Exception as e:
            st.error(f"크롤링 오류: {e}")
    else:
        st.error("URL을 입력하세요!")