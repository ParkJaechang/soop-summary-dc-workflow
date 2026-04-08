from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import pickle
import time
import os

def save_cookies(site_name, url, filename):
    print(f"\n🔵 [{site_name}] 로그인 쿠키를 저장합니다.")
    print(f"1. 브라우저가 열리면 {site_name}에 직접 로그인하세요.")
    print("2. 로그인이 완료되면, 이 검은 창(터미널)에 와서 엔터키를 누르세요.")
    
    # 크롬 브라우저 열기
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
    driver.get(url)
    
    # 사용자가 로그인할 때까지 대기
    input("⌨️ 로그인을 완료하셨나요? 그렇다면 여기서 엔터를 누르세요...")
    
    # 쿠키(로그인 정보) 파일로 저장
    cookies = driver.get_cookies()
    with open(filename, "wb") as f:
        pickle.dump(cookies, f)
        
    print(f"✅ {site_name} 로그인 정보 저장 완료! ({filename})")
    driver.quit()

if __name__ == "__main__":
    # 1. SOOP 로그인 저장 (즐겨찾기 확인용)
    save_cookies("SOOP(아프리카TV)", "https://login.sooplive.co.kr/afreeca/login.php?szFrom=full&request_uri=https%3A%2F%2Fwww.sooplive.co.kr%2F", "cookies_soop.pkl")
    
    # 2. 디시인사이드 로그인 저장 (글쓰기용)
    save_cookies("디시인사이드", "https://sign.dcinside.com/login?s_url=https%3A%2F%2Fgall.dcinside.com%2F&s_key=513", "cookies_dc.pkl")
    
    print("\n🎉 모든 준비가 끝났습니다! 이제 자동화 봇을 만들 수 있습니다.")