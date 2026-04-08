import customtkinter as ctk
from tkinter import filedialog, messagebox
import yt_dlp
import os
import sys
import threading
import json
import time
import re
import google.generativeai as genai
from datetime import timedelta

# === 디자인 설정 ===
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

CONFIG_FILE = "config.json"

class SoopModernApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SOOP Smart Summarizer (Interactive V5)")
        self.geometry("700x900") # 채팅창 공간 확보를 위해 길이 늘림
        self.resizable(False, False)

        # 변수
        self.api_key = ctk.StringVar()
        self.save_dir = ctk.StringVar()
        self.url_var = ctk.StringVar()
        self.status_var = ctk.StringVar(value="대기 중...")
        
        self.current_audio_file = None # 현재 업로드된 파일 객체 저장용
        self.current_mp3_path = None
        self.video_duration_sec = 0
        
        self.create_ui()
        self.load_config()

    def create_ui(self):
        # 1. 헤더
        self.header = ctk.CTkLabel(self, text="SOOP 방송 요약 & 대화하기", font=("AppleSDGothicNeo-Bold", 24, "bold"))
        self.header.pack(pady=(20, 10))

        # 2. 설정 프레임
        self.frame_settings = ctk.CTkFrame(self)
        self.frame_settings.pack(pady=5, padx=20, fill="x")

        ctk.CTkLabel(self.frame_settings, text="API Key").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.entry_api = ctk.CTkEntry(self.frame_settings, textvariable=self.api_key, show="*", width=300)
        self.entry_api.grid(row=0, column=1, padx=5, pady=5)

        ctk.CTkLabel(self.frame_settings, text="저장 폴더").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.entry_dir = ctk.CTkEntry(self.frame_settings, textvariable=self.save_dir, width=300, state="readonly")
        self.entry_dir.grid(row=1, column=1, padx=5, pady=5)
        self.btn_dir = ctk.CTkButton(self.frame_settings, text="선택", command=self.choose_directory, width=60)
        self.btn_dir.grid(row=1, column=2, padx=5, pady=5)

        # 3. 입력 프레임
        self.frame_input = ctk.CTkFrame(self)
        self.frame_input.pack(pady=5, padx=20, fill="x")
        
        self.entry_url = ctk.CTkEntry(self.frame_input, textvariable=self.url_var, width=580, height=35, placeholder_text="방송 URL 입력")
        self.entry_url.pack(padx=10, pady=10)

        # 4. 메인 버튼 (시작 / 초기화)
        self.btn_start = ctk.CTkButton(self, text="분석 시작 (Start)", command=self.start_thread, width=200, height=40, font=("Arial", 14, "bold"), fg_color="#0066cc")
        self.btn_start.pack(pady=10)
        
        self.btn_reset = ctk.CTkButton(self, text="종료 및 파일 삭제 (Reset)", command=self.reset_all, width=200, height=30, fg_color="#cc0000", state="disabled")
        self.btn_reset.pack(pady=0)

        self.lbl_status = ctk.CTkLabel(self, textvariable=self.status_var, font=("Arial", 12), text_color="#FFcc00")
        self.lbl_status.pack(pady=5)

        # 5. 로그/결과 창
        self.log_area = ctk.CTkTextbox(self, width=660, height=250, font=("Consolas", 12))
        self.log_area.pack(pady=5)
        self.log_area.configure(state="disabled")

        # 6. [NEW] 추가 질문(채팅) 프레임
        self.frame_chat = ctk.CTkFrame(self)
        self.frame_chat.pack(pady=10, padx=20, fill="x")
        
        ctk.CTkLabel(self.frame_chat, text="[추가 질문] 이미 분석된 파일에 대해 더 물어보세요").pack(anchor="w", padx=10, pady=5)
        
        self.entry_prompt = ctk.CTkEntry(self.frame_chat, width=540, height=35, placeholder_text="예: 방금 그 게임 이름이 뭐야? / 노래 제목 알려줘")
        self.entry_prompt.pack(side="left", padx=(10, 5), pady=10)
        
        self.btn_chat = ctk.CTkButton(self.frame_chat, text="전송", command=self.send_custom_prompt, width=80, height=35, state="disabled")
        self.btn_chat.pack(side="right", padx=(0, 10), pady=10)

    def log(self, message):
        self.log_area.configure(state="normal")
        self.log_area.insert("end", message + "\n")
        self.log_area.see("end")
        self.log_area.configure(state="disabled")
        self.status_var.set(message)

    # ... (기존 설정 로드/저장/모델 선택 함수는 동일하므로 생략하지 않고 그대로 사용) ...
    def choose_directory(self):
        path = filedialog.askdirectory()
        if path: self.save_dir.set(path); self.save_config()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.api_key.set(data.get("api_key", ""))
                    self.save_dir.set(data.get("save_dir", ""))
            except: pass

    def save_config(self):
        data = { "api_key": self.api_key.get(), "save_dir": self.save_dir.get() }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f: json.dump(data, f)

    def get_best_model(self, api_key):
        try:
            genai.configure(api_key=api_key, transport='rest')
            models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            for m in models: 
                if 'flash' in m: return m
            return models[0] if models else None
        except Exception as e: return None

    # ... (타임라인 보정 함수들 동일) ...
    def seconds_to_time(self, seconds):
        return f"[{str(timedelta(seconds=int(seconds))).zfill(8)}]"

    def enforce_linearity(self, text, video_duration_sec):
        # (V4의 시간 경찰 코드 그대로 사용)
        lines = text.split('\n'); corrected_lines = []; last_valid_seconds = 0
        timestamp_pattern = re.compile(r'\[(\d{1,2}):(\d{2}):(\d{2})\]')
        for line in lines:
            match = timestamp_pattern.search(line)
            if match:
                h, m, s = map(int, match.groups())
                if s >= 60: m += s // 60; s %= 60
                if m >= 60: h += m // 60; m %= 60
                curr_sec = h * 3600 + m * 60 + s
                if curr_sec > video_duration_sec:
                    shift_sec = h * 60 + m
                    if shift_sec <= video_duration_sec: curr_sec = shift_sec
                    else: curr_sec = last_valid_seconds + 60
                if last_valid_seconds > 0 and (curr_sec - last_valid_seconds > 600): curr_sec = last_valid_seconds + 120
                if curr_sec < last_valid_seconds: curr_sec = last_valid_seconds + 10
                line = timestamp_pattern.sub(self.seconds_to_time(curr_sec), line)
                last_valid_seconds = curr_sec
            corrected_lines.append(line)
        return '\n'.join(corrected_lines).replace("**", "").replace("##", "")

    # === [핵심 로직 변경] ===
    def start_thread(self):
        if not self.api_key.get() or not self.save_dir.get() or not self.url_var.get():
            messagebox.showwarning("입력 확인", "정보를 모두 입력해주세요.")
            return
        self.save_config()
        self.btn_start.configure(state="disabled")
        self.btn_reset.configure(state="disabled") # 작업 중엔 리셋 불가
        threading.Thread(target=self.run_process, daemon=True).start()

    def run_process(self):
        try:
            url = self.url_var.get().strip(); save_path = self.save_dir.get(); safe_key = self.api_key.get().strip()
            
            # 1. FFmpeg & Model 체크
            if getattr(sys, 'frozen', False): script_dir = os.path.dirname(sys.executable)
            else: script_dir = os.path.dirname(os.path.abspath(__file__))
            ffmpeg_path = os.path.join(script_dir, "ffmpeg.exe")
            if not os.path.exists(ffmpeg_path):
                self.log("🚨 ffmpeg.exe 없음"); self.reset_ui_state(); return

            self.log("📡 모델 연결 중...")
            self.model_name = self.get_best_model(safe_key) # self에 저장
            if not self.model_name:
                self.log("❌ AI 연결 실패"); self.reset_ui_state(); return

            # 2. 다운로드
            self.log("🚀 오디오 추출 중...")
            output_template = os.path.join(save_path, "%(uploader)s_%(title)s_%(upload_date)s.%(ext)s")
            ydl_opts = {
                'format': 'bestaudio/best', 'outtmpl': output_template,
                'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '64'}],
                'postprocessor_args': ['-ac', '1', '-map_metadata', '-1'],
                'ffmpeg_location': script_dir, 'quiet': True, 'no_warnings': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                self.current_mp3_path = os.path.splitext(ydl.prepare_filename(info))[0] + ".mp3"
                self.video_duration_sec = info.get('duration', 0)
                video_duration_str = time.strftime('%H:%M:%S', time.gmtime(self.video_duration_sec))

            self.log(f"✅ 추출 완료 ({video_duration_str})")
            
            # 3. 업로드 (파일 객체 보존)
            self.log("⚡ AI 서버로 업로드 중...")
            genai.configure(api_key=safe_key, transport='rest')
            
            # 여기서 self.current_audio_file에 저장해둠 (중요!)
            self.current_audio_file = genai.upload_file(path=self.current_mp3_path)
            
            while self.current_audio_file.state.name == "PROCESSING":
                time.sleep(1)
                self.current_audio_file = genai.get_file(self.current_audio_file.name)
            
            if self.current_audio_file.state.name == "FAILED":
                self.log("❌ 업로드 실패"); self.reset_all(); return

            # 4. 초기 요약 요청
            self.log("📝 전체 요약 및 타임라인 생성 중...")
            prompt = f"""
            너는 SOOP 방송 편집자야. 영상 길이: {video_duration_str}.
            [절대 규칙] 타임라인은 `[HH:MM:SS]` 형식 유지. 시간 순서 준수.
            [출력 양식] 3줄 요약, 상세 타임라인, 하이라이트, 주요 멘트.
            """
            model = genai.GenerativeModel(self.model_name)
            response = model.generate_content([prompt, self.current_audio_file])
            
            final_text = self.enforce_linearity(response.text, self.video_duration_sec)
            
            txt_filename = self.current_mp3_path.replace(".mp3", "_요약.txt")
            with open(txt_filename, "w", encoding="utf-8") as f: f.write(final_text)
            
            self.log(f"🎉 요약 완료! (파일 열림: {os.path.basename(txt_filename)})")
            os.startfile(txt_filename)
            
            # 5. 상태 전환: 대기 모드 (삭제 안 함!)
            self.log("💡 [대기] 추가 질문이 있다면 아래에 입력하세요. (파일 유지 중)")
            self.btn_chat.configure(state="normal")
            self.btn_reset.configure(state="normal", fg_color="#cc0000") # 리셋 버튼 활성화
            self.status_var.set("추가 질문 대기 중... (끝내려면 초기화 버튼 클릭)")

        except Exception as e:
            self.log(f"❌ 오류: {e}"); self.reset_all()

    # === [NEW] 추가 질문 기능 ===
    def send_custom_prompt(self):
        user_prompt = self.entry_prompt.get().strip()
        if not user_prompt: return
        
        if not self.current_audio_file:
            messagebox.showerror("오류", "분석된 파일이 없습니다.")
            return

        self.log(f"💬 질문 분석 중: {user_prompt}")
        self.btn_chat.configure(state="disabled")
        
        threading.Thread(target=self.process_custom_prompt, args=(user_prompt,), daemon=True).start()

    def process_custom_prompt(self, user_prompt):
        try:
            model = genai.GenerativeModel(self.model_name)
            # 기존 파일 객체를 재사용 (업로드 시간 0초)
            response = model.generate_content([user_prompt, self.current_audio_file])
            
            self.log(f"\n[Q] {user_prompt}\n[A] {response.text}\n" + "-"*30)
            self.entry_prompt.delete(0, 'end')
        except Exception as e:
            self.log(f"❌ 답변 실패: {e}")
        finally:
            self.btn_chat.configure(state="normal")

    # === 초기화 및 삭제 ===
    def reset_all(self):
        """파일 삭제 및 초기화"""
        self.log("🗑️ 정리 중...")
        try:
            # 서버 파일 삭제
            if self.current_audio_file:
                genai.configure(api_key=self.api_key.get().strip(), transport='rest')
                genai.delete_file(self.current_audio_file.name)
                self.log("☁️ 서버 파일 삭제 완료")
            
            # 로컬 파일 삭제
            if self.current_mp3_path and os.path.exists(self.current_mp3_path):
                os.remove(self.current_mp3_path)
                self.log("💻 로컬 MP3 삭제 완료")
                
        except Exception as e:
            self.log(f"⚠️ 삭제 중 경고: {e}")
        
        # 변수 초기화
        self.current_audio_file = None
        self.current_mp3_path = None
        self.reset_ui_state()
        self.log("✨ 초기화 완료. 새로운 URL을 입력하세요.")

    def reset_ui_state(self):
        self.btn_start.configure(state="normal")
        self.btn_chat.configure(state="disabled")
        self.btn_reset.configure(state="disabled")
        self.status_var.set("대기 중...")

if __name__ == "__main__":
    app = SoopModernApp()
    app.mainloop()