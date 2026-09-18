# -*- coding: utf-8 -*-
"""Unit tests for JapaneseITNService (chỉ kiểm tra chuẩn hóa số tổng quát, không hardcode từ vựng)."""

import pytest
from app.voice2text.services.japanese_itn_service import JapaneseITNService, kanji_number_to_arabic


def test_kanji_number_to_arabic():
    assert kanji_number_to_arabic("十四") == 14
    assert kanji_number_to_arabic("二十一") == 21
    assert kanji_number_to_arabic("十") == 10
    assert kanji_number_to_arabic("九") == 9
    assert kanji_number_to_arabic("百二十") == 120


def test_phone_digit_normalization():
    raw = "ゼロ五ゼロゼロ五ゼロはい一七八二一七八二はい一八八ゼロ一八八ゼロですね"
    norm = JapaneseITNService.normalize_phone_digit_sequences(raw)
    assert norm == "050050はい17821782はい18801880ですね"


def test_date_and_time_normalization():
    raw = "十四日の水曜日の十時からでお願いいたします"
    norm = JapaneseITNService.normalize_time_and_dates(raw)
    assert norm == "14日の水曜日の10時からでお願いいたします"

    raw2 = "平日朝九時から二十一時まで"
    norm2 = JapaneseITNService.normalize_time_and_dates(raw2)
    assert norm2 == "平日朝9時から21時まで"


def test_quantifier_normalization():
    raw = "一件の問い合わせで三人の方から五月の一年間に一回ありました一番です"
    norm = JapaneseITNService.normalize_quantifiers(raw)
    assert norm == "1件の問い合わせで3人の方から5月の1年間に1回ありました1番です"


def test_full_normalize():
    raw = "ゼロ五ゼロはい十四日の十時です一件あります"
    norm = JapaneseITNService.normalize(raw)
    assert "050" in norm
    assert "14日" in norm
    assert "10時" in norm
    assert "1件" in norm
