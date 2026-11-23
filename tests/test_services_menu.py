"""
追加サービスの左メニュー自動生成（deploy_hp/build_services_menu.py）のテスト
作成: 2026-11-11
"""

import json
import os
import sys

import pytest

DEPLOY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.abspath(DEPLOY_DIR))

import build_services_menu as menu  # noqa: E402

yaml = pytest.importorskip("yaml")


def write(folder, name, data):
    with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
        f.write(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False))


def sample_yml():
    return "\n".join(
        [
            "content:",
            "  - name: g",
            "    label: グループ",
            "    type: group",
            "    items:",
            "          - name: modal_ousama",
            "            label: 空気の王様",
            "            type: file",
            "            path: content/modals/ousama.json",
            "            fields:",
            "              - {name: title, label: 見出し, type: string}",
            "",
            menu.MARK_START,
            "          - name: old",
            menu.MARK_END,
            "",
            "  - name: after",
            "    label: 後ろ",
            "    type: file",
            "    path: x.json",
            "    fields: []",
            "",
        ]
    )


def menu_items(yml_text):
    config = yaml.safe_load(yml_text)
    return config["content"][0]["items"]


# ---- load_services ----


def test_表示順_ファイル名の順に並ぶ(tmp_path):
    write(tmp_path, "b.json", {"title": "B", "card": {"order": 20}})
    write(tmp_path, "a.json", {"title": "A", "card": {"order": 15}})
    write(tmp_path, "c.json", {"title": "C"})
    write(tmp_path, "d.json", {"title": "D", "card": {"order": 15}})
    assert [s["title"] for s in menu.load_services(str(tmp_path))] == [
        "A",
        "D",
        "B",
        "C",
    ]


def test_壊れたファイルとjson以外は飛ばす(tmp_path):
    write(tmp_path, "a.json", {"title": "A"})
    write(tmp_path, "broken.json", "{ 壊れ")
    write(tmp_path, "list.json", [1, 2])
    write(tmp_path, "memo.txt", "x")
    assert [s["file"] for s in menu.load_services(str(tmp_path))] == ["a.json"]


def test_フォルダが無ければ0件(tmp_path):
    assert menu.load_services(str(tmp_path / "none")) == []


def test_真偽値は表示順として扱わない(tmp_path):
    write(tmp_path, "a.json", {"title": "A", "card": {"order": True}})
    assert menu.load_services(str(tmp_path))[0]["order"] is None


# ---- build_block / replace_block ----


def test_空気の王様の下_追加サービスの上に1件1行で並ぶ(tmp_path):
    services = [
        {"file": "service-1.json", "title": "窓掃除", "order": 14},
        {"file": "service-2.json", "title": "換気扇", "order": None},
    ]
    new = menu.replace_block(sample_yml(), menu.build_block(services))
    labels = [i["label"] for i in menu_items(new)]
    assert labels[0] == "空気の王様"
    assert labels[1:3] == ["窓掃除", "換気扇"]
    assert labels[3] == "＋ サービスを追加"
    item = menu_items(new)[1]
    assert item["path"] == "content/extra-services/service-1.json"
    # 2026-11-22 仕様変更：一番上に公開スイッチ→カード枠（サービス名はこの中）→詳細画面の枠
    assert [f["name"] for f in item["fields"]] == ["published", "card", "detail"]


def test_0件なら追加サービスだけ():
    new = menu.replace_block(sample_yml(), menu.build_block([]))
    assert [i["name"] for i in menu_items(new)] == ["modal_ousama", "extra_services"]


def test_印の外は1文字も変えない():
    old = sample_yml()
    new = menu.replace_block(old, menu.build_block([]))
    assert old.split(menu.MARK_START)[0] == new.split(menu.MARK_START)[0]
    assert old.split(menu.MARK_END)[1] == new.split(menu.MARK_END)[1]


def test_記号入りの名前でも設定が壊れない():
    title = '窓掃除: "特価", #1 {A}\n2行目'
    new = menu.replace_block(
        sample_yml(), menu.build_block([{"file": "s.json", "title": title, "order": 1}])
    )
    menu.validate_yaml(new)
    assert menu_items(new)[1]["label"] == title


