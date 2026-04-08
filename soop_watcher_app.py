import customtkinter as ctk
from tkinter import messagebox
import os
import threading
import time
import json
import webbrowser
import pickle
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# === 디자인 테마 ===
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

CONFIG_FILE = "watcher_config.json"

class StreamerCard(ctk.CTkFrame):
    """스트리머 카드 UI"""
    def __init__(self, master, streamer_id, remove_callback):
        super().__init__(master, fg_color="#2B2B2B", corner_radius=10)
        self.streamer_id = streamer_id
        
        self.grid_columnconfigure(1, weight=1)

        self.status_indicator = ctk.CTkLabel(self, text="⚫", font=("Arial", 24))
        self.status_indicator.grid(row=0, column=0, rowspan=2, padx=(15, 5), pady=10)

        self.lbl_id = ctk.CTkLabel(self, text=streamer_id, font=("AppleSDGothicNeo-Bold", 16, "bold"))
        self.lbl_id.grid(row=0, column=1, sticky="w", padx=5, pady=(10, 0))
        
        self.lbl_status = ctk.CTkLabel(self, text="대기 중...", font=("Arial", 12), text_color="gray")
        self.lbl_status.grid(row=1, column=1, sticky="w", padx=5, pady=(0, 10))

        self.btn_go = ctk.CTkButton(self, text="방송국", width=60, height=24, fg_color="#444", 
                                    command=lambda: webbrowser.open(f"https://m.sooplive.co.kr/station/{streamer_id}"))
        self.btn_go.grid(row=0, column=2, padx=10, pady=(10, 0))

        self.btn_del = ctk.CTkButton(self, text="삭제", width=60, height=24, fg_color="#880000", hover_color="#AA0000",
                                     command=lambda: remove_callback(streamer_id))
        self.btn_del.grid(row=1, column=2, padx=10, pady=(5, 10))

    def update_status(self, status):
        if status == "ON":
            self.configure(border_width=2, border_color="#FF3333")
            self.status_indicator.configure(text="🔴", text_color="#FF3333")
            self.lbl_status.configure(text="방송 중 (LIVE)", text_color="#FF3333")
            self.lbl_id.configure(text_color="white")
        elif status == "OFF":
            self.configure(border_width=0)
            self.status_indicator.configure(text="⚫", text_color="gray")
            self.lbl_status.configure(text="방송 종료 (OFF)", text_color="gray")
            self.lbl_id.configure(text_color="gray")
        elif status == "CHECKING":
            self.status_indicator.configure(text="🟡", text_color="yellow")
            self.lbl_status.configure(text="확인 중...", text_color="yellow")

