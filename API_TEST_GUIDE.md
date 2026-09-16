# Hướng dẫn chạy Test Realtime API với Modal & Qwen3-ASR-1.7B-hf

Tài liệu này hướng dẫn cách khởi chạy và test API Realtime Speech-to-Text, bao gồm 3 bước chính:
1. Tải model weights lên Modal Volume.
2. Khởi chạy server FastAPI trên Modal.
3. Khởi chạy Web Client (Gradio) để test qua Microphone.

---

## 🛠 Yêu cầu trước khi bắt đầu
- Đã cài đặt [Modal](https://modal.com/docs/guide).
- Đã đăng nhập Modal trên máy (chạy `modal token new`).
- Đứng tại thư mục gốc của project (nơi chứa file `modal_run.py`).

---

## Bước 1: Tải Model Weights (Chỉ cần chạy 1 lần đầu)

Script này sẽ tạo một Modal Volume tên là `VOICE` (nếu chưa có) và tải model `Qwen/Qwen3-ASR-1.7B-hf` từ Hugging Face Hub về lưu trên Volume này.

**Lệnh chạy:**
```bash
modal run 01_download_model.py
```
*Lưu ý: Quá trình này sẽ mất một chút thời gian để tải model (~vài GB). Đợi đến khi log báo "Download and volume commit completed successfully!"*

---

## Bước 2: Khởi chạy API Server trên Modal

Khởi chạy server FastAPI trên Modal. Cấu hình hiện tại sẽ sử dụng GPU A10G (24GB VRAM) và đọc file `.env` cục bộ (nếu có).

**Lệnh chạy phục vụ môi trường Dev (tắt khi dừng lệnh):**
```bash
modal serve modal_run.py
```

**Hoặc lệnh Deploy (chạy thường trực trên Modal):**
```bash
modal deploy modal_run.py
```

*Lưu ý: Sau khi chạy thành công, Modal sẽ cấp cho bạn một đường dẫn (ví dụ: `https://your-workspace--javis-api-qwen3-hf-serve-serve.modal.run`). Hãy copy phần host của đường dẫn này (chỉ giữ phần `your-workspace--javis-api-qwen3-hf-serve-serve.modal.run`) để dùng cho Bước 3.*

---

## Bước 3: Khởi chạy Client Gradio để thu âm và Test

Client này cung cấp giao diện Web Gradio để thu âm trực tiếp qua mic, đồng thời đẩy stream âm thanh qua WebSocket lên Server Modal vừa tạo.

**Lệnh chạy:**
```bash
# Sử dụng Python 3.11 (hoặc py -3.11):
py -3.11 03_openai_realtime_microphone_client_adaptive.py --ws-url wss://<MODAL_HOST>/api/v2/transcript/ws/no-diarization
```

> **Thay `<MODAL_HOST>` bằng host bạn lấy được ở Bước 2 (không bao gồm `https://`).**
> Ví dụ: `py -3.11 03_openai_realtime_microphone_client_adaptive.py --ws-url wss://your-workspace--javis-api-qwen3-hf-serve-serve.modal.run/api/v2/transcript/ws/no-diarization`

*(Nếu bạn chạy server Local không qua Modal, bạn có thể chạy: `py -3.11 03_openai_realtime_microphone_client_adaptive.py --ws-url ws://localhost:8000/api/v2/transcript/ws/no-diarization`)*


### Sử dụng Client:
1. Mở trình duyệt truy cập vào đường dẫn Gradio (`http://127.0.0.1:7860`).
2. Bấm nút **Start** và bắt đầu nói vào Microphone.
3. Chờ xem kết quả trả về liên tục (Streaming) trên giao diện.
4. Bạn cũng có thể mở rộng phần "Đánh Giá Độ Chính Xác (ASR CER Evaluation)" để so sánh kết quả với file Ground Truth có sẵn.

---

## Bước 4: Kiểm thử LangGraph Transcript Analysis API

Sau khi có văn bản thô từ ASR, bạn có thể gọi LangGraph pipeline để làm sạch dấu câu, tóm tắt và trích xuất action items:

**Endpoint:** `POST /api/v2/transcript/analyze`

**Ví dụ cURL:**
```bash
curl -X POST "https://<MODAL_HOST>/api/v2/transcript/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "raw_transcript": "hôm nay chúng ta họp về tiến độ dự án anh nam sẽ hoàn thành api vào thứ sáu còn chị hoa sẽ kiểm thử trước thứ hai tuần tới",
    "language": "Vietnamese"
  }'
```

**Chạy Unit Tests cho LangGraph (Python 3.11):**
```powershell
cd javis-api-qwen3-hf
.\.venv\Scripts\pytest.exe tests/test_agent_graphs.py -v
```

