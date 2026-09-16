# Ground Truth Directory

Đặt các file `.txt` vào đây để tính WER/CER.

## Quy tắc đặt tên

File `.txt` phải có tên giống với file audio (bỏ extension).

**Ví dụ:**
```
input/
  file_test_1m.MP3
  meeting_clip.wav

ground_truth/
  file_test_1m.txt         ← transcript cho file_test_1m.MP3
  meeting_clip.txt         ← transcript cho meeting_clip.wav
```

> Tên file được so sánh theo **stem** (phần trước dấu `.`), không phân biệt hoa/thường.

## Định dạng file .txt

Plain text, UTF-8. Chỉ cần text thô, không cần timestamp hay speaker label.

```
Xin chào, đây là bài kiểm tra. Tôi đang kiểm tra chất lượng âm thanh.
```

Nếu không có file ground truth cho một audio nào, WER/CER của file đó sẽ là `N/A`.

## Cách chạy evaluate

```bash
cd /home/thanhnguyen/code/voice/audio_enhancement

# Evaluate toàn bộ output (cần backend ASR đang chạy)
python evaluate.py

# Chỉ evaluate một số pipeline cụ thể
python evaluate.py --only pipeline1.1,pipeline1.2,ap_bwe

# Dùng server khác / port khác
python evaluate.py --ws-url ws://localhost:8005

# Tiếng Anh, tắt diarization (nhanh hơn)
python evaluate.py --language en --no-detect-speaker

# Bỏ qua file đã có transcript cached
python evaluate.py --skip-existing
```

## Output

```
results/
  eval_report_20260401_120000.json    ← full JSON (summary + details)
  eval_summary_20260401_120000.csv    ← 1 row per enhancer
  eval_detail_20260401_120000.csv     ← 1 row per audio file
  transcripts/
    pipeline1.1/
      file_test_1m.json              ← cached ASR transcript
    pipeline1.2/
      file_test_1m.json
```
