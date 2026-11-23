"""
サービス一覧の「並び順」と「追加サービス」の計算部分のテスト。
対象: deploy_hp/js/services-order.js の sortKeys / normalizeExtras（Node で実行）
     ＋ content/services.json と .pages.yml の整合
作成: 2026-11-11
"""

import json
import os
import shutil
import subprocess

import pytest

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
JS_PATH = os.path.abspath(os.path.join(BASE, "js", "services-order.js"))
SERVICES_JSON = os.path.join(BASE, "content", "services.json")
PAGES_YML = os.path.join(BASE, ".pages.yml")

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node が必要")


def call(func, arg):
    script = (
        "const m=require(process.argv[1]);"
        "const arg=JSON.parse(process.argv[3]);"
        "process.stdout.write(JSON.stringify(m[process.argv[2]](arg)));"
    )
    out = subprocess.run(
        ["node", "-e", script, JS_PATH, func, json.dumps(arg, ensure_ascii=False)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout)


# ---- sortKeys（並び順） ----


def test_数字の小さい順に並ぶ():
    entries = [
        {"key": "a", "order": 30},
        {"key": "b", "order": 10},
        {"key": "c", "order": 20},
    ]
    assert call("sortKeys", entries) == ["b", "c", "a"]


def test_数字が無ければ今の並びのまま():
    entries = [{"key": "a"}, {"key": "b", "order": None}, {"key": "c", "order": ""}]
    assert call("sortKeys", entries) == ["a", "b", "c"]


def test_数字なしは数字ありの後ろに回る():
    entries = [{"key": "a"}, {"key": "b", "order": 5}, {"key": "c"}]
    assert call("sortKeys", entries) == ["b", "a", "c"]


def test_同じ数字は今の並び順で並ぶ():
    entries = [
        {"key": "a", "order": 10},
        {"key": "b", "order": 10},
        {"key": "c", "order": 1},
    ]
    assert call("sortKeys", entries) == ["c", "a", "b"]


def test_数字の文字列や小数マイナスも扱える():
    entries = [
        {"key": "a", "order": "20"},
        {"key": "b", "order": -1},
        {"key": "c", "order": 15.5},
    ]
    assert call("sortKeys", entries) == ["b", "c", "a"]


def test_空白や真偽値は数字なし扱い():
    entries = [
        {"key": "a", "order": " "},
        {"key": "b", "order": True},
        {"key": "c", "order": 1},
    ]
    assert call("sortKeys", entries) == ["c", "a", "b"]


def test_数字でない文字は数字なし扱い():
    entries = [{"key": "a", "order": "あ"}, {"key": "b", "order": 1}]
    assert call("sortKeys", entries) == ["b", "a"]


def test_空なら空():
    assert call("sortKeys", []) == []


# ---- normalizeExtras（追加サービスの入力整理） ----


def test_空や配列以外は0件():
    assert call("normalizeExtras", None) == []
    assert call("normalizeExtras", {"title": "x"}) == []
    assert call("normalizeExtras", []) == []


def test_タイトルが空の行は出さない():
    result = call(
        "normalizeExtras",
        [{"title": "  "}, {"price": "¥1,000"}, "文字", None, {"title": "窓掃除"}],
    )
    assert [r["title"] for r in result] == ["窓掃除"]
    assert result[0]["key"] == "extra-1"


def test_前後の空白を取り除く():
    result = call("normalizeExtras", [{"title": " 窓掃除 ", "price": " ¥3,000〜 "}])
    assert result[0]["title"] == "窓掃除"
    assert result[0]["price"] == "¥3,000〜"


def test_詳細が空なら詳細ボタンを出さない():
    result = call(
        "normalizeExtras",
        [
            {
                "title": "窓掃除",
                "detail_price_list": [{"name": "", "price": ""}],
                "detail_notes": [" "],
            }
        ],
    )
    assert result[0]["hasDetail"] is False
    assert result[0]["detailPriceList"] == []


def test_料金表に1行あれば詳細ボタンを出す():
    result = call(
        "normalizeExtras",
        [
            {
                "title": "窓掃除",
                "detail_price_list": [{"name": "1枚", "price": "¥1,000"}],
            }
        ],
    )
    assert result[0]["hasDetail"] is True
    assert result[0]["detailPriceList"] == [{"name": "1枚", "price": "¥1,000"}]


def test_危ない画像パスは捨てる():
    result = call(
        "normalizeExtras",
        [
            {"title": "a", "image": "javascript:alert(1)"},
            {"title": "b", "image": "data:image/png;base64,xx"},
            {"title": "c", "image": "/images/x.jpg"},
            {"title": "d", "image": "https://example.com/x.jpg"},
        ],
    )
    assert [r["image"] for r in result] == [
        "",
        "",
        "images/x.jpg",
        "https://example.com/x.jpg",
    ]


def test_表示順の数字を取り出す():
    result = call(
        "normalizeExtras",
        [
            {"title": "a", "order": 25},
            {"title": "b", "order": ""},
            {"title": "c", "order": "abc"},
        ],
    )
    assert [r["order"] for r in result] == [25, None, None]


def test_長い文章も切らずに受け取る():
    long_text = "あ" * 2000
    result = call("normalizeExtras", [{"title": "a", "description": long_text}])
    assert result[0]["description"] == long_text


# ---- mergeCards（各サービスのファイルからカードを集める） ----


def call2(func, a, b):
    script = (
        "const m=require(process.argv[1]);"
        "process.stdout.write(JSON.stringify(m[process.argv[2]](JSON.parse(process.argv[3]),JSON.parse(process.argv[4]))));"
    )
    out = subprocess.run(
        ["node", "-e", script, JS_PATH, func, json.dumps(a, ensure_ascii=False), json.dumps(b, ensure_ascii=False)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def test_各サービスのカードを集める():
    merged = call2("mergeCards", {"ousama": {"order": 13}, "extra": []}, {"aircon": {"card": {"title": "A", "order": 1}}})
    assert merged == {"ousama": {"order": 13}, "extra": [], "aircon": {"title": "A", "order": 1}}


def test_カードが無いファイルは古い置き場を使う():
    merged = call2("mergeCards", {"aircon": {"title": "旧", "order": 1}}, {"aircon": {"title": "詳細だけ"}, "washer": None})
    assert merged["aircon"] == {"title": "旧", "order": 1}
    assert "washer" not in merged


def test_services_jsonが読めなくても集められる():
    merged = call2("mergeCards", None, {"aircon": {"card": {"title": "A"}}})
    assert merged == {"aircon": {"title": "A"}}


# ---- 本番データとの整合 ----

KEYS = ["aircon", "washer", "water", "sofa", "mattress", "wall", "vacant",
        "aircon_install", "shop", "handyman", "drain", "housekeeping", "ousama"]
CARD_FIELDS = ["image", "title", "description", "price", "order"]


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_13サービスのファイルにカードがあり番号は1から13():
    for i, key in enumerate(KEYS, start=1):
        card = load_json(os.path.join(BASE, "content", "modals", key + ".json"))["card"]
        assert list(card) == CARD_FIELDS, key
        assert card["order"] == i, key
        assert card["title"] and card["image"].startswith("images/") and card["price"], key


def test_追加サービスは1件1ファイル_一覧ファイルがある():
    assert not os.path.exists(SERVICES_JSON)  # 古い置き場は廃止
    index = load_json(os.path.join(BASE, "content", "extra-services-index.json"))
    assert isinstance(index, list)
    for name in index:
        assert os.path.exists(os.path.join(BASE, "content", "extra-services", name))


def test_本番データは今の並び順のまま():
    entries = [{"key": k, "order": load_json(os.path.join(BASE, "content", "modals", k + ".json"))["card"]["order"]} for k in KEYS]
    assert call("sortKeys", entries) == KEYS


def load_service_group():
    yaml = pytest.importorskip("yaml")
    with open(PAGES_YML, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    page = next(c for c in config["content"] if c["name"] == "page_service")
    return next(i for i in page["items"] if i["name"] == "service_details")


def walk_fields(fields):
    for field in fields:
        yield field
        if "fields" in field:
            yield from walk_fields(field["fields"])


def test_編集画面は1サービス1画面で一番上にカード枠():
    group = load_service_group()
    files = {item["path"]: item for item in group["items"]}
    for key in KEYS:
        item = files["content/modals/" + key + ".json"]
        assert not item["label"].startswith("詳細："), key
        card = item["fields"][0]
        assert card["name"] == "card" and card["type"] == "object", key
        assert [f["name"] for f in card["fields"]] == CARD_FIELDS, key
    # 追加サービス（新規作成）は同じまとまりの一番最後
    assert group["items"][-1]["name"] == "extra_services"
    assert group["items"][-1]["type"] == "collection"


def test_行を足せる枠は全部折りたたみ_モーダルという言葉は出さない():
    group = load_service_group()
    for item in group["items"]:
        for field in walk_fields(item["fields"]):
            # 1行形式のカンマでラベルが切れると、余計なキーが増える
            assert set(field) <= {"name", "label", "type", "list", "fields", "options", "default"}, field
            assert "モーダル" not in field.get("label", ""), field
            if field.get("type") == "object" and field.get("list"):
                collapsible = field["list"]["collapsible"]
                assert collapsible["collapsed"] is True and "{index}" in collapsible["summary"], field["name"]


def test_追加サービス欄のラベルが切れていない():
    group = load_service_group()
    extra_item = group["items"][-1]
    card = {f["name"]: f for f in extra_item["fields"]}["card"]
    labels = {f["name"]: f["label"] for f in card["fields"]}
    assert labels["price"].endswith("「お見積り」）")


def test_空気の王様の詳細はHTMLの文字と同じ値で始まる():
    # 値がHTMLと同じなら、太字などのHTMLの飾りはそのまま残る
    data = load_json(os.path.join(BASE, "content", "modals", "ousama.json"))
    with open(os.path.join(BASE, "service.html"), encoding="utf-8") as f:
        html = f.read()
    fields = [k for k in data if k != "card"]
    assert len(fields) == 25
    for key in fields:
        assert 'data-cms-field="modal_ousama.' + key + '"' in html, key
    for key in ["image", "title", "description", "price"]:
        assert 'data-cms-field="services.ousama.' + key + '"' in html, key


def test_追加サービスのファイルをカードの形に直す():
    data = {"title": "窓掃除", "published": True, "card": {"image": "images/a.jpg", "price": "¥1", "order": 14, "badge": "NEW"},
            "detail_price_list": [{"name": "1枚", "price": "¥1"}]}
    item = call("fromExtraFile", data)
    assert item["title"] == "窓掃除" and item["order"] == 14 and item["badge"] == "NEW"
    assert call("normalizeExtras", [item])[0]["hasDetail"] is True


def test_下書きはページに出さない():
    assert call("fromExtraFile", {"title": "窓掃除", "published": False}) is None
    assert call("fromExtraFile", None) is None
    # 公開スイッチが無い古いファイルは表示する
    assert call("fromExtraFile", {"title": "窓掃除"})["title"] == "窓掃除"


# ---- 追加サービスの詳細（共通の型：お悩み・料金表・オプション・ポイント・FAQ・注意書き） ----


def test_共通の型の欄をすべて受け取る():
    data = {
        "title": "窓掃除",
        "card": {"order": 14},
        "detail_lead": "紹介",
        "concerns_title": "こんなお悩み",
        "concerns_list": ["くもる", " ", "カビ"],
        "detail_price_title": "料金",
        "detail_price_list": [{"name": "腰窓", "price": "¥3,000"}],
        "options_title": "オプション",
        "options_list": [{"name": "網戸", "price": "+¥1,000"}, {"name": "", "price": ""}],
        "points_title": "ポイント",
        "points_list": ["プロの道具"],
        "faq_title": "よくある質問",
        "faq_list": [{"question": "時間は？", "answer": "1時間"}, {"question": "", "answer": "答えだけ"}],
        "detail_notes": ["注意"],
    }
    item = call("normalizeExtras", [call("fromExtraFile", data)])[0]
    assert item["concernsTitle"] == "こんなお悩み"
    assert item["concernsList"] == ["くもる", "カビ"]
    assert item["optionsList"] == [{"name": "網戸", "price": "+¥1,000"}]
    assert item["pointsList"] == ["プロの道具"]
    assert item["faqList"] == [{"question": "時間は？", "answer": "1時間"}]
    assert item["hasDetail"] is True


def test_お悩みだけでも詳細ボタンを出す():
    item = call("normalizeExtras", [{"title": "a", "concerns_list": ["くもる"]}])[0]
    assert item["hasDetail"] is True


def test_見出しだけで中身が空なら詳細ボタンを出さない():
    item = call("normalizeExtras", [{"title": "a", "concerns_title": "お悩み", "faq_title": "FAQ", "options_title": "OP"}])[0]
    assert item["hasDetail"] is False


# ---- 追加サービスに既存サービスと同じ6つの欄＋自由な項目（2026-11-22 RIKIYA依頼） ----


def test_既存サービスと同じ6つの欄を受け取る():
    data = {
        "title": "ビル清掃",
        "concerns_list": ["汚れ"],
        "concerns_outro": "プロにお任せください",
        "points_title": "ポイント",
        "points_intro": "プロの技でスッキリ！",
        "points_list": ["外注なし"],
        "before_after_title": "Before / After",
        "before_after_slides": [
            {"caption": "床", "before_image": "images/a.jpg", "before_alt": "前", "after_image": "images/b.jpg", "after_alt": "後"},
            {"caption": "画像なし", "before_image": "", "after_image": ""},
            {"caption": "危ない", "before_image": "javascript:alert(1)", "after_image": "data:x"},
        ],
        "customer_request_title": "お客様へお願い",
        "customer_request_list": ["電気をお借りします", ""],
        "booking_notes_title": "ご予約に関する注意事項",
        "booking_notes_list": ["3日前までに"],
        "cancellation_title": "キャンセル料金",
        "cancellation_list": [
            {"period": "5日前まで", "rate": "0%", "color": "main"},
            {"period": "当日", "rate": "100%", "color": "red"},
            {"period": "前日", "rate": "50%", "color": "purple"},
            {"period": "", "rate": ""},
        ],
        "cancellation_note": "※48時間以内は無料",
    }
    item = call("normalizeExtras", [call("fromExtraFile", data)])[0]
    assert item["concernsOutro"] == "プロにお任せください"
    assert item["pointsIntro"] == "プロの技でスッキリ！"
    assert item["beforeAfterTitle"] == "Before / After"
    assert item["beforeAfterSlides"] == [
        {"caption": "床", "beforeImage": "images/a.jpg", "beforeAlt": "前", "afterImage": "images/b.jpg", "afterAlt": "後"}
    ]
    assert item["customerRequestTitle"] == "お客様へお願い"
    assert item["customerRequestList"] == ["電気をお借りします"]
    assert item["bookingNotesTitle"] == "ご予約に関する注意事項"
    assert item["bookingNotesList"] == ["3日前までに"]
    assert item["cancellationTitle"] == "キャンセル料金"
    # 色は main / warm / red だけ。それ以外は main に戻す
    assert item["cancellationList"] == [
        {"period": "5日前まで", "rate": "0%", "color": "main"},
        {"period": "当日", "rate": "100%", "color": "red"},
        {"period": "前日", "rate": "50%", "color": "main"},
    ]
    assert item["cancellationNote"] == "※48時間以内は無料"


def test_自由な項目は項目名か記述のどちらかがあれば出す():
    data = {
        "title": "a",
        "custom_sections": [
            {"heading": "作業時間", "body": "約2時間\n広さで変わります"},
            {"heading": "", "body": "記述だけ"},
            {"heading": "見出しだけ", "body": ""},
            {"heading": " ", "body": " "},
            "壊れた行",
        ],
    }
    item = call("normalizeExtras", [call("fromExtraFile", data)])[0]
    assert item["customSections"] == [
        {"heading": "作業時間", "body": "約2時間\n広さで変わります"},
        {"heading": "", "body": "記述だけ"},
        {"heading": "見出しだけ", "body": ""},
    ]
    assert item["hasDetail"] is True


@pytest.mark.parametrize(
    "field, value",
    [
        ("before_after_slides", [{"caption": "x", "after_image": "images/b.jpg"}]),
        ("customer_request_list", ["お願い"]),
        ("booking_notes_list", ["注意"]),
        ("cancellation_list", [{"period": "当日", "rate": "100%"}]),
        ("custom_sections", [{"heading": "h", "body": "b"}]),
    ],
)
def test_新しい欄だけでも詳細ボタンを出す(field, value):
    item = call("normalizeExtras", [{"title": "a", field: value}])[0]
    assert item["hasDetail"] is True


def test_締めの一文やリード文だけでは詳細ボタンを出さない():
    item = call("normalizeExtras", [{
        "title": "a", "concerns_outro": "x", "points_intro": "y", "cancellation_note": "z",
        "before_after_title": "BA", "customer_request_title": "お願い", "booking_notes_title": "注意", "cancellation_title": "キャンセル",
    }])[0]
    assert item["hasDetail"] is False


def test_今のビルメンテナンスのデータもそのまま読める():
    path = os.path.join(BASE, "content", "extra-services", "service-20261113-154419.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    item = call("normalizeExtras", [call("fromExtraFile", data)])[0]
    assert item["title"] == "ビルメンテナンス"
    assert data["card"]["title"] == "ビルメンテナンス"  # カード枠の中へ移した
    assert len(data["detail"]["detail_price_list"]) == 3  # 詳細画面の枠の中へ移した
    assert len(item["detailPriceList"]) == 3
    assert item["beforeAfterSlides"] == [] and item["customSections"] == []
    assert item["hasDetail"] is True


# ---- サービス名をカード枠の中へ（2026-11-22 RIKIYA依頼：既存サービスと並びを揃える） ----


def test_サービス名はカード枠の中から読む():
    item = call("fromExtraFile", {"card": {"title": "窓掃除"}})
    assert item["title"] == "窓掃除"


def test_古い置き場のサービス名も読める():
    assert call("fromExtraFile", {"title": "旧", "card": {}})["title"] == "旧"
    assert call("fromExtraFile", {"title": "旧", "card": {"title": "新"}})["title"] == "新"
    assert call("fromExtraFile", {"title": "旧", "card": {"title": "  "}})["title"] == "旧"


# ---- 編集画面を「カード」と「詳細画面」の2つの枠に分ける（2026-11-22 RIKIYA依頼） ----


def test_詳細画面の枠の中から読む():
    data = {"card": {"title": "窓"}, "detail": {"detail_lead": "紹介", "custom_sections": [{"heading": "h", "body": "b"}],
                                              "cancellation_list": [{"period": "当日", "rate": "100%", "color": "red"}]}}
    item = call("normalizeExtras", [call("fromExtraFile", data)])[0]
    assert item["detailLead"] == "紹介"
    assert item["customSections"] == [{"heading": "h", "body": "b"}]
    assert item["cancellationList"][0]["color"] == "red"


def test_詳細画面の枠が無い古い形も読める():
    item = call("normalizeExtras", [call("fromExtraFile", {"card": {"title": "窓"}, "detail_lead": "古い紹介"})])[0]
    assert item["detailLead"] == "古い紹介"
    assert item["hasDetail"] is True


def test_詳細画面の枠を優先し_無い欄だけ古い置き場を読む():
    data = {"card": {"title": "窓"}, "detail_lead": "古い", "points_list": ["古いポイント"], "detail": {"detail_lead": "新しい"}}
    item = call("normalizeExtras", [call("fromExtraFile", data)])[0]
    assert item["detailLead"] == "新しい"
    assert item["pointsList"] == ["古いポイント"]
