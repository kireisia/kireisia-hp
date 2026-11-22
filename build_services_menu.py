"""
追加サービスの「編集画面の左メニュー」と「一覧ファイル」を自動で作り直すスクリプト
作成: 2026-11-11

何をするか:
  content/extra-services/*.json（編集画面で追加したサービス 1件=1ファイル）を読み、
  1. .pages.yml の印（▼自動生成〜▲自動生成）の間を書き換える
     → 左メニューの「空気の王様」の下・「追加サービス」の上に 1件1行で並ぶ
  2. content/extra-services-index.json（ページが読むファイル名の一覧）を書き直す

安全装置:
  - 書き換えるのは印の間だけ。印が無い・壊れている時は何も書かずに止まる
  - 書き換え後の .pages.yml を YAML として読み直し、読めなければ書き込まない
  - 壊れたサービスファイルは飛ばして警告だけ出す（他のサービスは載せる）

GitHub Actions（.github/workflows/build-services-menu.yml）から、
content/extra-services/ が変わるたびに自動で実行される。
"""

import json
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICES_DIR = os.path.join(BASE_DIR, "content", "extra-services")
INDEX_PATH = os.path.join(BASE_DIR, "content", "extra-services-index.json")
PAGES_YML_PATH = os.path.join(BASE_DIR, ".pages.yml")

MARK_START = "          # ▼自動生成：追加サービス（build_services_menu.py が書き換える・この間は手で編集しない）"
MARK_END = "          # ▲自動生成ここまで"

SAFE_FILE_NAME = re.compile(r"^[A-Za-z0-9_.-]+\.json$")
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")

ORDER_LABEL = "表示順（1が一番前・2、3…の順に並びます。入れ替える時は番号を付け替えてください。空なら一番後ろ）"

