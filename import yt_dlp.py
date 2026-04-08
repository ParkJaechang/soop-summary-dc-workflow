import yt_dlp
import os
import tkinter as tk
from tkinter import filedialog

# === 설정 ===
file_name_base = "방송오디오" 

def download_audio():
    # 1. 다운로드 주소 입력 받기
    url = input("▶ 다운로드할 SOOP(아프리카) 다시보기 주소를 붙여넣으세요: ")
    
    if not url:
        print("주소가 입력되지 않았습니다.")
        return

    print("\n📂 저장할 폴더를 선택하는 창을 띄웁니다...")
    print("(창이 뜨지 않으면 작업표시줄의 '깃털 모양' 아이콘을 확인하세요)")

    # 2. 윈도우 폴더 선택 창 띄우기
    root = tk.Tk()
    root.withdraw() # 빈 창 숨기기
    root.attributes('-topmost', True) # 창을 맨 앞으로 가져오기
    save_path = filedialog.askdirectory(title="오디오를 저장할 폴더를 선택하세요")
    
    # 취소 눌렀을 경우 대비
    if not save_path:
        print("❌ 폴더 선택이 취소되었습니다. 프로그램을 종료합니다.")
        return

    print(f"\n🚀 다운로드를 시작합니다... \n📍 저장 위치: {save_path}")

    # 3. yt-dlp 설정 (경로 결합)
    # 선택한 폴더 경로 + 파일이름 + 확장자
    output_template = os.path.join(save_path, f'{file_name_base}.%(ext)s')

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_template,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        print(f"\n" + "="*40)
        print(f"✅ 다운로드 성공!")
        print(f"📂 확인하러 가기 -> {save_path}")
        print(f"="*40)
        
        # 다운로드 끝난 폴더 자동으로 열어주기 (서비스 기능)
        os.startfile(save_path)

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")

if __name__ == "__main__":
    download_audio()
    input("\n종료하려면 엔터키를 누르세요...")