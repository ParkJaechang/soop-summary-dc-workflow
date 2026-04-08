import yt_dlp
import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog

# === 설정 ===
file_name_base = "방송영상_최종"

def get_script_directory():
    """
    현재 실행 중인 파이썬 파일(mp4.py)이 있는 폴더 경로를 정확히 가져옵니다.
    명령어를 어디서 치든 상관없이 파일 위치를 기준으로 잡습니다.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def fix_video_file(input_path, output_path, ffmpeg_exe):
    """고장난 영상을 FFmpeg로 강제 수리하는 함수"""
    print(f"\n🔧 [2단계] 영상 인덱스(재생바) 수리 중... (금방 끝납니다)")
    
    cmd = [
        ffmpeg_exe, '-y', '-i', input_path, '-c', 'copy',
        '-map', '0', '-movflags', '+faststart', output_path
    ]
    
    try:
        # 터미널에 지저분한 로그 안 뜨게 설정
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        print("✅ 수리 완료!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 수리 실패: {e}")
        return False

def download_video_perfect():
    # 1. 경로 설정 (핵심 수정 부분)
    # 이제 무조건 파이썬 파일 옆에 있는 ffmpeg를 찾습니다.
    script_dir = get_script_directory()
    ffmpeg_path = os.path.join(script_dir, "ffmpeg.exe")
    
    print(f"🔍 FFmpeg 찾는 위치: {ffmpeg_path}")
    
    if not os.path.exists(ffmpeg_path):
        print("\n🚨 [오류] ffmpeg.exe 파일이 없습니다!")
        print(f"현재 파이썬 파일 위치: {script_dir}")
        print("반드시 이 폴더 안에 ffmpeg.exe를 넣어주세요.")
        return

    # 2. URL 입력
    url = input("▶ 다운로드할 SOOP(아프리카) 다시보기 주소를 붙여넣으세요: ")
    if not url: return

    # 3. 저장 폴더 선택
    print("\n📂 저장할 폴더를 선택하세요...")
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    save_path = filedialog.askdirectory()
    if not save_path: return

    print(f"\n🚀 [1단계] 영상 다운로드 시작...")

    temp_filename = f"{file_name_base}_raw.mp4"
    temp_path = os.path.join(save_path, temp_filename)
    final_filename = f"{file_name_base}_완성.mp4"
    final_path = os.path.join(save_path, final_filename)

    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': temp_path,
        'merge_output_format': 'mp4',
        'ffmpeg_location': script_dir, # FFmpeg 위치 강제 지정
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        if os.path.exists(temp_path):
            if fix_video_file(temp_path, final_path, ffmpeg_path):
                os.remove(temp_path) # 원본 삭제
                print(f"\n" + "="*40)
                print(f"🎉 작업 끝! 재생바가 정상 작동합니다.")
                print(f"📂 파일 위치: {final_path}")
                print(f"="*40)
                os.startfile(save_path)
            else:
                print("⚠️ 수리에 실패했습니다.")
        else:
            print("❌ 다운로드된 파일을 찾을 수 없습니다.")

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")

if __name__ == "__main__":
    download_video_perfect()
    input("\n종료하려면 엔터키를 누르세요...")