def test_名前が空なら未入力と出す():
    new = menu.replace_block(
        sample_yml(), menu.build_block([{"file": "s.json", "title": "", "order": None}])
    )
    assert menu_items(new)[1]["label"] == "（サービス名が未入力）"


def test_内部名は半角英数字だけ():
    assert menu.menu_name("service-2026 11日.json") == "extra_service_2026_11_"


def test_印が無ければ止まる():
    with pytest.raises(ValueError):
        menu.replace_block("content: []\n", menu.build_block([]))


def test_印が2組あれば止まる():
    doubled = sample_yml() + menu.MARK_START + "\n" + menu.MARK_END + "\n"
    with pytest.raises(ValueError):
        menu.replace_block(doubled, menu.build_block([]))


def test_書き換え後に追加サービスが無ければ止まる():
    with pytest.raises(ValueError):
        menu.validate_yaml("content:\n  - name: a\n    type: file\n")


def test_設定に同じ内部名が2つあれば止まる():
    # 番号を足す仕組みをすり抜けた時の最後の守り（手で書き足した設定と重なった場合など）
    doubled = "content:\n  - name: extra_services\n    type: collection\n  - name: extra_services\n    type: file\n"
    with pytest.raises(ValueError):
        menu.validate_yaml(doubled)


# ---- 本物の設定ファイル ----


def test_本物の設定は今の追加サービスの件数どおり():
    with open(menu.PAGES_YML_PATH, encoding="utf-8") as f:
        text = f.read()
    menu.validate_yaml(text)
    services = menu.load_services(menu.SERVICES_DIR)
    assert (
        menu.replace_block(text, menu.build_block(services)) == text
    )  # 生成済みの状態と一致
    with open(menu.INDEX_PATH, encoding="utf-8") as f:
        assert json.load(f) == [s["file"] for s in services]


def test_使えない文字のファイル名は飛ばす(tmp_path):
    write(tmp_path, "service ok #1.json", {"title": "空白入り"})
    write(tmp_path, "サービス.json", {"title": "日本語名"})
    write(tmp_path, "service-1.json", {"title": "正常"})
    assert [s["file"] for s in menu.load_services(str(tmp_path))] == ["service-1.json"]


def test_制御文字はタイトルから取り除く(tmp_path):
    write(tmp_path, "a.json", {"title": "窓\x7f掃除\x01"})
    services = menu.load_services(str(tmp_path))
    assert services[0]["title"] == "窓掃除"
    menu.validate_yaml(menu.replace_block(sample_yml(), menu.build_block(services)))


def test_内部名が重なっても番号を足して止まらない():
    services = [{"file": "a-b.json", "title": "A", "order": 1}, {"file": "a_b.json", "title": "B", "order": 2}]
    new = menu.replace_block(sample_yml(), menu.build_block(services))
    menu.validate_yaml(new)
    assert [i["name"] for i in menu_items(new)][1:3] == ["extra_a_b", "extra_a_b_2"]
    assert menu_items(new)[2]["path"] == "content/extra-services/a_b.json"