# 追加サービス1件の入力欄（左メニューの各行と「追加サービス」の新規作成で共通）
FIELDS_YAML = f"""              - {{name: published, label: ページに表示する（オフにするとページに出さない＝下書き）, type: boolean, default: true}}
              - name: card
                label: カード（サービス一覧に並ぶ枠）
                type: object
                fields:
                  - {{name: image, label: カード画像, type: image}}
                  - {{name: title, label: サービス名（カードのタイトル・詳細画面の見出し・必須）※新しく作った時は、保存して1〜2分後に再読み込みすると左メニューに出ます, type: string}}
                  - {{name: description, label: 説明文, type: text}}
                  - {{name: price, label: "価格表示（例：¥5,000〜（税込）・空なら「お見積り」）", type: string}}
                  - {{name: order, label: {ORDER_LABEL}, type: number}}
                  - {{name: badge, label: 画像左上の札（例：NEW・人気No.1。空なら出しません。カード画像がある時だけ表示）, type: string}}
              - name: detail
                label: 詳細画面（カードの「詳細」を押すと開く画面。空の欄は表示されません）
                type: object
                fields:
                  - {{name: detail_lead, label: 紹介文（この枠の欄が全部空なら、カードに「詳細」ボタンは出ません）, type: text}}
                  - {{name: concerns_title, label: お悩みリスト 見出し（空なら「こんなお悩みございませんか？」）, type: string}}
                  - name: concerns_list
                    label: お悩みリスト 項目（1行ずつ）
                    type: string
                    list: true
                  - {{name: concerns_outro, label: お悩みリスト 締めの一文（例：プロのクリーニングでお悩み解決いたします）, type: string}}
                  - {{name: detail_price_title, label: 価格表 見出し（空なら「価格表」）, type: string}}
                  - {{name: detail_price_note, label: 価格表 注記（例：※すべて税込価格です）, type: string}}
                  - name: detail_price_list
                    label: 価格表 項目
                    type: object
                    list:
                      collapsible:
                        collapsed: true
                        summary: "{{index}}. {{fields.name}}"
                    fields:
                      - {{name: name, label: 項目名, type: string}}
                      - {{name: price, label: 料金, type: string}}
                  - {{name: options_title, label: オプション 見出し（空なら「オプション」）, type: string}}
                  - name: options_list
                    label: オプション 項目
                    type: object
                    list:
                      collapsible:
                        collapsed: true
                        summary: "{{index}}. {{fields.name}}"
                    fields:
                      - {{name: name, label: 項目名, type: string}}
                      - {{name: price, label: 料金, type: string}}
                  - {{name: points_title, label: キレイシアのポイント 見出し（空なら「キレイシアのポイント」）, type: string}}
                  - {{name: points_intro, label: キレイシアのポイント リード文（例：プロの技でスッキリ！快適な空間をご提供します！）, type: string}}
                  - name: points_list
                    label: キレイシアのポイント 項目（1行ずつ）
                    type: string
                    list: true
                  - {{name: before_after_title, label: Before/After 見出し（空なら「Before / After」）, type: string}}
                  - name: before_after_slides
                    label: Before/After スライド（追加・削除可）
                    type: object
                    list:
                      collapsible:
                        collapsed: true
                        summary: "{{index}}. {{fields.caption}}"
                    fields:
                      - {{name: caption, label: キャプション, type: string}}
                      - {{name: before_image, label: Before画像, type: image}}
                      - {{name: before_alt, label: Before画像の説明（SEO用）, type: string}}
                      - {{name: after_image, label: After画像, type: image}}
                      - {{name: after_alt, label: After画像の説明（SEO用）, type: string}}
                  - {{name: customer_request_title, label: お客様へお願い 見出し（空なら「お客様へお願い」）, type: string}}
                  - name: customer_request_list
                    label: お客様へお願い 項目（1行ずつ）
                    type: string
                    list: true
                  - {{name: booking_notes_title, label: ご予約に関する注意事項 見出し（空なら「ご予約に関する注意事項」）, type: string}}
                  - name: booking_notes_list
                    label: ご予約に関する注意事項 項目（1行ずつ）
                    type: string
                    list: true
                  - {{name: faq_title, label: よくあるご質問 見出し（空なら「よくあるご質問」）, type: string}}
                  - name: faq_list
                    label: よくあるご質問 項目
                    type: object
                    list:
                      collapsible:
                        collapsed: true
                        summary: "{{index}}. {{fields.question}}"
                    fields:
                      - {{name: question, label: 質問, type: string}}
                      - {{name: answer, label: 回答, type: text}}
                  - {{name: cancellation_title, label: キャンセル料金 見出し（空なら「キャンセル料金」）, type: string}}
                  - name: cancellation_list
                    label: キャンセル料金 項目
                    type: object
                    list:
                      collapsible:
                        collapsed: true
                        summary: "{{index}}. {{fields.period}}"
                    fields:
                      - {{name: period, label: 期間（例：作業日の前日）, type: string}}
                      - {{name: rate, label: 料率（例：50%）, type: string}}
                      - name: color
                        label: 強調色（main＝黒・warm＝オレンジ・red＝赤）
                        type: select
                        options: {{values: [main, warm, red]}}
                  - {{name: cancellation_note, label: キャンセル料金 注記, type: string}}
                  - name: detail_notes
                    label: 注意書き（1行ずつ）
                    type: string
                    list: true
                  - name: custom_sections
                    label: ＋ 項目追加（項目名と記述・詳細画面の一番下に出ます。下の「Add an entry」を押すたびに1つ増えます）
                    type: object
                    list:
                      collapsible:
                        collapsed: true
                        summary: "{{index}}. {{fields.heading}}"
                    fields:
                      - {{name: heading, label: 項目名, type: string}}
                      - {{name: body, label: 記述, type: text}}"""


def clean_title(value):
    """サービス名から制御文字と前後の空白を取り除く（文字でなければ空）"""
    return CONTROL_CHARS.sub("", value).strip() if isinstance(value, str) else ""


