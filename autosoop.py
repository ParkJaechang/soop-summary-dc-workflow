import yt_dlp
import os
import sys
import time
import google.generativeai as genai
import tkinter as tk
from tkinter import filedialog

# ==========================================
# 🔑 [필수] API 키를 따옴표 안에 넣으세요
RAW_API_KEY = "AIzaSyAy3lQDoKTH4RtBe4tEBOVKLy0dKUQ4sYM"
# ==========================================

def get_script_directory():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_best_model(api_key):
    """
    [핵심 해결책]
    하드코딩된 이름을 쓰지 않고, API에게 직접 '사용 가능한 모델'을 물어본 뒤
    가장 적합한(Flash) 모델을 자동으로 선택합니다.
    """
    print("📡 사용 가능한 AI 모델을 검색 중입니다...")
    try:
        genai.configure(api_key=api_key, transport='rest')
        
        available_models = []
        # 내 키로 쓸 수 있는 모든 모델 가져오기
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        
        if not available_models:
            print("❌ 오류: 사용 가능한 모델이 하나도 없습니다. API 키를 확인해주세요.")
            return None

        # 1순위: Flash 모델 찾기
        for model_name in available_models:
            if 'flash' in model_name:
                print(f"✅ 최적의 모델을 찾았습니다: {model_name}")
                return model_name
        
        # 2순위: Pro 모델 찾기 (Flash가 없을 경우)
        for model_name in available_models:
            if 'pro' in model_name:
                print(f"⚠️ Flash 모델이 없어 Pro 모델을 사용합니다: {model_name}")
                return model_name

        # 3순위: 아무거나 첫 번째 모델
        print(f"⚠️ 특정 모델을 찾지 못해 기본 모델을 사용합니다: {available_models[0]}")
        return available_models[0]

    except Exception as e:
        print(f"❌ 모델 검색 중 오류 발생: {e}")
        return None

def download_clean_mp3(url, save_path):
    print(f"\n🚀 [1단계] 방송 오디오 다운로드 및 MP3 변환 시작...")
    script_dir = get_script_directory()
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    file_base = f"방송오디오_{timestamp}"
    output_template = os.path.join(save_path, f'{file_base}.%(ext)s')

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_template,
        'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}],
        'ffmpeg_location': script_dir,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        mp3_path = os.path.join(save_path, f"{file_base}.mp3")
        print(f"   ✅ MP3 변환 완료: {mp3_path}")
        return mp3_path
    except Exception as e:
        print(f"❌ 다운로드/변환 오류: {e}")
        return None

def summarize_with_auto_model(audio_path, model_name):
    print(f"\n⚡ [2단계] AI 요약 시작 (사용 모델: {model_name})")
    
    try:
        # 파일 업로드
        print("   📤 오디오 파일 업로드 중...")
        audio_file = genai.upload_file(path=audio_path)
        
        while audio_file.state.name == "PROCESSING":
            print(".", end="", flush=True)
            time.sleep(2)
            audio_file = genai.get_file(audio_file.name)
        
        if audio_file.state.name == "FAILED":
            print("\n❌ AI 서버 업로드 실패.")
            return None

        print("\n   ✅ 업로드 완료! 분석 시작...")

        # 선택된 모델로 요약 요청
        model = genai.GenerativeModel(model_name)
        
        prompt = """
        이 파일은 인터넷 방송(SOOP)의 오디오야. 전문 편집자 관점에서 아래 내용을 정리해줘.
        1. [방송 3줄 요약]
        2. [상세 타임라인] (시간대별 주제)
        3. [유튜브 각(하이라이트)] (재미있는 구간 3곳 추천)
        4. [주요 멘트]
        """
        response = model.generate_content([prompt, audio_file])
        return response.text

    except Exception as e:
        print(f"\n❌ AI 요약 오류: {e}")
        return None

def main():
    # 1. API 키 확인
    safe_key = RAW_API_KEY.strip()
    if not safe_key:
        print("\n❌ 오류: API 키가 입력되지 않았습니다!")
        input("종료하려면 엔터...")
        return

    # 2. FFmpeg 확인
    script_dir = get_script_directory()
    if not os.path.exists(os.path.join(script_dir, "ffmpeg.exe")):
        print("\n🚨 [비상] ffmpeg.exe 파일이 없습니다!")
        input("종료하려면 엔터...")
        return

    # 3. 모델 자동 감지 (여기서 404 원천 차단)
    target_model = get_best_model(safe_key)
    if not target_model:
        input("모델을 찾지 못해 종료합니다...")
        return

    # 4. URL 입력 및 다운로드
    url = input("\n▶ SOOP(아프리카) 다시보기 URL 입력: ")
    if not url: return

    print("\n📂 파일을 저장할 폴더를 선택하세요...")
    root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)
    save_path = filedialog.askdirectory()
    if not save_path: return

    mp3_path = download_clean_mp3(url, save_path)
    
    if mp3_path and os.path.exists(mp3_path):
        # 5. 찾아낸 모델로 요약 실행
        summary_text = summarize_with_auto_model(mp3_path, target_model)
        
        if summary_text:
            txt_filename = os.path.basename(mp3_path).replace(".mp3", "_요약.txt")
            result_file = os.path.join(save_path, txt_filename)
            with open(result_file, "w", encoding="utf-8") as f:
                f.write(summary_text)
            print(f"\n🎉 성공! 요약본 저장 완료: {result_file}")
            os.startfile(result_file)
    
    input("\n종료하려면 엔터키를 누르세요...")

if __name__ == "__main__":
    main()