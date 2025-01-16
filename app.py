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
]

# 제외할 도메인과 URL 키워드
EXCLUDE_DOMAINS = [
    "wordpress.com", "facebook.com", "instagram.com", "twitter.com", "linkedin.com", "youtube.com",
    "pinterest.com", "tumblr.com", "reddit.com", "tiktok.com"
]
EXCLUDE_KEYWORDS = [
    "ad", "ads", "login", "signup", "register", ".jpg", ".png", ".gif", ".mp4", ".mov", ".avi", ".webm"
]

# 고정된 설정
MAX_DEPTH = 5
BATCH_SIZE = 2000

# Streamlit 페이지 구성
st.set_page_config(page_title="HTTP 요청 지속 크롤러", layout="centered")
st.title("HTTP 요청 지속 크롤러")
st.markdown("**URL을 입력하고 크롤링을 시작하세요. WordPress 및 소셜 미디어 링크는 제외됩니다.**")

base_url = st.text_input("크롤링할 URL을 입력하세요 (HTTP/HTTPS 모두 지원):")
file_type = st.selectbox("저장 형식 선택", ["json", "csv"])
st.write("최대 성능으로 크롤링이 진행됩니다.")

if st.button("크롤링 시작"):
    if not base_url:
        st.error("URL을 입력하세요!")
    else:
        session = requests.Session()
        retries = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # 초기화
        bloom_filter = BloomFilter(max_elements=1000000, error_rate=0.01)
        all_data = []
        failed_links = []

        # 함수 정의
        def is_excluded_link(url):
            """도메인 및 URL 키워드 기반 제외 필터링"""
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.lower()

            # 도메인 필터링
            if any(excluded_domain in domain for excluded_domain in EXCLUDE_DOMAINS):
                return True

            # URL 키워드 필터링
            if any(keyword in url.lower() for keyword in EXCLUDE_KEYWORDS):
                return True

            return False

        def make_request(url):
            """HTTP 요청 함수"""
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            try:
                time.sleep(random.uniform(0.1, 0.5))  # 랜덤 지연
                response = session.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                return response
            except requests.exceptions.HTTPError as e:
                # 404 오류 처리
                if response.status_code == 404:
                    st.warning(f"404 오류 (URL: {url}): {e}")
                    failed_links.append(url)
                else:
                    st.warning(f"HTTP 오류 (URL: {url}): {e}")
                    failed_links.append(url)
            except requests.exceptions.RequestException as e:
                st.warning(f"요청 실패: {url} - {e}")
                failed_links.append(url)
            return None

        def clean_html(soup):
            """HTML에서 불필요한 요소 제거"""
            for tag in ["script", "style"]:
                for element in soup.find_all(tag):
                    element.decompose()
            return soup

        def crawl_link(url):
            if is_excluded_link(url):
                st.info(f"제외된 링크: {url}")
                return {"url": url, "content": None}

            response = make_request(url)
            if not response:
                return {"url": url, "content": None}

            try:
                soup = BeautifulSoup(response.text, "html.parser")
                soup = clean_html(soup)
                content = soup.get_text(strip=True)
                return {"url": url, "content": content}
            except Exception as e:
                st.warning(f"파싱 실패: {url} - {e}")
                failed_links.append(url)
                return {"url": url, "content": None}

        def extract_links(url):
            response = make_request(url)
            if not response:
                return []

            try:
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

        def divide_batches(data):
            for i in range(0, len(data), BATCH_SIZE):
                yield data[i:i + BATCH_SIZE]

        # 크롤링 시작
        progress_bar = st.progress(0)
        status_text = st.empty()

        try:
            queue = [base_url]
            for depth in range(MAX_DEPTH):
                next_queue = []
                batch_count = 0
                for batch in divide_batches(queue):
                    with ThreadPoolExecutor(max_workers=10) as executor:
                        futures = {executor.submit(crawl_link, url): url for url in batch}
                        for future in as_completed(futures):
                            result = future.result()
                            if result and result["content"]:
                                all_data.append(result)
                    # 다음 단계 링크 추출
                    for url in batch:
                        next_queue.extend(extract_links(url))
                    batch_count += 1
                    progress_bar.progress(min(batch_count / len(queue), 1.0))

                queue = next_queue

            # 결과 저장
            timestamp = int(time.time())
            if file_type == "json":
                file_name = f"crawled_data_{timestamp}.json"
                with open(file_name, "w", encoding="utf-8") as f:
                    json.dump(all_data, f, ensure_ascii=False, indent=4)
                st.success("크롤링 완료!")
                st.download_button("결과 다운로드 (JSON)", data=open(file_name, "rb").read(), file_name=file_name)

            elif file_type == "csv":
                file_name = f"crawled_data_{timestamp}.csv"
                with open(file_name, "w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["URL", "Content"])
                    for item in all_data:
                        writer.writerow([item["url"], item["content"]])
                st.success("크롤링 완료!")
                st.download_button("결과 다운로드 (CSV)", data=open(file_name, "rb").read(), file_name=file_name)

            # 실패한 링크 출력
            if failed_links:
                st.warning(f"실패한 링크 {len(failed_links)}개가 있습니다.")
                st.write(failed_links)

        except Exception as e:
            st.error(f"크롤링 오류: {e}")