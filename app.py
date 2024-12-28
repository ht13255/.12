import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import random
import torch  # PyTorch for GPU processing

# GPU 활성화 여부 확인
use_gpu = torch.cuda.is_available()
device = torch.device("cuda" if use_gpu else "cpu")

# 필터링 대상
EXCLUDED_DOMAINS = [
    "facebook.com", "instagram.com", "twitter.com", "linkedin.com", "tiktok.com",
    "google.com", "whatsapp.com", "telegram.org", "pinterest.com", "snapchat.com", "reddit.com",
    "bet", "casino", "gamble", "lotto"
]
EXCLUDED_EXTENSIONS = [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".exe", ".png", ".jpg", ".jpeg", ".gif", ".mp4", ".txt"]
EXCLUDED_SCHEMES = ["mailto:"]  # 메일 링크 제외
EXCLUDED_KEYWORDS = ["guideline", "terms", "policy", "privacy", "cookies"]

# User-Agent 리스트
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1",
]

# HTTP 헤더 다양화
def random_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

# URL 유효성 검사 함수
def is_valid_url(url):
    try:
        parsed = urlparse(url)
        return bool(parsed.netloc) and bool(parsed.scheme)
    except Exception:
        return False

# 링크를 수집하는 함수
def collect_links(base_url):
    visited = set()
    links_to_visit = [base_url]
    collected_links = []
    failed_links = []

    while links_to_visit:
        url = links_to_visit.pop()
        if url in visited:
            continue
        visited.add(url)

        try:
            headers = random_headers()
            response = requests.get(url, headers=headers, timeout=2)
            response.raise_for_status()
        except requests.RequestException as e:
            failed_links.append({"url": url, "error": str(e)})
            continue

        try:
            soup = BeautifulSoup(response.text, "html.parser")
            collected_links.append(url)

            for tag in soup.find_all("a", href=True):
                href = urljoin(url, tag["href"])
                parsed_href = urlparse(href)

                if any(domain in parsed_href.netloc for domain in EXCLUDED_DOMAINS):
                    continue
                if any(href.endswith(ext) for ext in EXCLUDED_EXTENSIONS):
                    continue
                if any(keyword in href.lower() for keyword in EXCLUDED_KEYWORDS):
                    continue
                if parsed_href.scheme in EXCLUDED_SCHEMES:
                    continue
                if href not in visited and href not in links_to_visit:
                    links_to_visit.append(href)

        except Exception as e:
            failed_links.append({"url": url, "error": f"HTML 파싱 오류: {e}"})

    return collected_links, failed_links

# 멀티스레딩을 이용한 내용 크롤링 함수
def crawl_content_multithread(links):
    content_data = []
    total_links = len(links)
    completed = 0

    def fetch_and_parse(link):
        nonlocal completed
        try:
            headers = random_headers()
            response = requests.get(link, headers=headers, timeout=2)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            text = soup.get_text(separator="\n").strip()
            result = {"url": link, "content": text}
        except Exception as e:
            result = {"url": link, "content": f"HTML 가져오기 실패: {e}"}
        finally:
            completed += 1
        return result

    max_threads = os.cpu_count()  # 항상 최대 스레드 유지
    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        future_to_url = {executor.submit(fetch_and_parse, link): link for link in links}
        for future in as_completed(future_to_url):
            try:
                content_data.append(future.result())
            except Exception as e:
                content_data.append({"url": future_to_url[future], "content": f"크롤링 실패: {e}"})

    return content_data

# GPU에서 텍스트 분석 처리 (예시)
def analyze_with_gpu(data):
    # GPU 텐서 생성
    tensor_data = torch.tensor([len(item["content"]) for item in data], device=device)
    return tensor_data.sum().item()

# 데이터 저장 함수
def save_data(data, file_format):
    try:
        file_path = f"crawled_content.{file_format}"
        if file_format == "json":
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        elif file_format == "csv":
            pd.DataFrame(data).to_csv(file_path, index=False, encoding="utf-8")
        return file_path
    except Exception as e:
        st.error(f"파일 저장 중 오류 발생: {e}")
        return None

# Streamlit 앱
st.title("고속 크롤링 및 GPU 확장 크롤러")
st.write("멀티스레드와 GPU를 최대한 활용하는 크롤러입니다.")

if use_gpu:
    st.success("GPU가 활성화되었습니다!")
else:
    st.warning("GPU를 사용할 수 없습니다. CPU 모드로 실행합니다.")

# 입력 필드
url_input = st.text_input("크롤링할 사이트 URL을 입력하세요:", placeholder="https://example.com")
file_format = st.radio("저장할 파일 형식 선택:", ["json", "csv"])
start_button = st.button("크롤링 시작")

if start_button and url_input:
    if not is_valid_url(url_input):
        st.error("유효한 URL을 입력하세요.")
    else:
        with st.spinner("링크를 수집 중입니다..."):
            try:
                links, failed_links = collect_links(url_input)
                st.success(f"수집된 링크 수: {len(links)}")
            except Exception as e:
                st.error(f"링크 수집 중 오류 발생: {e}")
                links, failed_links = [], []

        if links:
            with st.spinner("내용을 크롤링 중입니다..."):
                try:
                    content = crawl_content_multithread(links)
                    st.success(f"크롤링된 데이터 수: {len(content)}")
                except Exception as e:
                    st.error(f"크롤링 중 오류 발생: {e}")
                    content = []

            if content:
                # GPU 텍스트 분석 (옵션)
                if use_gpu:
                    total_length = analyze_with_gpu(content)
                    st.info(f"GPU를 사용하여 분석된 총 텍스트 길이: {total_length}")

                # 데이터 저장 및 다운로드
                file_path = save_data(content, file_format)
                if file_path:
                    with open(file_path, "rb") as f:
                        st.download_button(
                            label=f"크롤링 결과 다운로드 ({file_format.upper()})",
                            data=f,
                            file_name=file_path,
                            mime="application/json" if file_format == "json" else "text/csv"
                        )