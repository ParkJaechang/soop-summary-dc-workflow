import google.generativeai as genai
import sys

# ==========================================
# 🔑 [여기에 새 키를 붙여넣으세요]
# 붙여넣을 때 따옴표("") 안에 넣는 것 잊지 마세요!
RAW_API_KEY = "AIzaSyAy3lQDoKTH4RtBe4tEBOVKLy0dKUQ4sYM"
# ==========================================

# 1. 실수로 들어간 공백/줄바꿈 자동 제거 (수리)
API_KEY = RAW_API_KEY.strip()

print(f"🔑 입력된 키 확인 중... (길이: {len(API_KEY)})")

if not API_KEY or "여기에" in API_KEY:
    print("❌ 오류: API 키를 입력하지 않았습니다. 코드를 수정해주세요.")
    sys.exit()

if " " in API_KEY:
    print("❌ 오류: 키 중간에 띄어쓰기가 포함되어 있습니다. 다시 확인해주세요.")
    sys.exit()

# 2. 설정 및 모델 확인
print("📡 구글 서버에 연결 시도 중...")

try:
    # transport='rest' 옵션: gRPC 오류(Illegal header)를 우회하는 강력한 설정입니다.
    genai.configure(api_key=API_KEY, transport='rest') 
    
    print("\n✅ [연결 성공] 사용 가능한 모델 목록:")
    found_flash = False
    
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"- {m.name}")
            if 'flash' in m.name:
                found_flash = True
    
    print("\n" + "="*40)
    if found_flash:
        print("🎉 성공! 'gemini-1.5-flash' 모델을 쓸 수 있습니다.")
        print("이제 본 프로그램(auto_soop.py)에 키를 넣고 돌리시면 됩니다.")
    else:
        print("⚠️ 목록에 Flash 모델이 안 보입니다. 'gemini-pro'를 사용해야 할 수 있습니다.")
    print("="*40)

except Exception as e:
    print(f"\n❌ 여전히 오류가 발생했습니다: {e}")
    print("팁: VPN을 끄거나, 인터넷 연결을 확인해보세요.")