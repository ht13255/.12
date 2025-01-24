import streamlit as st
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from bloom_filter2 import BloomFilter
import json
import re
import os
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed

# User-Agent 리스트
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
]

# 제외할 도메인 및 URL 키워드
EXCLUDE_DOMAINS = [
    "facebook.com", "instagram.com", "twitter.com", "linkedin.com", "youtube.com",
    "pinterest.com", "tumblr.com", "reddit.com", "tiktok.com"
]
EXCLUDE_KEYWORDS = [
    "ad", "ads", "login", "signup", "register", "subscribe", ".jpg", ".png", ".gif", ".mp4", ".mov", ".avi", ".webm"
]

# 고정된 설정
MAX_THREADS = min(os.cpu_count() * 10, 1000)
MAX_DEPTH = 5
BATCH_SIZE = 2000

# Streamlit 페이지 구성
st.set_page_config(page_title="학습 데이터 크롤러", layout="wide")
st.title("학습 데이터 크롤러")
st.markdown("**GPT 학습 자료로 업로드하기 전 데이터를 필터링하고 편집합니다.**")

base_url = st.text_input("크롤링할 URL 입력:")
file_type = st.selectbox("저장 형식 선택", ["json", "csv", "jsonl"])

# 민감한 데이터 패턴 (예: 이메일, 전화번호)
SENSITIVE_PATTERNS = [
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    r"\b\d{3}[-.\s]??\d{3}[-.\s]??\d{4}\b",  # 전화번호 패턴
]

# 데이터 필터링 함수
def sanitize_content(content):
    """민감한 데이터를 제거하여 텍스트를 정리"""
    for pattern in SENSITIVE_PATTERNS:
        content = re.sub(pattern, "[FILTERED]", content)
    return content.strip()

if st.button("크롤링 시작"):
    if not base_url:
        st.error("URL을 입력하세요!")
    else:
        session = requests.Session()
        retries = Retry(
            total=5,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # 초기화
        base_domain = urlparse(base_url).netloc
        bloom_filter = BloomFilter(max_elements=1000000, error_rate=0.01)
        collected_links = []
        all_data = []

        # 함수 정의
        def is_excluded_link(url):
            """외부 링크 및 제외 조건 필터링"""
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.lower()
            if domain != base_domain:  # 외부 링크 제외
                return True
            if any(excluded_domain in domain for excluded_domain in EXCLUDE_DOMAINS):
                return True
            if any(keyword in url.lower() for keyword in EXCLUDE_KEYWORDS):
                return True
            return False

        def extract_links(url):
            """링크 추출 및 유효성 검사"""
            try:
                response = session.get(url, headers={"User-Agent": USER_AGENTS[0]}, timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                links = []
                for link in soup.find_all("a", href=True):
                    full_url = urljoin(base_url, link["href"])
                    if full_url not in bloom_filter and not is_excluded_link(full_url):
                        bloom_filter.add(full_url)
                        links.append(full_url)
                return links
            except Exception as e:
                st.warning(f"링크 추출 실패: {url} - {e}")
                return []

        def crawl_content(url):
            """URL에서 콘텐츠 크롤링"""
            try:
                response = session.get(url, headers={"User-Agent": USER_AGENTS[0]}, timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                content = sanitize_content(soup.get_text(strip=True))  # 민감 데이터 제거
                return {"url": url, "content": content}
            except Exception as e:
                st.warning(f"콘텐츠 크롤링 실패: {url} - {e}")
                return {"url": url, "content": None}

        # 링크 수집
        st.info("링크를 수집 중입니다...")
        queue = [base_url]
        for depth in range(MAX_DEPTH):
            next_queue = []
            with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
                futures = {executor.submit(extract_links, url): url for url in queue}
                for future in as_completed(futures):
                    links = future.result()
                    if links:
                        collected_links.extend(links)
                        next_queue.extend(links)
            queue = next_queue
        st.success(f"총 {len(collected_links)}개의 링크 수집 완료.")

        # 콘텐츠 크롤링
        st.info("콘텐츠를 크롤링 중입니다...")
        for batch_start in range(0, len(collected_links), BATCH_SIZE):
            batch = collected_links[batch_start:batch_start + BATCH_SIZE]
            with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
                futures = {executor.submit(crawl_content, url): url for url in batch}
                for future in as_completed(futures):
                    result = future.result()
                    if result and result["content"]:
                        all_data.append(result)
        st.success(f"콘텐츠 크롤링 완료! 총 {len(all_data)}개의 데이터 수집.")

        # 데이터 편집
        st.write("**크롤링 결과를 검토 및 편집하세요:**")
        for idx, item in enumerate(all_data):
            item["content"] = st.text_area(f"URL: {item['url']}", item["content"], key=f"content_{idx}")

        # 파일 저장
        st.info("파일 저장 중...")
        timestamp = int(time.time())
        if file_type == "json":
            file_name = f"crawled_data_{timestamp}.json"
            with open(file_name, "w", encoding="utf-8") as f:
                json.dump(all_data, f, ensure_ascii=False, indent=4)
        elif file_type == "csv":
            file_name = f"crawled_data_{timestamp}.csv"
            with open(file_name, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["URL", "Content"])
                for item in all_data:
                    writer.writerow([item["url"], item["content"]])
        elif file_type == "jsonl":
            file_name = f"crawled_data_{timestamp}.jsonl"
            with open(file_name, "w", encoding="utf-8") as f:
                for item in all_data:
                    json.dump(item, f, ensure_ascii=False)
                    f.write("\n")
        st.success(f"파일 저장 완료: {file_name}")
        with open(file_name, "rb") as f:
            st.download_button("결과 다운로드", data=f, file_name=file_name)