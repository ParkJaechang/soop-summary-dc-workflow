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
        self.title("SOOP Smart Summarizer (Time Police Ver.)")
        self.geometry("700x800")
        self.resizable(False, False)

        # 변수
        self.api_key = ctk.StringVar()
        self.save_dir = ctk.StringVar()
        self.url_var = ctk.StringVar()
        self.auto_delete = ctk.BooleanVar(value=True)
        self.status_var = ctk.StringVar(value="대기 중...")
        
        self.create_ui()
        self.load_config()

    def create_ui(self):
        self.header = ctk.CTkLabel(self, text="SOOP 방송 요약 & 타임라인 (시간 보정판)", font=("AppleSDGothicNeo-Bold", 24, "bold"))
        self.header.pack(pady=(30, 20))

        # 설정 프레임
        self.frame_settings = ctk.CTkFrame(self)
        self.frame_settings.pack(pady=10, padx=20, fill="x")

        ctk.CTkLabel(self.frame_settings, text="Gemini API Key").grid(row=0, column=0, padx=15, pady=10, sticky="w")
        self.entry_api = ctk.CTkEntry(self.frame_settings, textvariable=self.api_key, show="*", width=350)
        self.entry_api.grid(row=0, column=1, padx=10, pady=10)

        ctk.CTkLabel(self.frame_settings, text="저장 폴더").grid(row=1, column=0, padx=15, pady=10, sticky="w")
        self.entry_dir = ctk.CTkEntry(self.frame_settings, textvariable=self.save_dir, width=350, state="readonly")
        self.entry_dir.grid(row=1, column=1, padx=10, pady=10)
        self.btn_dir = ctk.CTkButton(self.frame_settings, text="폴더 선택", command=self.choose_directory, width=80)
        self.btn_dir.grid(row=1, column=2, padx=10, pady=10)

        # 입력 프레임
        self.frame_input = ctk.CTkFrame(self)
        self.frame_input.pack(pady=10, padx=20, fill="x")

        ctk.CTkLabel(self.frame_input, text="방송 URL").pack(anchor="w", padx=15, pady=(15, 5))
        self.entry_url = ctk.CTkEntry(self.frame_input, textvariable=self.url_var, width=600, height=40, placeholder_text="https://vod.sooplive.co.kr/player/...")
        self.entry_url.pack(padx=15, pady=(0, 15))

        self.switch_delete = ctk.CTkSwitch(self, text="작업 완료 후 오디오 파일 자동 삭제", variable=self.auto_delete, onvalue=True, offvalue=False)
        self.switch_delete.pack(pady=10)

        self.btn_start = ctk.CTkButton(self, text="분석 시작 (Start)", command=self.start_thread, width=200, height=50, font=("Arial", 16, "bold"), fg_color="#0066cc")
        self.btn_start.pack(pady=20)

        self.lbl_status = ctk.CTkLabel(self, textvariable=self.status_var, font=("Arial", 14), text_color="#FFcc00")
        self.lbl_status.pack(pady=5)

        self.log_area = ctk.CTkTextbox(self, width=660, height=200, font=("Consolas", 12))
        self.log_area.pack(pady=10)
        self.log_area.configure(state="disabled")

    def log(self, message):
        self.log_area.configure(state="normal")
        self.log_area.insert("end", message + "\n")
        self.log_area.see("end")
        self.log_area.configure(state="disabled")
        self.status_var.set(message)

    def choose_directory(self):
        path = filedialog.askdirectory()
        if path:
            self.save_dir.set(path)
            self.save_config()

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
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def get_best_model(self, api_key):
        try:
            genai.configure(api_key=api_key, transport='rest')
            models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            for m in models: 
                if 'flash' in m: return m
            return models[0] if models else None
        except Exception as e:
            self.log(f"❌ 모델 검색 오류: {e}")
            return None

    def time_to_seconds(self, time_str):
        """[HH:MM:SS] 문자열을 초(int)로 변환"""
        try:
            # 대괄호 제거 및 분리
            clean_str = time_str.replace('[', '').replace(']', '')
            parts = list(map(int, clean_str.split(':')))
            if len(parts) == 3:
                return parts[0] * 3600 + parts[1] * 60 + parts[2]
            elif len(parts) == 2:
                return parts[0] * 60 + parts[1]
            return 0
        except:
            return 0

    def seconds_to_time(self, seconds):
        """초(int)를 [HH:MM:SS] 문자열로 변환"""
        return f"[{str(timedelta(seconds=int(seconds))).zfill(8)}]"

    def enforce_linearity(self, text, video_duration_sec):
        """
        [시간 경찰 기능]
        1. 98초 같은 형식 오류 수정
        2. 06분 -> 32분 같은 급발진(스파이크) 감지 및 강제 교정
        3. 시간 역행(타임루프) 방지
        """
        self.log("👮 타임라인 논리 검사 및 교정 중...")
        
        lines = text.split('\n')
        corrected_lines = []
        last_valid_seconds = 0
        
        # 타임스탬프 패턴 찾기 (예: [00:05:30])
        timestamp_pattern = re.compile(r'\[(\d{1,2}):(\d{2}):(\d{2})\]')

        for line in lines:
            match = timestamp_pattern.search(line)
            if match:
                # 1. 형식적 오류 수정 (98초 -> 1분 38초)
                h, m, s = map(int, match.groups())
                if s >= 60:
                    m += s // 60; s %= 60
                if m >= 60:
                    h += m // 60; m %= 60
                
                current_seconds = h * 3600 + m * 60 + s
                
                # 2. 논리적 오류 교정 (Time Police)
                
                # Case A: 영상 길이보다 긴 시간? -> 단위 착각일 확률 높음 (시프트)
                if current_seconds > video_duration_sec:
                    # 혹시 [분:초:밀리초]였나? 한 칸씩 밀어보기
                    shifted_seconds = h * 60 + m
                    if shifted_seconds <= video_duration_sec:
                        current_seconds = shifted_seconds
                    else:
                        # 그래도 이상하면 바로 직전 시간 + 1분으로 강제 조정
                        current_seconds = last_valid_seconds + 60

                # Case B: 급발진 (스파이크) 감지
                # 직전 시간보다 10분 이상 갑자기 점프했다면? (단, 초반부는 제외)
                if last_valid_seconds > 0 and (current_seconds - last_valid_seconds > 600):
                    # 너무 큰 점프는 환각으로 간주하고, 그냥 직전 시간 + 2분 정도로 평탄화
                    current_seconds = last_valid_seconds + 120
                
                # Case C: 시간 역행 (과거로 돌아감)
                if current_seconds < last_valid_seconds:
                    # 과거로 가면 안 되므로, 직전 시간과 똑같이 맞추거나 10초 뒤로 설정
                    current_seconds = last_valid_seconds + 10

                # 교정된 값을 다시 문자열로 변환
                corrected_time_str = self.seconds_to_time(current_seconds)
                
                # 원본 라인의 타임스탬프를 교정된 것으로 교체
                line = timestamp_pattern.sub(corrected_time_str, line)
                
                last_valid_seconds = current_seconds

            corrected_lines.append(line)

        # 마크다운 제거
        result_text = '\n'.join(corrected_lines)
        result_text = result_text.replace("**", "").replace("##", "")
        result_text = re.sub(r'\n{3,}', '\n\n', result_text)
        
        return result_text

    def start_thread(self):
        if not self.api_key.get().strip() or not self.save_dir.get().strip() or not self.url_var.get().strip():
            messagebox.showwarning("입력 확인", "API 키, 저장 폴더, URL을 모두 입력해주세요.")
            return
        self.save_config()
        self.btn_start.configure(state="disabled", text="작업 진행 중...")
        threading.Thread(target=self.run_process, daemon=True).start()

    def run_process(self):
        try:
            url = self.url_var.get().strip()
            save_path = self.save_dir.get()
            safe_key = self.api_key.get().strip()
            
            # FFmpeg 체크
            if getattr(sys, 'frozen', False): script_dir = os.path.dirname(sys.executable)
            else: script_dir = os.path.dirname(os.path.abspath(__file__))
            ffmpeg_path = os.path.join(script_dir, "ffmpeg.exe")
            
            if not os.path.exists(ffmpeg_path):
                self.log("🚨 [오류] ffmpeg.exe 없음")
                self.reset_button()
                return

            self.log("📡 모델 연결 중...")
            model_name = self.get_best_model(safe_key)
            if not model_name:
                self.log("❌ AI 연결 실패")
                self.reset_button()
                return

            self.log("🚀 오디오 추출 중 (Mono/64k)...")
            output_template = os.path.join(save_path, "%(uploader)s_%(title)s_%(upload_date)s.%(ext)s")
            
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_template,
                'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '64'}],
                'postprocessor_args': ['-ac', '1', '-map_metadata', '-1'],
                'ffmpeg_location': script_dir,
                'quiet': True, 'no_warnings': True,
            }

            mp3_filename = ""
            video_duration_str = ""
            video_duration_sec = 0

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                mp3_filename = os.path.splitext(filename)[0] + ".mp3"
                video_duration_sec = info.get('duration', 0)
                video_duration_str = time.strftime('%H:%M:%S', time.gmtime(video_duration_sec))

            self.log(f"✅ 추출 완료 (영상길이: {video_duration_str})")
            
            self.log("⚡ AI 분석 시작 (시간 순차 필터 적용)...")
            genai.configure(api_key=safe_key, transport='rest')
            audio_file = genai.upload_file(path=mp3_filename)
            
            while audio_file.state.name == "PROCESSING":
                time.sleep(1)
                audio_file = genai.get_file(audio_file.name)
            
            if audio_file.state.name == "FAILED":
                self.log("❌ AI 업로드 실패")
                self.reset_button()
                return

            prompt = f"""
            너는 SOOP 방송 편집자야. 오디오를 듣고 타임라인을 작성해.
            
            [영상 정보]
            - 총 길이: {video_duration_str}
            
            [절대 규칙]
            1. 타임라인은 반드시 `[HH:MM:SS]` 형식을 유지해.
            2. 시간은 순차적으로 흘러가야 해. (갑자기 30분 점프 금지)
            3. 후원 리액션이나 잡담은 제외하고 핵심 내용만 적어.
            
            [출력 양식]
            【 📋 3줄 요약 】
            - ...

            【 🕒 상세 타임라인 】
            [00:00:00] 방송 시작
            [HH:MM:SS] 내용
            
            【 ⭐ 하이라이트 】
            [HH:MM:SS] 제목 (이유)
            
            【 💬 주요 멘트 】
            [HH:MM:SS] "내용"
            """
            
            model = genai.GenerativeModel(model_name)
            response = model.generate_content([prompt, audio_file])
            
            # === [최종병기] 타임라인 강제 교정 ===
            # AI가 뱉은 텍스트를 한 줄 한 줄 검사해서 시간 오류를 싹 고칩니다.
            final_text = self.enforce_linearity(response.text, video_duration_sec)
            
            txt_filename = mp3_filename.replace(".mp3", "_요약.txt")
            with open(txt_filename, "w", encoding="utf-8") as f:
                f.write(final_text)
            
            self.log("🎉 완료! 결과 파일을 엽니다.")
            os.startfile(txt_filename)

            if self.auto_delete.get():
                try:
                    genai.delete_file(audio_file.name)
                    os.remove(mp3_filename)
                    self.log("🗑️ 오디오 파일 삭제됨")
                except: pass

        except Exception as e:
            self.log(f"❌ 오류: {e}")
        finally:
            self.reset_button()

    def reset_button(self):
        self.btn_start.configure(state="normal", text="분석 시작 (Start)")
        self.status_var.set("대기 중...")

if __name__ == "__main__":
    app = SoopModernApp()
    app.mainloop()