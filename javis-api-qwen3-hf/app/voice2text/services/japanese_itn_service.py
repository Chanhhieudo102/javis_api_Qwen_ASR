# -*- coding: utf-8 -*-
"""
japanese_itn_service.py
========================
Module Inverse Text Normalization (ITN) tổng quát cho tiếng Nhật trong ASR.
Chỉ áp dụng các quy tắc ngữ pháp và biểu diễn số tổng quát, TUYỆT ĐỐI KHÔNG hardcode từ vựng:
1. Chuỗi số đọc rời (đặc trưng số điện thoại, mã số): 'ゼロ五ゼロ' -> '050', '一七八二' -> '1782'.
2. Ngày trong tháng tổng quát: '十四日' -> '14日', '二十一日' -> '21日'.
3. Thời gian tổng quát: '九時' -> '9時', '二十一時' -> '21時', '三十分' -> '30分'.
"""

import re
from typing import Dict

KANJI_DIGIT_MAP: Dict[str, str] = {
    "〇": "0", "零": "0", "ゼロ": "0", "ぜろ": "0",
    "一": "1", "壱": "1", "いち": "1",
    "二": "2", "弐": "2", "に": "2",
    "三": "3", "参": "3", "さん": "3",
    "四": "4", "よん": "4", "し": "4",
    "五": "5", "ご": "5",
    "六": "6", "ろく": "6",
    "七": "7", "なな": "7", "しち": "7",
    "八": "8", "はち": "8",
    "九": "9", "きゅう": "9", "く": "9",
}

KANJI_DIGITS_ONLY: Dict[str, str] = {
    "〇": "0", "零": "0",
    "一": "1", "壱": "1",
    "二": "2", "弐": "2",
    "三": "3", "参": "3",
    "四": "4",
    "五": "5",
    "六": "6",
    "七": "7",
    "八": "8",
    "九": "9",
}

def kanji_number_to_arabic(kanji_str: str) -> int:
    """Chuyển chuỗi chữ Hán số lượng tổng quát (như 十四, 二十一, 百二十) sang int."""
    units = {"十": 10, "百": 100, "千": 1000, "万": 10000}
    val = 0
    temp = 0
    for char in kanji_str:
        if char in KANJI_DIGITS_ONLY:
            temp = int(KANJI_DIGITS_ONLY[char])
        elif char in units:
            unit_val = units[char]
            if temp == 0:
                temp = 1
            val += temp * unit_val
            temp = 0
    val += temp
    return val


class JapaneseITNService:
    """Dịch vụ chuẩn hóa số tổng quát (ITN) tiếng Nhật cho ASR."""

    @staticmethod
    def normalize_phone_digit_sequences(text: str) -> str:
        """
        Nhận diện và chuyển đổi các chuỗi số đọc rời tổng quát (đặc trưng số điện thoại / ID).
        Ví dụ: 'ゼロ五ゼロ' -> '050', '一七八二' -> '1782', '一八八ゼロ' -> '1880'.
        """
        pattern = re.compile(r'([〇零ゼロぜろ一二三四五六七八九壱弐参]{2,})')
        
        def replace_digits(m: re.Match) -> str:
            s = m.group(1)
            # Nếu chứa các đơn vị hàng chục, trăm, nghìn thì không phải chuỗi số đọc rời
            if any(k in s for k in ("十", "百", "千", "万")):
                return s
            res = []
            i = 0
            while i < len(s):
                matched = False
                for token, digit in (("ゼロ", "0"), ("ぜろ", "0")):
                    if s[i:i+2] == token:
                        res.append(digit)
                        i += 2
                        matched = True
                        break
                if not matched:
                    ch = s[i]
                    res.append(KANJI_DIGIT_MAP.get(ch, ch))
                    i += 1
            return "".join(res)

        return pattern.sub(replace_digits, text)

    @staticmethod
    def normalize_time_and_dates(text: str) -> str:
        """
        Chuẩn hóa ngày tháng và thời gian tổng quát:
        '十四日' -> '14日', '二十一日' -> '21日', '十時' -> '10時', '二十一時' -> '21時'.
        """
        # Ngày: [Số Kanji]日
        day_pat = re.compile(r'([一二三四五六七八九十]+)日')
        def replace_day(m: re.Match) -> str:
            val = kanji_number_to_arabic(m.group(1))
            return f"{val}日"
        text = day_pat.sub(replace_day, text)

        # Giờ: [Số Kanji]時
        hour_pat = re.compile(r'([一二三四五六七八九十]+)時')
        def replace_hour(m: re.Match) -> str:
            val = kanji_number_to_arabic(m.group(1))
            return f"{val}時"
        text = hour_pat.sub(replace_hour, text)

        # Phút: [Số Kanji]分
        minute_pat = re.compile(r'([一二三四五六七八九十]+)分')
        def replace_min(m: re.Match) -> str:
            val = kanji_number_to_arabic(m.group(1))
            return f"{val}分"
        text = minute_pat.sub(replace_min, text)

        return text

    @staticmethod
    def normalize_quantifiers(text: str) -> str:
        """
        Chuẩn hóa số đếm tổng quát đi kèm các lượng từ thông dụng:
        '一件' -> '1件', '三人' -> '3人', '五月' -> '5月', '一年' -> '1年', '一番' -> '1番', '一回' -> '1回'.
        """
        counter_pat = re.compile(r'([一二三四五六七八九十百]+)(件|人|月|年|番|回)')
        def replace_counter(m: re.Match) -> str:
            val = kanji_number_to_arabic(m.group(1))
            unit = m.group(2)
            return f"{val}{unit}"
        return counter_pat.sub(replace_counter, text)

    @staticmethod
    def normalize_mixed_numbers(text: str) -> str:
        """
        Chuẩn hóa số hỗn hợp Kanji-Arabic thường xuất hiện trong ASR nhật.
        Ví dụ:
          '10月19日' -> '10月19日' (giữ nguyên — đã là dạng chuẩn)
          '１０月１９日' -> '10月19日' (full-width -> half-width)
          '一月十九日' -> '1月19日'
        """
        # 1. Full-width digit -> half-width digit (general normalization)
        text = text.translate(str.maketrans(
            '０１２３４５６７８９',
            '0123456789'
        ))
        # 2. Kanji standalone decade + unit 月/日/年/号/番/回/件/人
        #    e.g. '一月' -> '1月', '十九日' -> '19日', '二〇二四年' -> '2024年'
        compound_pat = re.compile(r'([〇一二三四五六七八九十百千]+)(月|日|年|号|番|回|件|人|階|本|台|枚|冊|個|袋)')
        def replace_compound(m: re.Match) -> str:
            try:
                val = kanji_number_to_arabic(m.group(1))
                return f"{val}{m.group(2)}"
            except Exception:
                return m.group(0)
        text = compound_pat.sub(replace_compound, text)
        return text

    @classmethod
    def normalize(cls, text: str) -> str:
        """Chuẩn hóa số tổng quát trong transcript."""
        if not text:
            return ""

        # 0. Full-width and mixed Kanji-Arabic numbers
        text = cls.normalize_mixed_numbers(text)

        # 1. Chuẩn hóa ngày tháng, giờ giấc tổng quát
        text = cls.normalize_time_and_dates(text)

        # 2. Chuẩn hóa các lượng từ đếm tổng quát
        text = cls.normalize_quantifiers(text)

        # 3. Chuẩn hóa chuỗi số đọc rời tổng quát
        text = cls.normalize_phone_digit_sequences(text)

        return text

