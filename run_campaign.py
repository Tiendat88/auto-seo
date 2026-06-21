import sys
import requests

def main():
    if len(sys.argv) < 2:
        print("Sử dụng: python run_campaign.py \"<từ khóa chính>\" [số lượng từ khóa phụ]")
        sys.exit(1)
        
    main_keyword = sys.argv[1]
    num_keywords = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    
    print(f"🚀 Đang gửi lệnh tạo chiến dịch cho từ khóa: '{main_keyword}'...")
    
    url = "http://localhost:8000/api/jobs/campaign"
    payload = {
        "main_keyword": main_keyword,
        "num_keywords": num_keywords,
        "language": "vi"
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        
        print("\n✅ Thành công! DeepSeek đã phân rã thành các từ khóa sau:")
        for idx, kw in enumerate(data.get("generated_keywords", []), 1):
            print(f"  {idx}. {kw}")
            
        print("\n⏳ Hệ thống đã tự động tạo các tiến trình (Jobs) tương ứng.")
        print("👉 Vui lòng mở http://localhost:3050/pipeline để xem AI đang viết bài!")
        
    except Exception as e:
        print(f"❌ Lỗi khi gửi yêu cầu: {e}")

if __name__ == "__main__":
    main()
