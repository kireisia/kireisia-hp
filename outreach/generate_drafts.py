#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
営業メッセージ文面生成スクリプト（ホテル・介護事業者向け）

leads.csv の status=researched 行を対象に、業種別テンプレート（templates/*.md）
を使って件名・本文を生成し、drafts/ にテキストファイルとして出力する。
処理した行は status=drafted に更新する。

ここでは何も送信しない。出力されたテキストを見て、人（または依頼を受けた
ClaudeのGmail連携）がGmail下書きを作成し、最終的な送信は必ず人が行う。

外部ライブラリは使わず、標準ライブラリのみで動作する（build_blog.py と同じ方針）。

使い方:
    python3 generate_drafts.py
"""

import csv
import os
import re
import sys
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LEADS_CSV = os.path.join(BASE_DIR, "leads.csv")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
DRAFTS_DIR = os.path.join(BASE_DIR, "drafts")

# 文面の差出人名（必要に応じて書き換える）
SENDER_NAME = "営業担当"

CATEGORY_TEMPLATES = {
    "hotel": "hotel.md",
    "nursing_care": "nursing_care.md",
}

TEMPLATE_RE = re.compile(r"^SUBJECT:\s*(?P<subject>.+?)\n-{3,}\n(?P<body>.*)$", re.S)

FIELDNAMES = [
    "id", "category", "company_name", "prefecture", "city",
    "contact_email", "contact_page_url", "source_url", "status",
    "notes", "date_added", "date_contacted",
]


def load_leads():
    with open(LEADS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def save_leads(rows):
    with open(LEADS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def load_template(category):
    filename = CATEGORY_TEMPLATES.get(category)
    if filename is None:
        return None
    path = os.path.join(TEMPLATES_DIR, filename)
    with open(path, encoding="utf-8") as f:
        return f.read()


def render(template_text, row):
    rendered = template_text.replace("{{company_name}}", row["company_name"].strip())
    rendered = rendered.replace("{{sender_name}}", SENDER_NAME)
    return rendered


def sanitize_filename(text):
    text = re.sub(r"[^\w一-龥ぁ-んァ-ヶー]+", "_", text, flags=re.UNICODE)
    return text.strip("_") or "lead"


def main():
    if not os.path.exists(LEADS_CSV):
        print(f"leads.csv が見つかりません: {LEADS_CSV}", file=sys.stderr)
        return 1

    os.makedirs(DRAFTS_DIR, exist_ok=True)
    rows = load_leads()

    generated = 0
    skipped = 0

    for row in rows:
        if row.get("status") != "researched":
            continue

        company_name = (row.get("company_name") or "").strip()
        contact_email = (row.get("contact_email") or "").strip()
        contact_page_url = (row.get("contact_page_url") or "").strip()

        if not company_name:
            print(f"[スキップ] id={row.get('id')}: company_name が空です")
            skipped += 1
            continue

        if not contact_email and not contact_page_url:
            print(f"[スキップ] id={row.get('id')} {company_name}: "
                  f"contact_email も contact_page_url も空です")
            skipped += 1
            continue

        template_text = load_template(row.get("category"))
        if template_text is None:
            print(f"[スキップ] id={row.get('id')} {company_name}: "
                  f"未対応の category '{row.get('category')}'")
            skipped += 1
            continue

        rendered = render(template_text, row)
        match = TEMPLATE_RE.match(rendered)
        if not match:
            print(f"[スキップ] id={row.get('id')} {company_name}: "
                  f"テンプレート形式が不正です（SUBJECT: / --- が見つかりません）")
            skipped += 1
            continue

        subject = match.group("subject").strip()
        body = match.group("body").strip()
        destination = contact_email or f"(フォーム) {contact_page_url}"

        out_name = f"{row.get('id')}_{sanitize_filename(company_name)}.txt"
        out_path = os.path.join(DRAFTS_DIR, out_name)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"宛先: {destination}\n")
            f.write(f"出典: {row.get('source_url', '')}\n")
            f.write(f"件名: {subject}\n\n")
            f.write(body + "\n")

        row["status"] = "drafted"
        generated += 1
        print(f"[生成] {out_name}")

    if generated:
        save_leads(rows)

    print(f"\n完了: {generated}件生成 / {skipped}件スキップ")
    print("内容を確認のうえ、Gmail下書きの作成・送信は人が行ってください。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
