import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import math
import json
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import time
import re

# SNS 도메인 목록 (제외할 도메인)
SNS_DOMAINS = ["facebook.com", "instagram.com", "twitter.com", "linkedin.com", "tiktok.com"]

# 제외할 링크 키워드
EXCLUDED_KEYWORDS = ["login", "signin", "signup", "auth", "oauth", "account", "register"]

# 사용자 에이전트 설정
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
}

# 링크를 수집하는 함수
def collect_links(base_url):
    visited = set()
    links_to_visit = [base_url]
    collected_links = []

    while links_to_visit:
        url = links_to_visit.pop()
        if url in visited:
            continue
        visited.add(url)

        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            st.warning(f"HTTP 오류: {e} ({url})")
            continue
        except requests.RequestException as e:
            st.warning(f"요청 실패: {e} ({url})")
            continue

        try:
            soup = BeautifulSoup(response.text, 'html.parser')
            collected_links.append(url)

            # 모든 링크를 수집
            for tag in soup.find_all('a', href=True):
                href = urljoin(url, tag['href'])  # 절대 경로로 변환
                parsed_href = urlparse(href)

                # SNS 링크 및 제외할 키워드 필터링
                if any(domain in parsed_href.netloc for domain in SNS_DOMAINS):
                    continue
                if any(keyword in parsed_href.path.lower() for keyword in EXCLUDED_KEYWORDS):
                    continue

                # 중복 제거 후 링크 추가
                if href not in visited and href not in links_to_visit:
                    links_to_visit.append(href)
        except Exception as e:
            st.warning(f"HTML 파싱 중 오류 발생: {url} ({e})")

    return collected_links

# 요청 및 컨텐츠 가져오기 함수
def fetch_content(url, retries=3, delay=5, use_proxy=False):
    proxies = {
        "http": "http://your_proxy:port",
        "https": "https://your_proxy:port"
    } if use_proxy else None

    for i in range(retries):
        try:
            response = requests.get(url, headers=HEADERS, proxies=proxies, timeout=10)
            response.raise_for_status()
            time.sleep(1)  # 요청 간 지연
            return response.text
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                st.warning(f"404 오류: URL을 찾을 수 없습니다. ({url})")
                return f"Error: 404 Not Found ({url})"
            elif e.response.status_code in [429, 503]:  # Too Many Requests 또는 Service Unavailable
                if i < retries - 1:
                    time.sleep(delay)  # 딜레이 후 재시도
                else:
                    return f"Error: HTTP {e.response.status_code} ({e})"
            else:
                return f"Error: HTTP {e.response.status_code} ({e})"
        except requests.RequestException as e:
            if i < retries - 1:
                time.sleep(delay)
            else:
                return f"Error: Unable to fetch content ({e})"

# 멀티스레딩을 이용한 내용 크롤링 함수
def crawl_content_multithread(links):
    content_data = []

    def fetch_and_parse_content(link):
        html = fetch_content(link, retries=3, delay=5, use_proxy=False)
        try:
            soup = BeautifulSoup(html, 'html.parser')
            text = soup.get_text(separator="\n")
            text = clean_text(text)
            return {"url": link, "content": text}
        except Exception as e:
            return {"url": link, "content": f"Error parsing content: {e}"}

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(fetch_and_parse_content, links))
        content_data.extend(results)

    return content_data

# 텍스트 정리 함수 (가이드라인 제거)
def clean_text(text):
    try:
        text = text.strip()
        text_lines = text.splitlines()

        # 제거할 키워드가 포함된 줄 제거
        keywords_to_remove = ["cookie", "Cookie", "privacy", "Privacy", "terms", "Terms"]
        cleaned_lines = [
            line for line in text_lines
            if not any(keyword.lower() in line.lower() for keyword in keywords_to_remove)
        ]

        # 남은 줄을 합치고 연속된 줄바꿈을 하나로 치환
        cleaned_text = "\n".join(cleaned_lines)
        cleaned_text = re.sub(r'\n+', '\n', cleaned_text)  # 연속된 줄바꿈 제거
        return cleaned_text
    except Exception as e:
        st.warning(f"텍스트 정리 중 오류 발생: {e}")
        return ""

# 데이터 저장 함수 (JSON 및 CSV)
def save_data(data, file_format):
    try:
        if file_format == "json":
            file_path = "crawled_content.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return file_path
        elif file_format == "csv":
            file_path = "crawled_content.csv"
            df = pd.DataFrame(data)
            df.to_csv(file_path, index=False, encoding="utf-8")
            return file_path
    except Exception as e:
        st.error(f"데이터 저장 중 오류 발생: {e}")
    return None

# URL 유효성 검사 함수
def is_valid_url(url):
    try:
        parsed = urlparse(url)
        return bool(parsed.netloc) and bool(parsed.scheme)
    except Exception as e:
        st.error(f"URL 유효성 검사 중 오류 발생: {e}")
        return False

# Streamlit 앱
st.title("모든 링크 크롤러 및 학습 데이터 생성기")
url_input = st.text_input("사이트 URL을 입력하세요", placeholder="https://example.com")
RESULTS_PER_PAGE = 5
file_format = st.selectbox("저장할 파일 형식을 선택하세요", ["json", "csv"])
start_crawl = st.button("크롤링 시작")

if start_crawl and url_input:
    if not is_valid_url(url_input):
        st.error("유효한 URL을 입력하세요.")
        st.stop()

    with st.spinner("링크를 수집 중입니다..."):
        try:
            links = collect_links(url_input)
        except Exception as e:
            st.error(f"링크 수집 중 치명적인 오류 발생: {e}")
            links = []

    if links:
        st.success(f"수집된 링크 수: {len(links)}")
        st.write(links)

        with st.spinner("내용을 크롤링 중입니다..."):
            try:
                content = crawl_content_multithread(links)
            except Exception as e:
                st.error(f"크롤링 중 치명적인 오류 발생: {e}")
                content = []

        if content:
            st.success("크롤링 완료! 학습용 데이터를 저장합니다.")
            file_path = save_data(content, file_format)

            if file_path:
                try:
                    with open(file_path, "rb") as f:
                        st.download_button(
                            label=f"크롤링 결과 다운로드 ({file_format.upper()})",
                            data=f,
                            file_name=file_path,
                            mime="application/json" if file_format == "json" else "text/csv"
                        )
                    time.sleep(3600)  # 다운로드 버튼 유지 시간: 1시간
                except Exception as e:
                    st.error(f"파일 다운로드 중 오류 발생: {e}")
    else:
        st.error("링크를 수집할 수 없습니다. URL을 확인하세요.")