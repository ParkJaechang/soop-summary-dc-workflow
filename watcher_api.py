import customtkinter as ctk
from tkinter import messagebox, filedialog
import os
import threading
import time
import json
import webbrowser
import pyperclip
import re
import subprocess
import sys # [추가] 파이썬 실행 경로 확인용
from PIL import Image, ImageTk
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# === 설정 ===
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# [핵심 수정] 현재 파일이 있는 폴더의 절대 경로를 구함
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 절대 경로를 사용해 파일 지정 (이제 못 찾을 수가 없음)
CONFIG_FILE = os.path.join(BASE_DIR, "watcher_list.json")
SUMMARIZER_APP = os.path.join(BASE_DIR, "soop_summery_pro.py") # 요약기 파일명

class StreamerCard(ctk.CTkFrame):
    def __init__(self, master, streamer_data, vod_callback, delete_callback, image_callback):
        super().__init__(master, fg_color="#2B2B2B", corner_radius=10, border_width=2, border_color="#333")
        
        self.streamer_id = streamer_data.get('id')
        self.image_path = streamer_data.get('img', '')
        self.vod_callback = vod_callback
        self.image_callback = image_callback
        
        self.grid_columnconfigure(2, weight=1)

        # 1. 프로필 이미지
        self.lbl_image = ctk.CTkLabel(self, text="No Img", width=60, height=60, fg_color="#111", corner_radius=5)
        self.lbl_image.grid(row=0, column=0, rowspan=2, padx=(15, 5), pady=10)
        
        self.btn_img = ctk.CTkButton(self, text="📷", width=30, height=60, fg_color="#333", hover_color="#555",
                                     command=lambda: self.select_image())
        self.btn_img.grid(row=0, column=1, rowspan=2, padx=(0, 15), pady=10)

        # 2. 닉네임
        self.lbl_nick = ctk.CTkLabel(self, text="Loading...", font=("AppleSDGothicNeo-Bold", 18, "bold"), anchor="w")
        self.lbl_nick.grid(row=0, column=2, sticky="ew", padx=5, pady=(8, 0))
        
        # 3. 아이디
        self.lbl_id = ctk.CTkLabel(self, text=f"ID: {self.streamer_id}", font=("Arial", 12), text_color="gray", anchor="w")
        self.lbl_id.grid(row=1, column=2, sticky="nw", padx=5, pady=(0, 8))
        
        # 4. 상태
        self.lbl_status = ctk.CTkLabel(self, text="Offline", font=("Arial", 12, "bold"), text_color="#888", width=80)
        self.lbl_status.grid(row=0, column=3, rowspan=2, padx=10)

        # 5. VOD 버튼
        self.btn_vod = ctk.CTkButton(self, text="⚡ VOD", width=90, height=32, 
                                     fg_color="#1F6AA5", hover_color="#144870", text_color="white",
                                     font=("Arial", 12, "bold"),
                                     command=lambda: self.vod_callback(self.streamer_id, self.btn_vod))
        self.btn_vod.grid(row=0, column=4, rowspan=2, padx=5, pady=10)

        # 6. 삭제 버튼
        self.btn_del = ctk.CTkButton(self, text="X", width=35, height=32, 
                                     fg_color="#880000", hover_color="#AA0000",
                                     command=lambda: delete_callback(self.streamer_id))
        self.btn_del.grid(row=0, column=5, rowspan=2, padx=(5, 15), pady=10)

        if self.image_path:
            self.load_image_from_file(self.image_path)

    def select_image(self):
        file_path = filedialog.askopenfilename(filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.gif")])
        if file_path:
            self.image_path = file_path
            self.load_image_from_file(file_path)
            self.image_callback(self.streamer_id, file_path)

    def load_image_from_file(self, path):
        try:
            img = Image.open(path)
            img = img.resize((60, 60), Image.Resampling.LANCZOS)
            photo = ctk.CTkImage(light_image=img, dark_image=img, size=(60, 60))
            self.lbl_image.configure(image=photo, text="")
        except: pass

    def set_analyzing(self, is_analyzing):
        if is_analyzing: self.configure(border_color="#00FF00", border_width=3)
        else: self.configure(border_width=2)

    def update_nick(self, nickname):
        if nickname: self.lbl_nick.configure(text=nickname)

    def set_status(self, is_live):
        if is_live:
            self.lbl_nick.configure(text_color="#FF3333")
            self.lbl_status.configure(text="LIVE (ON)", text_color="#FF3333")
            self.configure(border_color="#FF3333")
        else:
            self.lbl_nick.configure(text_color="white")
            self.lbl_status.configure(text="Offline", text_color="#888")
            self.configure(border_color="#333")

class SoopDashboard(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SOOP Watcher V43 (Path Fixed)")
        self.geometry("1050x750")
        
        self.streamers = [] 
        self.cards = {} 
        self.is_running = False
        self.driver = None 

        self.input_id = ctk.StringVar()
        self.monitor_interval = ctk.StringVar(value="30")
        self.cycle_status = ctk.StringVar(value="대기 중")
        self.auto_summarize = ctk.BooleanVar(value=False) 
        
        self.create_ui()
        self.load_streamers()

    def create_ui(self):
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)

        # Left
        frame_left = ctk.CTkFrame(self, fg_color="transparent")
        frame_left.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        ctk.CTkLabel(frame_left, text="📡 Monitoring Deck", font=("Arial", 22, "bold")).pack(anchor="w", pady=(0, 10))
        self.scroll_frame = ctk.CTkScrollableFrame(frame_left, height=400, fg_color="#1A1A1A")
        self.scroll_frame.pack(fill="both", expand=True)

        # Right
        frame_right = ctk.CTkFrame(self, fg_color="#222222")
        frame_right.grid(row=0, column=1, sticky="nsew", padx=(0, 20), pady=20)
        
        ctk.CTkLabel(frame_right, text="⚙️ Control Panel", font=("Arial", 18, "bold")).pack(pady=20)
        self.entry_id = ctk.CTkEntry(frame_right, textvariable=self.input_id, placeholder_text="Streamer ID", width=200)
        self.entry_id.pack(pady=5)
        ctk.CTkButton(frame_right, text="+ Add Card", command=self.add_streamer, width=200, fg_color="#1F6AA5").pack(pady=5)
        
        ctk.CTkLabel(frame_right, text="Interval (sec):").pack(pady=(20, 5))
        self.entry_interval = ctk.CTkEntry(frame_right, textvariable=self.monitor_interval, width=100)
        self.entry_interval.pack(pady=5)
        
        self.chk_auto = ctk.CTkCheckBox(frame_right, text="VOD 발견 시 요약 앱 자동실행", variable=self.auto_summarize, font=("Arial", 12))
        self.chk_auto.pack(pady=15)
        
        ctk.CTkLabel(frame_right, text="Cycle Status:", text_color="gray").pack(pady=(10, 0))
        self.lbl_cycle = ctk.CTkLabel(frame_right, textvariable=self.cycle_status, font=("Arial", 14, "bold"), text_color="#00FF00")
        self.lbl_cycle.pack(pady=(0, 10))

        self.btn_toggle = ctk.CTkButton(frame_right, text="▶ Start Monitoring", command=self.toggle_monitoring, 
                                        fg_color="#00AA00", height=50, font=("Arial", 16, "bold"))
        self.btn_toggle.pack(pady=10, fill="x", padx=20)

        ctk.CTkLabel(frame_right, text="[ System Log ]", font=("Arial", 12)).pack(pady=(20, 5), anchor="w", padx=20)
        self.log_box = ctk.CTkTextbox(frame_right, height=150, font=("Consolas", 11))
        self.log_box.pack(fill="both", expand=True, padx=20, pady=(0, 20))

    def log(self, msg):
        timestamp = time.strftime('%H:%M:%S')
        self.log_box.insert("end", f"[{timestamp}] {msg}\n")
        self.log_box.see("end")

    def get_driver(self):
        options = Options()
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-position=-10000,0") 
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument('--disable-blink-features=AutomationControlled')
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"})
        return driver

    def load_cookies(self, driver):
        try:
            import pickle
            if os.path.exists("cookies_soop.pkl"):
                driver.get("https://www.sooplive.co.kr")
                with open("cookies_soop.pkl", "rb") as f:
                    cookies = pickle.load(f)
                    for c in cookies:
                        if 'expiry' in c: del c['expiry']
                        try: driver.add_cookie(c)
                        except: pass
                driver.refresh()
                time.sleep(1)
        except: pass

    def add_streamer(self):
        sid = self.input_id.get().strip()
        for s in self.streamers:
            if s['id'] == sid: return
        data = {'id': sid, 'img': ''}
        self.streamers.append(data)
        self.create_card(data)
        self.input_id.set("")
        self.save_streamers()
        threading.Thread(target=self.fetch_nick_only, args=(sid,), daemon=True).start()

    def create_card(self, data):
        sid = data['id']
        card = StreamerCard(self.scroll_frame, data, self.manual_fetch_vod, self.delete_streamer, self.update_image_path)
        card.pack(fill="x", pady=5, padx=5)
        self.cards[sid] = card

    def update_image_path(self, sid, path):
        for s in self.streamers:
            if s['id'] == sid:
                s['img'] = path
                break
        self.save_streamers()

    def delete_streamer(self, sid):
        self.streamers = [s for s in self.streamers if s['id'] != sid]
        if sid in self.cards:
            self.cards[sid].destroy()
            del self.cards[sid]
        self.save_streamers()

    def save_streamers(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f: json.dump(self.streamers, f)

    def load_streamers(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    for item in loaded:
                        if isinstance(item, str): data = {'id': item, 'img': ''}
                        else: data = item
                        self.streamers.append(data)
                        self.create_card(data)
                        threading.Thread(target=self.fetch_nick_only, args=(data['id'],), daemon=True).start()
            except: pass

    def fetch_nick_only(self, sid):
        try:
            driver = self.get_driver()
            driver.get(f"https://www.sooplive.co.kr/station/{sid}")
            time.sleep(2)
            nickname = sid
            page_title = driver.title
            if "의 방송국" in page_title: nickname = page_title.split("의 방송국")[0]
            elif "방송국" in page_title: nickname = page_title.replace(" | SOOP", "").replace(" 방송국", "")
            driver.quit()
            if sid in self.cards: self.cards[sid].update_nick(nickname)
        except: pass

    # [핵심] 요약기 실행 - 절대 경로 사용
    def run_summarizer(self, vod_link):
        if not os.path.exists(SUMMARIZER_APP):
            self.log(f"⚠️ 오류: {SUMMARIZER_APP} 파일을 찾을 수 없습니다.")
            self.log(f"📂 현재 위치: {BASE_DIR}")
            return

        self.log(f"🚀 요약 앱 실행 중... ({vod_link})")
        try:
            # 절대 경로로 파일 실행
            subprocess.Popen(["python", SUMMARIZER_APP, vod_link], shell=True)
        except Exception as e:
            self.log(f"⚠️ 실행 실패: {e}")

    def manual_fetch_vod(self, sid, btn):
        def _run():
            btn.configure(state="disabled", text="Scan...", fg_color="#66EE66", text_color="white")
            self.log(f"🔎 [{sid}] VOD 검색 중...")
            
            driver = self.get_driver()
            self.load_cookies(driver)
            
            link = None
            try:
                driver.get(f"https://www.sooplive.co.kr/station/{sid}/vod")
                
                wait = WebDriverWait(driver, 20)
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/player/']")))
                links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/player/']")
                pattern = re.compile(r"/player/\d+")
                for l in links:
                    href = l.get_attribute("href")
                    if href and pattern.search(href):
                        link = href
                        break 
            except Exception as e: pass
            
            driver.quit()
            
            if link:
                pyperclip.copy(link)
                self.log(f"✅ [{sid}] 링크 확보!")
                btn.configure(text="Found!", fg_color="#2CC985")
                
                if self.auto_summarize.get():
                    self.run_summarizer(link)
            else:
                self.log(f"⚠️ [{sid}] VOD 없음")
                btn.configure(text="None", fg_color="#555555")
            
            time.sleep(2)
            btn.configure(state="normal", text="⚡ VOD", fg_color="#1F6AA5")

        threading.Thread(target=_run, daemon=True).start()

    def toggle_monitoring(self):
        if not self.is_running:
            if not self.streamers: return
            self.is_running = True
            self.btn_toggle.configure(text="■ Stop Monitoring", fg_color="#AA0000")
            self.log("Monitoring Started")
            threading.Thread(target=self.monitor_loop, daemon=True).start()
        else:
            self.is_running = False
            self.btn_toggle.configure(text="▶ Start Monitoring", fg_color="#00AA00")
            self.log("Monitoring Stopped")
            self.cycle_status.set("중지됨")
            if self.driver:
                try: self.driver.quit()
                except: pass
                self.driver = None

    def monitor_loop(self):
        try:
            self.driver = self.get_driver()
            self.load_cookies(self.driver)
            was_live = {s['id']: False for s in self.streamers}
            
            while self.is_running:
                self.cycle_status.set("⚡ 감시 사이클 가동 중")
                
                for s_data in self.streamers:
                    if not self.is_running: break
                    sid = s_data['id']
                    
                    if sid in self.cards: self.cards[sid].set_analyzing(True)
                    
                    is_live = False
                    try:
                        self.driver.get(f"https://www.sooplive.co.kr/station/{sid}")
                        try:
                            WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "[class*='Badge-module__live']")))
                            is_live = True
                        except: is_live = False
                    except: pass
                    
                    if sid in self.cards: 
                        self.cards[sid].set_analyzing(False) 
                        self.cards[sid].set_status(is_live)
                    
                    if is_live and not was_live.get(sid):
                        self.log(f"🔴 [{sid}] Live ON!")
                    elif not is_live and was_live.get(sid):
                        self.log(f"🚀 [{sid}] Live OFF! VOD Search...")
                        self.manual_fetch_vod(sid, self.cards[sid].btn_vod)
                        
                    was_live[sid] = is_live
                    time.sleep(1)
                
                try: wait = int(self.monitor_interval.get())
                except: wait = 30
                
                for i in range(wait, 0, -1):
                    if not self.is_running: break
                    self.cycle_status.set(f"💤 대기 중 ({i}초)")
                    time.sleep(1)

        except Exception as e:
            self.log(f"Loop Error: {e}")
            self.is_running = False
            self.btn_toggle.configure(text="▶ Start Monitoring", fg_color="#00AA00")

if __name__ == "__main__":
    app = SoopDashboard()
    app.mainloop()