class SoopDashboard(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SOOP Watcher V11 (Mobile Mode)")
        self.geometry("900x650")
        
        self.streamers = [] 
        self.cards = {} 
        self.is_running = False
        self.driver = None

        self.input_id = ctk.StringVar()
        # [핵심 수정] 에러 방지를 위해 StringVar 사용
        self.monitor_interval = ctk.StringVar(value="60") 
        self.status_msg = ctk.StringVar(value="시스템 대기 중")

        self.create_ui()
        # 설정 파일 로드 시 에러나면 파일을 삭제하고 다시 시작
        try:
            self.load_config()
        except Exception as e:
            print(f"설정 파일 오류로 초기화합니다: {e}")
            if os.path.exists(CONFIG_FILE): os.remove(CONFIG_FILE)

    def create_ui(self):
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)

        frame_left = ctk.CTkFrame(self, fg_color="transparent")
        frame_left.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

        ctk.CTkLabel(frame_left, text="📡 모니터링 목록", font=("AppleSDGothicNeo-Bold", 20, "bold")).pack(anchor="w", pady=(0, 10))
        
        self.scroll_frame = ctk.CTkScrollableFrame(frame_left, height=400, fg_color="#1A1A1A")
        self.scroll_frame.pack(fill="both", expand=True)

        frame_right = ctk.CTkFrame(self, fg_color="#222222")
        frame_right.grid(row=0, column=1, sticky="nsew", padx=(0, 20), pady=20)

        ctk.CTkLabel(frame_right, text="⚙️ 제어판", font=("AppleSDGothicNeo-Bold", 18, "bold")).pack(pady=15)
        
        self.entry_id = ctk.CTkEntry(frame_right, textvariable=self.input_id, placeholder_text="스트리머 ID", width=200)
        self.entry_id.pack(pady=5)
        
        ctk.CTkButton(frame_right, text="+ 스트리머 추가", command=self.add_streamer, width=200).pack(pady=5)

        ctk.CTkLabel(frame_right, text="감시 주기 (초)").pack(pady=(15, 0))
        # [핵심 수정] 빈 값 에러 방지용 안전한 Entry
        self.entry_interval = ctk.CTkEntry(frame_right, textvariable=self.monitor_interval, width=100)
        self.entry_interval.pack(pady=5)

        self.btn_toggle = ctk.CTkButton(frame_right, text="▶ 감시 시작", command=self.toggle_monitoring, 
                                        fg_color="#00AA00", height=40, font=("Arial", 14, "bold"))
        self.btn_toggle.pack(pady=20, fill="x", padx=20)

        ctk.CTkLabel(frame_right, text="📝 VOD 알림 로그", font=("Arial", 14, "bold")).pack(anchor="w", padx=20, pady=(10, 5))
        self.log_area = ctk.CTkTextbox(frame_right, height=200, font=("Consolas", 11))
        self.log_area.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        ctk.CTkLabel(self, textvariable=self.status_msg, text_color="gray", height=30).grid(row=1, column=0, columnspan=2, sticky="ew")

    def log(self, message):
        timestamp = time.strftime('%H:%M:%S')
        self.log_area.configure(state="normal")
        self.log_area.insert("end", f"[{timestamp}] {message}\n")
        self.log_area.see("end")
        self.log_area.configure(state="disabled")

    def add_streamer(self):
        sid = self.input_id.get().strip()
        if not sid: return
        for s in self.streamers:
            if s['id'] == sid: return
        self.streamers.append({'id': sid, 'was_live': False})
        card = StreamerCard(self.scroll_frame, sid, self.remove_streamer)
        card.pack(fill="x", pady=5, padx=5)
        self.cards[sid] = card
        self.input_id.set("")
        self.save_config()

    def remove_streamer(self, sid):
        self.streamers = [s for s in self.streamers if s['id'] != sid]
        if sid in self.cards:
            self.cards[sid].destroy()
            del self.cards[sid]
        self.save_config()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                saved_list = data.get("streamers", [])
                for sid in saved_list:
                    self.input_id.set(sid)
                    self.add_streamer()
                # 문자열로 변환하여 로드 (에러 방지)
                self.monitor_interval.set(str(data.get("interval", 60)))

    def save_config(self):
        try:
            val = int(self.monitor_interval.get())
        except:
            val = 60 # 에러나면 기본값 저장
            
        data = { "streamers": [s['id'] for s in self.streamers], "interval": val }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f: json.dump(data, f)

    def get_safe_interval(self):
        try:
            val = int(self.monitor_interval.get())
            return max(5, val) # 최소 5초 보장
        except:
            return 60

    def toggle_monitoring(self):
        if not self.is_running:
            # 쿠키 파일 위치 찾기 (절대 경로)
            script_dir = os.path.dirname(os.path.abspath(__file__))
            cookie_path = os.path.join(script_dir, "cookies_soop.pkl")
            
            if not os.path.exists(cookie_path):
                messagebox.showerror("오류", f"쿠키 파일이 없습니다!\n위치: {cookie_path}\nlogin_saver.py를 먼저 실행하세요.")
                return

            if not self.streamers: messagebox.showwarning("알림", "스트리머를 추가해주세요."); return
            
            self.is_running = True
            self.btn_toggle.configure(text="■ 감시 중지", fg_color="#AA0000")
            self.status_msg.set("🔵 감시 가동 중 (모바일 우회 모드)")
            self.save_config()
            threading.Thread(target=self.run_loop, daemon=True).start()
        else:
            self.is_running = False
            self.btn_toggle.configure(text="▶ 감시 시작", fg_color="#00AA00")
            self.status_msg.set("⚫ 감시 중지됨")
            if self.driver: 
                try: self.driver.quit()
                except: pass
                self.driver = None

    def run_loop(self):
        try:
            options = Options()
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            # [핵심] 창 숨기기 + 모바일 위장
            options.add_argument("--window-position=-10000,0") 
            # 모바일 User-Agent 사용 (가장 중요)
            options.add_argument("user-agent=Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")
            
            self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
            
            # 쿠키 로드 (모바일 도메인으로)
            self.driver.get("https://m.sooplive.co.kr")
            script_dir = os.path.dirname(os.path.abspath(__file__))
            cookie_path = os.path.join(script_dir, "cookies_soop.pkl")
            
            with open(cookie_path, "rb") as f:
                cookies = pickle.load(f)
                for c in cookies:
                    if 'expiry' in c: del c['expiry']
                    self.driver.add_cookie(c)
            
            self.log("시스템 가동 (모바일 모드)")

            while self.is_running:
                for s in self.streamers:
                    if not self.is_running: break
                    sid = s['id']
                    if sid in self.cards: self.cards[sid].update_status("CHECKING")
                    
                    is_live = self.check_live_status(sid)
                    
                    if is_live:
                        if sid in self.cards: self.cards[sid].update_status("ON")
                        if not s['was_live']: self.log(f"🔴 [{sid}] 방송 시작!")
                        s['was_live'] = True
                    else:
                        if sid in self.cards: self.cards[sid].update_status("OFF")
                        if s['was_live']:
                            self.log(f"🚀 [{sid}] 방종! VOD 찾는 중...")
                            time.sleep(15)
                            link, title = self.get_vod_link(sid)
                            if link:
                                self.log(f"✅ VOD 발견: {title}")
                                self.log(f"🔗 {link}")
                            else:
                                self.log(f"⚠️ VOD 못 찾음 (비공개?)")
                        s['was_live'] = False
                    
                    time.sleep(1)

                wait_time = self.get_safe_interval()
                for i in range(wait_time):
                    if not self.is_running: break
                    time.sleep(1)

        except Exception as e:
            self.log(f"오류: {e}")
            self.is_running = False
            self.btn_toggle.configure(text="▶ 감시 재시작", fg_color="#00AA00")

    def check_live_status(self, sid):
        """모바일 페이지를 이용한 확실한 감지"""
        try:
            # 모바일 방송국 접속
            url = f"https://m.sooplive.co.kr/station/{sid}"
            self.driver.get(url)
            
            # 로딩 대기
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except: pass

            src = self.driver.page_source
            
            # [모바일 감지 포인트]
            # 1. 'on-air' 클래스나 텍스트 확인
            # 2. '생방송' 텍스트 확인
            if "on-air" in src or "생방송" in src or "status on" in src:
                return True
            
            return False
        except: return False

    def get_vod_link(self, sid):
        try:
            # VOD 목록은 PC 페이지가 파싱하기 편함 (또는 모바일 VOD 페이지)
            url = f"https://ch.sooplive.co.kr/{sid}/vods"
            self.driver.get(url)
            time.sleep(2)
            vods = self.driver.find_elements(By.CSS_SELECTOR, "a.thumb")
            if vods: return vods[0].get_attribute("href"), vods[0].get_attribute("title")
            return None, None
        except: return None, None

if __name__ == "__main__":
    app = SoopDashboard()
    app.mainloop()