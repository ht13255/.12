import streamlit as st
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from bloom_filter2 import BloomFilter
import json
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

# 멀티스레드 설정
MAX_THREADS = 300
CHUNK_SIZE = 500  # 한 번에 처리할 링크 개수

# Bloom Filter 설정
BLOOM_FILTER_CAPACITY = 10000000
BLOOM_FILTER_ERROR_RATE = 0.01

@st.cache_resource
def create_session():
    """HTTP 세션 생성 및 재시도 정책 설정"""
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

# 링크 필터링 함수
def is_excluded_link(url):
    exclude_keywords = [
        "ad", "cookie", "popup", "login", "signup", "banner", ".jpg", ".png", ".gif", ".mp4", ".mov", ".avi"
    ]
    return any(keyword in url.lower() for keyword in exclude_keywords)

# 요청 함수
def make_request(url, session):
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        response = session.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        return response
    except Exception as e:
        st.warning(f"요청 실패: {url} - {e}")
    return None

# 링크 추출 함수
def extract_links(base_url, session, bloom_filter):
    response = make_request(base_url, session)
    if not response:
        return []

    try:
        soup = BeautifulSoup(response.text, "html.parser")
        links = set()
        for link in soup.find_all("a", href=True):
            url = urljoin(base_url, link["href"])
            if url not in bloom_filter and not is_excluded_link(url):
                links.add(url)
                bloom_filter.add(url)
        return list(links)
    except Exception as e:
        st.error(f"링크 추출 오류: {e}")
        return []

# 링크 크롤링 함수
def crawl_link(url, session):
    response = make_request(url, session)
    if not response:
        return {"url": url, "content": None}

    try:
        soup = BeautifulSoup(response.text, "html.parser")
        content = soup.get_text(strip=True)
        return {"url": url, "content": content}
    except Exception as e:
        st.error(f"크롤링 오류: {e}")
        return {"url": url, "content": None}

# 대량 크롤링 처리
def bulk_crawl(urls, session):
    results = []
    with ThreadPoolExecutor(MAX_THREADS) as executor:
        futures = {executor.submit(crawl_link, url, session): url for url in urls}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                st.warning(f"스레드 작업 실패: {e}")
    return results

# 상태 저장 함수
def save_progress(data, filepath="progress.json"):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# 진행 상태 불러오기
def load_progress(filepath="progress.json"):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

# 재귀적 크롤링
def recursive_crawl(start_url, max_depth, progress_callback=None):
    session = create_session()
    bloom_filter = BloomFilter(max_elements=BLOOM_FILTER_CAPACITY, error_rate=BLOOM_FILTER_ERROR_RATE)
    to_crawl = [start_url]
    all_results = []
    depth = 1

    while to_crawl and depth <= max_depth:
        chunk = to_crawl[:CHUNK_SIZE]
        to_crawl = to_crawl[CHUNK_SIZE:]

        # 크롤링 처리
        results = bulk_crawl(chunk, session)
        all_results.extend(results)

        # 링크 추출 및 큐에 추가
        for result in results:
            if result["content"]:
                links = extract_links(result["url"], session, bloom_filter)
                to_crawl.extend(links)

        # 진행 상황 업데이트 및 상태 저장
        if progress_callback:
            progress_callback(len(all_results), len(to_crawl))
        save_progress(all_results)

        depth += 1

    return all_results

# Streamlit UI
st.set_page_config(page_title="대량 링크 크롤러", layout="wide")

st.title("대량 링크 크롤러")
st.markdown("**만 개 이상의 링크를 안정적으로 크롤링합니다.**")

base_url = st.text_input("크롤링할 URL을 입력하세요 (HTTP/HTTPS):")
max_depth = st.slider("크롤링 깊이", 1, 20, 5)

if st.button("크롤링 시작"):
    if base_url:
        progress_bar = st.progress(0)
        status_text = st.empty()

        def progress_callback(crawled, remaining):
            progress_bar.progress(crawled / (crawled + remaining))
            status_text.text(f"크롤링 중: {crawled} 완료, {remaining} 남음")

        try:
            results = recursive_crawl(base_url, max_depth, progress_callback)
            st.success(f"크롤링 완료! 총 {len(results)} 개의 링크 처리.")
            save_file = "crawled_results.json"
            save_progress(results, save_file)
            with open(save_file, "rb") as f:
                st.download_button("결과 다운로드", f, file_name=save_file)
        except Exception as e:
            st.error(f"크롤링 오류: {e}")
    else:
        st.error("URL을 입력하세요!")
