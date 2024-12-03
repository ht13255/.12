import streamlit as st
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import os


def is_social_media_link(link):
    social_keywords = ["facebook", "twitter", "instagram", "linkedin", "youtube", "tiktok"]
    return any(keyword in link for keyword in social_keywords)


def get_links_from_website(url):
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.content, "html.parser")
        links = [a['href'] for a in soup.find_all('a', href=True) if not is_social_media_link(a['href'])]
        return links
    except Exception as e:
        st.error(f"Error fetching links: {e}")
        return []


def save_page_as_pdf(url, output_path, driver):
    try:
        driver.get(url)
        time.sleep(2)  # Wait for the page to load
        pdf_path = os.path.join(output_path, f"{url.replace('https://', '').replace('/', '_')}.pdf")
        driver.execute_script('window.print();')
        return True
    except Exception as e:
        st.error(f"Error saving {url} as PDF: {e}")
        return False


def main():
    st.title("웹사이트 링크를 PDF로 저장")
    
    url = st.text_input("웹사이트 URL을 입력하세요", "https://example.com")
    output_folder = "saved_pdfs"
    os.makedirs(output_folder, exist_ok=True)

    if st.button("PDF 저장 시작"):
        st.info("링크를 수집 중입니다...")
        links = get_links_from_website(url)

        if links:
            st.success(f"{len(links)}개의 링크를 발견했습니다!")
            st.info("PDF로 저장 중...")
            
            # Selenium 설정
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

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