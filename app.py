import streamlit as st
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
import os

def is_social_media_link(link):
    """SNS 링크인지 확인하는 함수"""
    social_keywords = ["facebook", "twitter", "instagram", "linkedin", "youtube", "tiktok"]
    return any(keyword in link for keyword in social_keywords)

def get_links_from_website(url):
    """웹사이트에서 링크를 수집"""
    try:
        response = requests.get(url)
        response.raise_for_status()  # HTTP 오류 확인
        soup = BeautifulSoup(response.content, "html.parser")
        links = [
            a['href'] for a in soup.find_all('a', href=True)
            if not is_social_media_link(a['href'])  # SNS 링크 제외
        ]
        # 상대 경로를 절대 경로로 변환
        links = [link if link.startswith("http") else requests.compat.urljoin(url, link) for link in links]
        return links
    except Exception as e:
        st.error(f"Error fetching links: {e}")
        return []

def save_page_as_pdf(url, output_path, driver):
    """페이지를 PDF로 저장"""
    try:
        driver.get(url)
        time.sleep(2)  # 페이지 로드 대기
        pdf_path = os.path.join(output_path, f"{url.replace('https://', '').replace('/', '_')}.pdf")
        with open(pdf_path, "wb") as f:
            f.write(driver.execute_cdp_cmd("Page.printToPDF", {"printBackground": True})["data"].encode("utf-8"))
        return True
    except Exception as e:
        st.error(f"Error saving {url} as PDF: {e}")
        return False

def setup_driver():
    """ChromeDriver 설정"""
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.binary_location = "/usr/bin/google-chrome"  # Streamlit Cloud에 설치된 Chrome 위치
        return webdriver.Chrome(
            service=Service("/usr/bin/chromedriver"),  # Streamlit Cloud에 설치된 ChromeDriver 위치
            options=chrome_options
        )
    except Exception as e:
        st.error(f"Error setting up ChromeDriver: {e}")
        return None

def main():
    st.title("웹사이트 링크를 PDF로 저장")

    # 사용자 입력 URL
    url = st.text_input("웹사이트 URL을 입력하세요", "https://example.com")
    output_folder = "saved_pdfs"
    os.makedirs(output_folder, exist_ok=True)  # 출력 폴더 생성

    if st.button("PDF 저장 시작"):
        st.info("링크를 수집 중입니다...")
        links = get_links_from_website(url)

        if links:
            st.success(f"{len(links)}개의 링크를 발견했습니다!")
            st.info("PDF로 저장 중...")

            driver = setup_driver()
            if not driver:
                st.error("ChromeDriver 설정에 실패했습니다.")
                return

            saved_count = 0
            for link in links:
                if save_page_as_pdf(link, output_folder, driver):
                    saved_count += 1

            driver.quit()
            st.success(f"{saved_count}/{len(links)} 페이지를 PDF로 저장했습니다.")
        else:
            st.warning("링크를 찾을 수 없습니다.")

    st.info(f"PDF는 '{output_folder}' 폴더에 저장됩니다.")

if __name__ == "__main__":
    main()