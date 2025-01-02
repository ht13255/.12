import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from bloom_filter2 import BloomFilter
import json
import csv
import os
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

# 헤더 설정 (User-Agent 회전)
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

# 멀티스레드 개수 고정
MAX_THREADS = 300

# 요청 재시도 메커니즘
def make_request(url, session, retries=3):
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    for attempt in range(retries):
        try:
            response = session.get(url, headers=headers, timeout=2)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            st.warning(f"HTTP 오류 (코드 {response.status_code}) on {url}: {e}")
            break  # HTTP 에러는 재시도하지 않음
        except requests.exceptions.RequestException as e:
            if attempt < retries - 1:
                time.sleep(1)  # 재시도 전 대기
            else:
                st.warning(f"요청 실패 after {retries} retries: {url} - {e}")
    return None

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

# 내부 링크 추출
def extract_internal_links(base_url, session, bloom_filter):
    response = make_request(base_url, session)
    if not response:
        return []

    try:
        soup = BeautifulSoup(response.text, 'html.parser')
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
def crawl_link(url, session):
    response = make_request(url, session)
    if not response:
        return {"url": url, "content": None}

    try:
        soup = BeautifulSoup(response.text, 'html.parser')
        content = soup.get_text(strip=True)
        return {"url": url, "content": content}
    except Exception as e:
        st.error(f"링크 크롤링 오류: {e}")
        return {"url": url, "content": None}

# 재귀적으로 크롤링
def recursive_crawl(base_url, max_depth, progress_callback=None):
    session = requests.Session()
    bloom_filter = BloomFilter(max_elements=1000000, error_rate=0.01)
    all_data = []
    visited_count = 0  # Progress tracking

    def crawl_recursive(urls, depth):
        nonlocal visited_count
        if depth > max_depth or not urls:
            return []

        next_urls = []
        with ThreadPoolExecutor(MAX_THREADS) as executor:
            futures = {executor.submit(crawl_link, url, session): url for url in urls}
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
        for url in urls:
            links = extract_internal_links(url, session, bloom_filter)
            next_urls.extend(links)

        return crawl_recursive(next_urls, depth + 1)

    crawl_recursive([base_url], 1)
    return all_data

# 작업 저장
def save_to_file(data, filename, file_type='json'):
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
st.set_page_config(page_title="HTTP 오류 방지 크롤러", layout="centered")

st.title("HTTP 오류 방지 크롤러")
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
            # 항상 최대 깊이를 유지
            max_depth = 10  # 최대 깊이
            crawled_data = recursive_crawl(base_url, max_depth, progress_callback)

            # 파일 저장
            timestamp = int(time.time())
            filename = f"crawled_data_{timestamp}.{file_type}"
            filepath = save_to_file(crawled_data, filename, file_type)

            if filepath:
                st.success("크롤링 완료!")
                with open(filepath, "rb") as f:
                    st.download_button("결과 다운로드", data=f.read(), file_name=filename)
        except Exception as e:
            st.error(f"크롤링 오류: {e}")
    else:
        st.error("URL을 입력하세요!")