def load_services(services_dir):
    # サービス名はカード枠の中（card.title）。2026-11-22 より前の置き場（一番上の title）も読む
    """追加サービスのファイルを読み、表示順→ファイル名の順に並べて返す（壊れたファイルは飛ばす）"""
    services = []
    if not os.path.isdir(services_dir):
        return services
    for file_name in sorted(os.listdir(services_dir)):
        if not file_name.endswith(".json"):
            continue
        if not SAFE_FILE_NAME.match(file_name):
            # ページ側（service.html）も同じ条件で読むので、通らない名前はメニューにも載せない
            print(
                f"[警告] {file_name} は使えない文字を含むため飛ばします（半角英数字・_・.・- だけ）",
                file=sys.stderr,
            )
            continue
        path = os.path.join(services_dir, file_name)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as error:
            print(
                f"[警告] {file_name} を読めないため飛ばします: {error}", file=sys.stderr
            )
            continue
        if not isinstance(data, dict):
            print(
                f"[警告] {file_name} の中身が正しくないため飛ばします", file=sys.stderr
            )
            continue
        card = data.get("card") if isinstance(data.get("card"), dict) else {}
        title = clean_title(card.get("title")) or clean_title(data.get("title"))
        order = card.get("order")
        has_order = isinstance(order, (int, float)) and not isinstance(order, bool)
        services.append(
            {"file": file_name, "title": title, "order": order if has_order else None}
        )
    services.sort(
        key=lambda s: (
            s["order"] is None,
            s["order"] if s["order"] is not None else 0,
            s["file"],
        )
    )
    return services


def menu_name(file_name):
    """ファイル名から、左メニューの内部名（半角英数字と _ だけ）を作る"""
    stem = os.path.splitext(file_name)[0]
    return "extra_" + re.sub(r"[^A-Za-z0-9_]", "_", stem)


def build_block(services):
    """印の間に入れる文字（各サービスの行＋「追加サービス」の新規作成）を作る"""
    lines = [MARK_START]
    used_names = set()
    for service in services:
        name = menu_name(service["file"])
        while name in used_names:  # a-b.json と a_b.json のように重なったら番号を足す
            name += "_2"
        used_names.add(name)
        label = service["title"] or "（サービス名が未入力）"
        lines += [
            f"          - name: {name}",
            f"            label: {json.dumps(label, ensure_ascii=False)}",
            "            type: file",
            f"            path: {json.dumps('content/extra-services/' + service['file'])}",
            "            format: json",
            "            fields:",
            FIELDS_YAML,
            "",
        ]
    lines += [
        "          - name: extra_services",
        "            label: ＋ サービスを追加",
        "            type: collection",
        "            path: content/extra-services",
        "            format: json",
        "            filename: 'service-{year}{month}{day}-{hour}{minute}{second}.json'",
        "            view:",
        "              fields: [card.title, published]",
        "              primary: card.title",
        "            fields:",
        FIELDS_YAML,
        MARK_END,
    ]
    return "\n".join(lines)


def replace_block(yml_text, block):
    """印の間だけを差し替える。印が1組ちょうど無ければ ValueError"""
    if yml_text.count(MARK_START) != 1 or yml_text.count(MARK_END) != 1:
        raise ValueError(
            "[E001] .pages.yml の自動生成の印が見つからないか、2つ以上あります。手で直してください。"
        )
    start = yml_text.index(MARK_START)
    end = yml_text.index(MARK_END) + len(MARK_END)
    if end < start:
        raise ValueError(
            "[E002] .pages.yml の自動生成の印の順番が逆です。手で直してください。"
        )
    return yml_text[:start] + block + yml_text[end:]


def validate_yaml(yml_text):
    """書き換え後の設定が YAML として読めて、追加サービスの新規作成が残っているか確かめる"""
    import yaml  # GitHub Actions では pip で入れる

    config = yaml.safe_load(yml_text)
    names = []

    def walk(items):
        for item in items:
            names.append(item.get("name"))
            if item.get("type") == "group":
                walk(item.get("items", []))

    walk(config["content"])
    if "extra_services" not in names:
        raise ValueError("[E003] 書き換え後の設定に「追加サービス」が見つかりません。")
    if len(names) != len(set(names)):
        raise ValueError("[E004] 書き換え後の設定に同じ内部名が2つ以上あります。")


def main():
    services = load_services(SERVICES_DIR)
    with open(PAGES_YML_PATH, encoding="utf-8") as f:
        old_yml = f.read()
    new_yml = replace_block(old_yml, build_block(services))
    validate_yaml(new_yml)
    if new_yml != old_yml:
        with open(PAGES_YML_PATH, "w", encoding="utf-8") as f:
            f.write(new_yml)
    index = [service["file"] for service in services]
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write(json.dumps(index, ensure_ascii=False, indent=2) + "\n")
    print(f"追加サービス {len(services)} 件で左メニューと一覧を作り直しました。")


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        print(error, file=sys.stderr)
        sys.exit(1)
