# -*- coding: utf-8 -*-
import sys
import re
import unicodedata
from collections import Counter
# Set encoding to utf-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def remove_speaker_and_timestamps(text):
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if re.match(r'^Speaker\s+\d+$', stripped, re.IGNORECASE):
            continue
        if re.match(r'^\d+(?::\d+)+(?:\.\d+)?\s*[\-–—~]\s*\d+(?::\d+)+(?:\.\d+)?$', stripped):
            continue
        if stripped.lower() in ('nam', 'nữ', 'nu'):
            continue
        cleaned_lines.append(line)
    return '\n'.join(cleaned_lines)


from janome.tokenizer import Tokenizer

_janome_tokenizer = None

def get_tokenizer():
    global _janome_tokenizer
    if _janome_tokenizer is None:
        _janome_tokenizer = Tokenizer()
    return _janome_tokenizer

def kata_to_hira(text: str) -> str:
    res = []
    for ch in text:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:
            res.append(chr(code - 0x60))
        else:
            res.append(ch)
    return ''.join(res)

def to_hiragana_reading(text: str) -> str:
    """Chuẩn hóa Hán tự (Kanji) và Katakana về cùng 1 kiểu chữ Hiragana ngữ âm."""
    t = get_tokenizer()
    res = []
    for tok in t.tokenize(text):
        r = tok.reading
        if r and r != '*':
            res.append(kata_to_hira(r))
        else:
            res.append(kata_to_hira(tok.surface))
    return ''.join(res)


def clean_text(text):
    text = unicodedata.normalize('NFKC', text)
    text = remove_speaker_and_timestamps(text)
    # Phân tích ngữ âm trước khi xóa dấu câu để giữ nguyên ranh giới từ ngữ cảnh
    text = to_hiragana_reading(text)
    text = re.sub(r'[\s\u3000]+', '', text)
    # Loại bỏ dấu câu và ký tự trường âm Katakana 'ー' (Chōonpu)
    text = re.sub(
        r'[、。・！？「」『』【】〔〕《》〈〉（）(),.!?\-—…～~・゛゜ー]+',
        '', text
    )
    return text

def get_words(text):
    text = remove_speaker_and_timestamps(text)
    try:
        import MeCab
        tagger = MeCab.Tagger('-Owakati')
        parsed = tagger.parse(text)
        if not parsed:
            return []
        raw_words = parsed.strip().split()
    except Exception:
        raw_words = list(text)
        
    cleaned_words = []
    for word in raw_words:
        cleaned_word = re.sub(r'[、。・！？「」（）()\[\],.!?\-—\s\u3000]+', '', word)
        if cleaned_word:
            cleaned_words.append(cleaned_word)
    return cleaned_words
