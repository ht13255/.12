import streamlit as st
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from bloom_filter2 import BloomFilter
import json
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

# User-Agent 리스트
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
]

# 제외할 도메인 및 URL 키워드
EXCLUDE_DOMAINS = [
    "facebook.com", "instagram.com", "twitter.com", "linkedin.com", "youtube.com",
    "pinterest.com", "tumblr.com", "reddit.com", "tiktok.com"
]
EXCLUDE_KEYWORDS = [
    "ad", "ads", "login", "signup", "register", "subscribe", ".jpg", ".png", ".gif", ".mp4", ".mov", ".avi", ".webm"
]

# 필터링할 불필요한 문구
UNNECESSARY_TERMS = [
    "copyright", "rights reserved", "all rights reserved", "terms of service",
    "privacy policy", "cookies", "powered by", "trademark", "©"
]

# 고정된 설정
MAX_DEPTH = 5
MAX_THREADS = min(os.cpu_count() * 10, 1000)
BATCH_SIZE = 2000

# 캐시 삭제
st.cache_data.clear()
st.cache_resource.clear()

# Streamlit 페이지 구성
st.set_page_config(page_title="자동 텍스트 정리 크롤러", layout="centered")
st.title("자동 텍스트 정리 크롤러")
st.markdown("**크롤링 텍스트를 정제하고 불필요한 문구를 자동 제거합니다.**")

# 세션 상태 초기화
if "collected_links" not in st.session_state:
    st.session_state["collected_links"] = []
if "progress" not in st.session_state:
    st.session_state["progress"] = 0

base_url = st.text_input("크롤링할 URL을 입력하세요 (HTTP/HTTPS 모두 지원):")
file_type = st.selectbox("저장 형식 선택", ["json", "csv"])
st.write("크롤링과 정제 후 불필요한 문구를 제거한 텍스트를 저장합니다.")

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
        failed_links = []
        all_data = []
        refined_data = []

        # 함수 정의
        def is_excluded_link(url):
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.lower()

            # 외부 링크 및 제외 조건 필터링
            if domain != base_domain:
                return True
            if any(excluded_domain in domain for excluded_domain in EXCLUDE_DOMAINS):
                return True
            if any(keyword in url.lower() for keyword in EXCLUDE_KEYWORDS):
                return True

            return False

        def is_valid_url(url):
            parsed = urlparse(url)
            return parsed.scheme in ["http", "https"] and bool(parsed.netloc)

        def make_request(url):
            headers = {"User-Agent": USER_AGENTS[0]}  # User-Agent 고정
            try:
                response = session.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                st.warning(f"요청 실패: {url} - {e}")
                failed_links.append(url)
            return None

        def extract_links(url):
            response = make_request(url)
            if not response:
                return []

            try:
                soup = BeautifulSoup(response.text, "html.parser")
                links = []
                for link in soup.find_all("a", href=True):
                    full_url = urljoin(base_url, link["href"])
                    if full_url not in bloom_filter and not is_excluded_link(full_url) and is_valid_url(full_url):
                        bloom_filter.add(full_url)
                        links.append(full_url)
                return links
            except Exception as e:
                st.warning(f"링크 추출 실패: {url} - {e}")
                return []

        def divide_batches(data):
            for i in range(0, len(data), BATCH_SIZE):
                yield data[i:i + BATCH_SIZE]

        def crawl_content(url):
            response = make_request(url)
            if not response:
                return {"url": url, "content": None}

            try:
                soup = BeautifulSoup(response.text, "html.parser")
                content = soup.get_text(strip=True)
                return {"url": url, "content": content}
            except Exception as e:
                st.warning(f"파싱 실패: {url} - {e}")
                failed_links.append(url)
                return {"url": url, "content": None}

        def clean_text(text):
            """텍스트 정제"""
            # HTML 태그, URL, 이메일 제거
            text = re.sub(r"<[^>]*>", "", text)
            text = re.sub(r"http\S+|www\S+", "", text)
            text = re.sub(r"&\w+;", "", text)  # HTML 엔터티 제거
            text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "", text)
            # 불필요한 문구 제거
            for term in UNNECESSARY_TERMS:
                text = re.sub(rf"\b{term}\b", "", text, flags=re.IGNORECASE)
            # 특수문자 및 중복 제거
            text = re.sub(r"[^\w\s.,!?가-힣]", "", text)
            text = re.sub(r"\s+", " ", text)
            text = re.sub(r"(\n|\r)+", "\n", text)
            return text.strip()

        # 1단계: 링크 수집
        st.info("1단계: 내부 링크를 수집 중입니다.")
        progress_bar = st.progress(0)
        status_text = st.empty()

        try:
            queue = [base_url]
            for depth in range(MAX_DEPTH):
                next_queue = []
                batch_count = 0
                for batch in divide_batches(queue):
                    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
                        futures = {executor.submit(extract_links, url): url for url in batch}
                        for future in as_completed(futures):
                            links = future.result()
                            if links:
                                collected_links.extend(links)
                                next_queue.extend(links)
                    batch_count += 1
                    progress = min((batch_count / len(queue)) * 100, 100)
                    st.session_state["progress"] = progress
                    progress_bar.progress(progress / 100)
                    status_text.text(f"진행 중: {len(collected_links)}개의 내부 링크 수집 완료")

                queue = next_queue

            st.session_state["collected_links"] = collected_links
            st.success(f"1단계 완료! 총 {len(collected_links)}개의 내부 링크를 수집했습니다.")

        except Exception as e:
            st.error(f"링크 수집 오류: {e}")

        # 2단계: 내용 크롤링
        st.info("2단계: 내용을 크롤링 중입니다.")
        progress_bar.progress(0)

        try:
            for batch in divide_batches(collected_links):
                with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
                    futures = {executor.submit(crawl_content, url): url for url in batch}
                    for future in as_completed(futures):
                        result = future.result()
                        if result and result["content"]:
                            all_data.append(result)
                progress = min(len(all_data) / len(collected_links), 1.0)
                progress_bar.progress(progress)
                status_text.text(f"진행 중: {len(all_data)}개의 내용 크롤링 완료")

            st.success(f"2단계 완료! 총 {len(all_data)}개의 내용 크롤링 완료!")

        except Exception as e:
            st.error(f"내용 크롤링 오류: {e}")

        # 3단계: 텍스트 정제 및 불필요한 문구 제거
        st.info("3단계: 텍스트를 정제 중입니다.")
        progress_bar.progress(0)

        try:
            for index, item in enumerate(all_data):
                if item["content"]:
                    cleaned_content = clean_text(item["content"])
                    refined_data.append({"url": item["url"], "content": cleaned_content})
                progress = (index + 1) / len(all_data)
                progress_bar.progress(progress)
                status_text.text(f"정제 중: {index + 1}/{len(all_data)} 완료")

            # 결과 저장
            timestamp = int(time.time())
            file_name = f"refined_data_{timestamp}.{file_type}"
            with open(file_name, "w", encoding="utf-8", newline="") as f:
                if file_type == "json":
                    json.dump(refined_data, f, ensure_ascii=False, indent=4)
                elif file_type == "csv":
                    import csv
                    writer = csv.writer(f)
                    writer.writerow(["URL", "Content"])
                    for item in refined_data:
                        writer.writerow([item["url"], item["content"]])

            st.success("3단계 완료! 텍스트 정제가 완료되었습니다.")
            with open(file_name, "rb") as f:
                st.download_button("결과 다운로드", data=f, file_name=file_name)

        except Exception as e:
            st.error(f"텍스트 정제 오류: {e}")