def test_追加サービスの入力欄は共通の型():
    new = menu.replace_block(sample_yml(), menu.build_block([]))
    # 2026-11-22 RIKIYA依頼：「カード（一覧の枠）」と「詳細画面」の2つの枠に分ける（編集のしやすさ優先）
    top = menu_items(new)[-1]["fields"]
    assert [f["name"] for f in top] == ["published", "card", "detail"]
    top_by_name = {f["name"]: f for f in top}
    assert top_by_name["card"]["type"] == "object" and top_by_name["detail"]["type"] == "object"
    assert "カード" in top_by_name["card"]["label"] and "詳細画面" in top_by_name["detail"]["label"]
    fields = [f["name"] for f in top_by_name["detail"]["fields"]]
    assert fields == [
        "concerns_title", "concerns_list", "concerns_outro",
        "detail_lead",  # 実際の画面と同じ順（お悩みリストの次に紹介文）
        "detail_price_title", "detail_price_note", "detail_price_list",
        "options_title", "options_list",
        "points_title", "points_intro", "points_list",
        "before_after_title", "before_after_slides",
        "customer_request_title", "customer_request_list",
        "booking_notes_title", "booking_notes_list",
        "faq_title", "faq_list",
        "cancellation_title", "cancellation_list", "cancellation_note",
        "detail_notes",
        "custom_sections",
    ]
    by_name = {f["name"]: f for f in top_by_name["detail"]["fields"]}
    by_name["card"] = top_by_name["card"]
    for name in ["detail_price_list", "options_list", "faq_list", "before_after_slides", "cancellation_list", "custom_sections"]:
        assert by_name[name]["list"]["collapsible"]["collapsed"] is True
    # カード枠は既存サービスと同じ並び（画像→サービス名→説明文→価格→表示順）＋最後に左上の札
    assert [f["name"] for f in by_name["card"]["fields"]] == ["image", "title", "description", "price", "order", "badge"]
    card_labels = {f["name"]: f["label"] for f in by_name["card"]["fields"]}
    assert card_labels["title"].startswith("サービス名")
    assert "人気No.1" in card_labels["badge"] and "サービス名" not in card_labels["badge"]
    # 詳細画面の項目名は実際の表示と同じ言葉（価格表・よくあるご質問）
    assert "価格表 見出し" in by_name["detail_price_title"]["label"] and "「価格表」" in by_name["detail_price_title"]["label"]
    assert "「よくあるご質問」" in by_name["faq_title"]["label"]
    assert "料金表" not in new.split(menu.MARK_START)[1]
    # 一覧画面ではカード枠の中のサービス名を見出しにする
    collection = menu_items(new)[-1]
    assert collection["view"]["primary"] == "card.title"
    # 一番下は「＋ 項目追加」（項目名と記述）
    assert "項目追加" in by_name["custom_sections"]["label"]
    assert [f["name"] for f in by_name["custom_sections"]["fields"]] == ["heading", "body"]
    assert by_name["custom_sections"]["fields"][1]["type"] == "text"
    # キャンセル料金の色は既存サービスと同じ3色から選ぶ
    color = by_name["cancellation_list"]["fields"][2]
    assert color["type"] == "select" and color["options"]["values"] == ["main", "warm", "red"]


def test_サービス名はカード枠の中を読み_古い置き場も読む(tmp_path):
    write(tmp_path, "a.json", {"card": {"title": "新しい置き場", "order": 1}})
    write(tmp_path, "b.json", {"title": "古い置き場", "card": {"order": 2}})
    write(tmp_path, "c.json", {"title": "古い", "card": {"title": "新しい", "order": 3}})
    assert [s["title"] for s in menu.load_services(str(tmp_path))] == ["新しい置き場", "古い置き場", "新しい"]


def test_詳細画面の欄は実際の画面の上からの順に番号が付いている():
    new = menu.replace_block(sample_yml(), menu.build_block([]))
    detail = {f["name"]: f for f in menu_items(new)[-1]["fields"]}["detail"]
    numbers = {
        "concerns_title": 1, "concerns_list": 1, "concerns_outro": 1, "detail_lead": 2,
        "detail_price_title": 3, "detail_price_note": 3, "detail_price_list": 3,
        "options_title": 4, "options_list": 4,
        "points_title": 5, "points_intro": 5, "points_list": 5,
        "before_after_title": 6, "before_after_slides": 6,
        "customer_request_title": 7, "customer_request_list": 7,
        "booking_notes_title": 8, "booking_notes_list": 8,
        "faq_title": 9, "faq_list": 9,
        "cancellation_title": 10, "cancellation_list": 10, "cancellation_note": 10,
        "detail_notes": 11, "custom_sections": 12,
    }
    assert {f["name"] for f in detail["fields"]} == set(numbers)
    for field in detail["fields"]:
        assert field["label"].startswith(f"【{numbers[field['name']]}】"), field["label"]
    assert "【1】〜【12】" in detail["label"]