def levenshtein_distance(ref, hyp):
    m, n = len(ref), len(hyp)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref[i - 1] == hyp[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = min(
                    dp[i - 1][j] + 1,    
                    dp[i][j - 1] + 1,   
                    dp[i - 1][j - 1] + 1 
                )
    return dp[m][n], dp
def get_alignment(ref, hyp, dp):
    i, j = len(ref), len(hyp)
    align_ref = []
    align_hyp = []
    operations = []
    
    while i > 0 or j > 0:
        if i > 0 and j > 0 and ref[i - 1] == hyp[j - 1]:
            align_ref.append(ref[i - 1])
            align_hyp.append(hyp[j - 1])
            operations.append('match')
            i -= 1
            j -= 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
            align_ref.append(ref[i - 1])
            align_hyp.append(hyp[j - 1])
            operations.append('sub')
            i -= 1
            j -= 1
        elif j > 0 and (i == 0 or dp[i][j] == dp[i][j - 1] + 1):
            align_ref.append('*')
            align_hyp.append(hyp[j - 1])
            operations.append('ins')
            j -= 1
        elif i > 0 and (j == 0 or dp[i][j] == dp[i - 1][j] + 1):
            align_ref.append(ref[i - 1])
            align_hyp.append('*')
            operations.append('del')
            i -= 1
            
    align_ref.reverse()
    align_hyp.reverse()
    operations.reverse()
    return align_ref, align_hyp, operations
def evaluate_texts(ref_raw: str, hyp_raw: str, verbose: bool = True):
    ref_chars = clean_text(ref_raw)
    hyp_chars = clean_text(hyp_raw)

    dist_c, dp_c = levenshtein_distance(ref_chars, hyp_chars)
    align_ref_c, align_hyp_c, operations_c = get_alignment(ref_chars, hyp_chars, dp_c)

    deletions_c = operations_c.count('del')
    insertions_c = operations_c.count('ins')
    substitutions_c = operations_c.count('sub')
    matches_c = operations_c.count('match')

    ref_len = len(ref_chars)
    cer = (dist_c / ref_len * 100) if ref_len > 0 else 0.0
    accuracy_c = max(0.0, 100.0 - cer)

    # B. Counter Character Frequency Match
    ref_counts_c = Counter(ref_chars)
    hyp_counts_c = Counter(hyp_chars)
    common_counts_c = ref_counts_c & hyp_counts_c
    total_matched_chars = sum(common_counts_c.values())
    match_rate_c = (total_matched_chars / len(ref_chars)) * 100 if len(ref_chars) > 0 else 0.0

    if verbose:
        print("============================================================")
        print("CHARACTER-LEVEL ALIGNMENT (CER)")
        print("============================================================")
        print(f"Cleaned Ref length: {len(ref_chars)}")
        print(f"Cleaned Hyp length: {len(hyp_chars)}")
        print(f"Levenshtein Distance (Total Errors): {dist_c}")
        print(f"Deletions: {deletions_c}")
        print(f"Insertions: {insertions_c}")
        print(f"Substitutions: {substitutions_c}")
        print(f"Matches: {matches_c}")
        print(f"CER: {cer:.4f}%")
        print(f"Độ chính xác (Accuracy): {accuracy_c:.2f}%")
        print("\n--- Differences Detail (Without Punctuation/Spaces) ---")
        for op, r, h in zip(operations_c, align_ref_c, align_hyp_c):
            if op != 'match':
                print(f"Op: {op.upper()} | Ref: '{r}' | Hyp: '{h}'")

        print("\n")
        print("============================================================")
        print("SO KHỚP TẦN SUẤT KÝ TỰ (CHARACTER COUNTER MATCH)")
        print("============================================================")
        print(f"Tổng số ký tự gốc (Ref): {len(ref_chars)}")
        print(f"Tổng số ký tự dự đoán (Hyp): {len(hyp_chars)}")
        print(f"Số ký tự trùng khớp: {total_matched_chars}")
        print(f"Độ trùng khớp (Match Rate): {match_rate_c:.2f}%")

        print("\n--- Chi tiết sai sót (Không tính lệch dòng) ---")
        missing_c = ref_counts_c - hyp_counts_c
        if missing_c:
            print("Những chữ bị AI nhận diện THIẾU:")
            for char, count in missing_c.items():
                print(f"  - '{char}': thiếu {count} lần")

        extra_c = hyp_counts_c - ref_counts_c
        if extra_c:
            print("\nNhững chữ AI nhận diện THỪA:")
            for char, count in extra_c.items():
                print(f"  - '{char}': thừa {count} lần")
        print("\n")

    return {
        "ref_clean": ref_chars,
        "hyp_clean": hyp_chars,
        "dist": dist_c,
        "cer": cer,
        "accuracy": accuracy_c,
        "match_rate": match_rate_c,
        "deletions": deletions_c,
        "insertions": insertions_c,
        "substitutions": substitutions_c
    }


class JapaneseASREvaluator:
    """ASR evaluation standard for Japanese text."""

    @staticmethod
    def normalize_strict(text: str) -> str:
        """1. CER Strict: Giữ nguyên Hán tự & Katakana, chỉ bỏ speaker label, timestamp, khoảng trắng/xuống dòng."""
        text = remove_speaker_and_timestamps(text)
        return re.sub(r'[\s\u3000\r\n]+', '', text)

    @staticmethod
    def normalize_standard(text: str) -> str:
        """2. CER Standard: Chuẩn hóa NFKC, bỏ speaker, timestamp, dấu câu và khoảng trắng."""
        text = unicodedata.normalize('NFKC', text)
        text = remove_speaker_and_timestamps(text)
        text = re.sub(r'[、。・！？「」『』【】〔〕《》〈〉（）(),.!?\-—…～~・゛゜ー]+', '', text)
        return re.sub(r'[\s\u3000\r\n]+', '', text)

    @staticmethod
    def normalize_loose(text: str) -> str:
        """3. CER Loose: Chuẩn hóa ngữ âm Hiragana qua Janome, loại bỏ dấu câu và filler words."""
        return clean_text(text)

    @staticmethod
    def calc_cer(ref: str, hyp: str) -> float:
        """Calculate CER in ratio [0.0, 1.0]."""
        if not ref:
            return 0.0 if not hyp else 1.0
        dist, _ = levenshtein_distance(ref, hyp)
        return dist / len(ref)


if __name__ == '__main__':
    import os

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    GT_DIR = os.path.join(BASE_DIR, "ground_truth")

    default_ref = """
お電話ありがとうございます。建設のエスタと申します。あ、いつもお世話になってます。AJテクノロジーズの山下です。はい、お世話になっております。お世話になります。すいません、カセさんってお戻りになられてますか？あ、ちょっと今外出しちゃってるんですけども。あ、かしこまりました。じゃあまた改めてご連絡させていただきます。あ、はい、かしこまりました。すいません、どうもありがとうございます。はい、失礼いたします。失礼いたします。
"""
    default_hyp = """
ありがとうございます。三水建設の須田と申します。いつもお世話になってます。AJテクノロジーズの山下です。はい、お世話になっております。お世話になります。すみません、川本さんともどうになられてますか。あ、ちょっと今外出しちゃってるんです。あ、けれども。かしこまりました。また改めてご連絡させていただきます。かしこまりました。すみません、どうもありがとうございます。はい、失礼いたします。失礼いたします。
"""
    if len(sys.argv) >= 3:
        p1, p2 = sys.argv[1], sys.argv[2]
        # Hỗ trợ tìm trong thư mục ground_truth nếu p1 chỉ là tên file
        if not os.path.isfile(p1) and os.path.isfile(os.path.join(GT_DIR, p1)):
            p1 = os.path.join(GT_DIR, p1)
        ref = open(p1, encoding='utf-8').read() if os.path.isfile(p1) else p1
        hyp = open(p2, encoding='utf-8').read() if os.path.isfile(p2) else p2
    else:
        ref = default_ref
        hyp = default_hyp

    evaluate_texts(ref, hyp)

