#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
キレイシアHP ブログCMS化：ローカル自動ビルドスクリプト

content/blog/*.md（マークダウン＋フロントマター）を読み込み、
published: true の記事だけを対象に、
  ・各記事の個別ページ  blog/<slug>.html
  ・記事一覧ページ       blog.html
を生成する。

外部ライブラリは使わず、Python標準ライブラリのみで動作する（uv環境不要）。
マークダウン→HTML変換も自作（最低限の記法に対応）。

使い方:
    python3 build_blog.py
"""

import html
import os
import re
import shutil
import sys
from datetime import datetime

# ===== 基本設定（全環境共通の固定値なのでコードに直接記述） =====

# このスクリプトが置かれているフォルダ（＝HP制作フォルダ）を基準にする
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 記事マークダウンの置き場
CONTENT_DIR = os.path.join(BASE_DIR, "content", "blog")
# 個別記事HTMLの出力先（サブフォルダ）
BLOG_OUT_DIR = os.path.join(BASE_DIR, "blog")
# 一覧ページの出力先
BLOG_LIST_PATH = os.path.join(BASE_DIR, "blog.html")
# サイトマップ（検索エンジン向けのURL一覧）の出力先
SITEMAP_PATH = os.path.join(BASE_DIR, "sitemap.xml")

# サイトマップに必ず収録する主要ページ
# （ファイル名, changefreq=更新頻度の目安, priority=優先度）
# changefreq・priority は検索エンジンへの「目安」であり、絶対的な意味はない。
MAIN_PAGES = [
    ("index.html", "weekly", "1.0"),  # トップページ
    ("service.html", "monthly", "0.9"),  # サービス一覧
    ("about.html", "monthly", "0.8"),  # 企業理念
    ("company.html", "monthly", "0.8"),  # 会社概要
    ("blog.html", "weekly", "0.8"),  # ブログ一覧
    ("contact.html", "monthly", "0.7"),  # お問い合わせ
    ("privacy.html", "yearly", "0.3"),  # プライバシーポリシー
]
# 既存 blog.html のバックアップ先
BACKUP_DIR = os.path.join(BASE_DIR, "_backup_blog_cms")
BACKUP_PATH = os.path.join(BACKUP_DIR, "blog_before_cms.html")

# 公開サイトのベースURL（canonical・OGP・JSON-LD用）
SITE_BASE = "https://kireisia.github.io"
# OGP用の共通画像（絶対URL）
OGP_IMAGE = SITE_BASE + "/images/ogp.jpg"

# カテゴリのchip配色（施工事例だけ暖色、それ以外は水色テーマ）
CATEGORY_WARM = {"施工事例", "お知らせ"}


# ============================================================
# 1. フロントマター＋本文の読み込み
# ============================================================


def parse_front_matter(text):
    """
    マークダウンファイルの先頭にある `---` で囲まれたフロントマターを解析する。

    戻り値: (メタ情報の辞書, 本文文字列)
    対応する書き方: `キー: 値`（値は文字列としてそのまま保持）
    """
    # ファイルが `---` で始まっていなければフロントマター無しとみなす
    if not text.startswith("---"):
        return {}, text

    # 先頭の `---` 以降を、次の `---` 行までで分割する
    lines = text.splitlines()
    meta = {}
    body_start_index = 0
    closed = False

    # 1行目は `---` なので2行目から探索する
    for i in range(1, len(lines)):
        line = lines[i]
        if line.strip() == "---":
            # フロントマターの終わり
            body_start_index = i + 1
            closed = True
            break
        # `キー: 値` を分解（最初のコロンだけで分ける）
        if ":" in line:
            key, _, value = line.partition(":")
            value = value.strip()
            # YAMLで値が引用符で囲まれている場合は外す（CMSがタイトル等を "..." で出力するため）
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            meta[key.strip()] = value

    # 閉じる `---` が無い場合はフォーマット不正として例外を出す
    if not closed:
        raise ValueError("フロントマターの終わりを示す '---' が見つかりません")

    body = "\n".join(lines[body_start_index:]).strip()
    return meta, body


def load_articles():
    """
    content/blog/*.md を全て読み込み、published: true の記事だけを返す。

    戻り値: 記事辞書のリスト（date降順でソート済み）
    """
    articles = []

    # content/blog フォルダが無ければ親切なエラーを出す
    if not os.path.isdir(CONTENT_DIR):
        raise FileNotFoundError(f"記事フォルダが見つかりません: {CONTENT_DIR}")

    # 拡張子 .md のファイルを名前順に処理（処理順を安定させる＝冪等性のため）
    for file_name in sorted(os.listdir(CONTENT_DIR)):
        if not file_name.endswith(".md"):
            continue

        file_path = os.path.join(CONTENT_DIR, file_name)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_text = f.read()
            meta, body = parse_front_matter(raw_text)
        except Exception as error:
            # 1ファイルの不調で全体を止めないよう、警告だけ出して飛ばす
            print(f"  [警告] {file_name} の読み込みに失敗しました: {error}")
            continue

        # published が true の記事だけを対象にする
        if str(meta.get("published", "")).lower() != "true":
            print(f"  [スキップ] {file_name}（published が true ではありません）")
            continue

        # 必須キーの存在チェック（足りない場合は警告して飛ばす）
        required_keys = [
            "title",
            "slug",
            "type",
            "category",
            "date",
            "description",
            "lead",
        ]
        missing = [k for k in required_keys if not meta.get(k)]
        if missing:
            print(
                f"  [警告] {file_name} に必須キーが不足しています: {', '.join(missing)}"
            )
            continue

        meta["body"] = body
        articles.append(meta)

    # date（YYYY-MM-DD）の降順で並べる。日付が不正な記事は最後に回す
    def sort_key(article):
        try:
            return datetime.strptime(article["date"], "%Y-%m-%d")
        except ValueError:
            return datetime.min

    articles.sort(key=sort_key, reverse=True)
    return articles


# ============================================================
# 2. マークダウン → HTML 変換（標準ライブラリのみ・自作）
#    1関数1仕事で分割する
# ============================================================


def resolve_path(path, root):
    """
    記事内の相対パスを、出力先フォルダに合わせて調整する。

    記事は blog/ サブフォルダに出力されるため、`images/...` や `service.html`
    のような相対パスは `../images/...`・`../service.html` にする必要がある。
    root には記事なら "../"、一覧ページなら "" を渡す。

    外部URL・アンカー・tel/mailto・既に ../ や / で始まるものはそのまま返す。
    """
    if not path:
        return path
    lowered = path.lower()
    if (
        lowered.startswith("http://")
        or lowered.startswith("https://")
        or path.startswith("#")
        or path.startswith("/")
        or path.startswith("../")
        or lowered.startswith("mailto:")
        or lowered.startswith("tel:")
    ):
        return path
    return root + path


def render_inline(text, root):
    """
    段落・リスト項目などの「行内」記法をHTMLに変換する。

    対応: 画像 ![alt](src) / リンク [text](url) / 太字 **strong**
    先にHTMLエスケープしてから、記法部分だけタグに置き換える。
    """
    # まず本文をエスケープ（< > & を無害化）
    escaped = html.escape(text, quote=False)

    # 画像 ![alt](src) を figure ではなく行内imgとして処理（段落内画像用）
    def image_sub(match):
        alt = match.group(1)
        src = resolve_path(match.group(2), root)
        return (
            f'<img src="{html.escape(src)}" alt="{alt}" '
            f'class="rounded-lg my-2" loading="lazy" decoding="async">'
        )

    escaped = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", image_sub, escaped)

    # リンク [text](url)
    def link_sub(match):
        label = match.group(1)
        href = resolve_path(match.group(2), root)
        # 外部リンクは別タブ＋rel付与
        extra = ""
        if href.lower().startswith("http"):
            extra = ' target="_blank" rel="noopener"'
        return (
            f'<a href="{html.escape(href)}" '
            f'class="text-primary hover:underline"{extra}>{label}</a>'
        )

    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_sub, escaped)

    # 太字 **text** → <strong>
    escaped = re.sub(
        r"\*\*([^*]+)\*\*", r'<strong class="text-text-main">\1</strong>', escaped
    )

    return escaped


def is_table_separator(line):
    """表のヘッダ区切り行（| --- | --- |）かどうかを判定する"""
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    # すべてのセルが --- のみ（ハイフン）で構成されていれば区切り行
    return (
        len(cells) > 0
        and all(re.fullmatch(r":?-{1,}:?", c) for c in cells if c != "")
        and any(cells)
    )


def split_table_row(line):
    """表の1行（| a | b |）をセルのリストに分解する"""
    return [c.strip() for c in line.strip().strip("|").split("|")]


def render_table(rows, root):
    """
    表ブロック（行のリスト）をHTMLの<table>に変換する。
    1行目をヘッダ、2行目を区切り、3行目以降を本体として扱う。
    """
    if len(rows) < 2:
        return ""
    header_cells = split_table_row(rows[0])
    body_rows = rows[2:]  # rows[1] は区切り行なので飛ばす

    parts = [
        '<div class="overflow-x-auto">',
        '<table class="w-full text-sm border-collapse">',
        '<thead><tr class="bg-primary-50 text-text-main">',
    ]
    for cell in header_cells:
        parts.append(
            f'<th class="border border-border px-3 py-2 text-left">{render_inline(cell, root)}</th>'
        )
    parts.append("</tr></thead><tbody>")

    # 偶数行に薄い背景を付けて読みやすくする
    for index, row in enumerate(body_rows):
        cells = split_table_row(row)
        row_class = ' class="bg-surface"' if index % 2 == 1 else ""
        parts.append(f"<tr{row_class}>")
        for cell in cells:
            parts.append(
                f'<td class="border border-border px-3 py-2">{render_inline(cell, root)}</td>'
            )
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts)


def render_faq(faq_items, root):
    """
    FAQブロック（(質問, 回答) のリスト）を、サンプル準拠のアコーディオンHTMLにする。
    """
    chevron = (
        '<svg class="w-5 h-5 text-text-light flex-shrink-0 ml-3 '
        'group-open:rotate-180 transition-transform" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">'
        '<polyline points="6 9 12 15 18 9"/></svg>'
    )
    parts = [
        '<section id="faq">',
        '<h2 class="font-display font-bold text-xl sm:text-2xl text-text-main '
        'mb-5 pl-3 border-l-4 border-primary">よくある質問</h2>',
        '<div class="space-y-3">',
    ]
    for question, answer in faq_items:
        parts.append('<details class="group bg-surface rounded-xl ring-1 ring-border">')
        parts.append(
            '<summary class="flex items-center justify-between cursor-pointer '
            'p-4 text-sm sm:text-base font-medium text-text-main">'
            f"<span>{render_inline(question, root)}</span>{chevron}</summary>"
        )
        parts.append(
            '<div class="px-4 pb-4 text-sm text-text-sub leading-relaxed">'
            f"{render_inline(answer, root)}</div>"
        )
        parts.append("</details>")
    parts.append("</div></section>")
    return "".join(parts)


def slugify_heading(text, used_ids):
    """見出しテキストから目次リンク用のidを作る（重複しないよう連番を付ける）"""
    # 日本語はidに不向きなので、英数字以外はハイフンに置換。空ならsectionにする
    base = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    if not base:
        base = "section"
    candidate = base
    counter = 2
    while candidate in used_ids:
        candidate = f"{base}-{counter}"
        counter += 1
    used_ids.add(candidate)
    return candidate


def convert_markdown(body, root):
    """
    マークダウン本文をHTMLに変換する。

    対応記法:
      ## 見出し → h2 / ### 見出し → h3
      - 箇条書き → ul / 1. 番号付き → ol
      | a | b | 表 → table
      ![alt](src) 単独行 → figure+img
      > 引用 → 注記ブロック（仮データ注記などに使用）
      ::: faq ... ::: → FAQアコーディオン
      その他の行 → 段落 p

    戻り値: (本文HTML, 目次用の見出しリスト[(id, テキスト)], FAQの(質問,回答)リスト)
    """
    lines = body.split("\n")
    html_parts = []
    headings = []  # 目次生成用の (id, テキスト)
    faq_items = []  # FAQPage JSON-LD生成用の (質問, 回答)
    used_ids = set()
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # --- 空行：何もしない ---
        if stripped == "":
            i += 1
            continue

        # --- FAQブロック ::: faq ... ::: ---
        if stripped == "::: faq":
            block_faq = []
            i += 1
            current_q = None
            while i < n and lines[i].strip() != ":::":
                row = lines[i].strip()
                if row.startswith("Q:"):
                    current_q = row[2:].strip()
                elif row.startswith("A:") and current_q is not None:
                    answer = row[2:].strip()
                    block_faq.append((current_q, answer))
                    current_q = None
                i += 1
            i += 1  # 閉じ ::: を飛ばす
            faq_items.extend(block_faq)
            html_parts.append(render_faq(block_faq, root))
            continue

        # --- 見出し ### → h3 ---
        if stripped.startswith("### "):
            text = stripped[4:].strip()
            html_parts.append(
                '<h3 class="font-display font-bold text-lg text-text-main mt-6 mb-2">'
                f"{render_inline(text, root)}</h3>"
            )
            i += 1
            continue

        # --- 見出し ## → h2（idを付けて目次に登録） ---
        if stripped.startswith("## "):
            text = stripped[3:].strip()
            heading_id = slugify_heading(text, used_ids)
            headings.append((heading_id, text))
            html_parts.append(
                f'<h2 id="{heading_id}" class="font-display font-bold text-xl sm:text-2xl '
                'text-text-main mb-3 pl-3 border-l-4 border-primary">'
                f"{render_inline(text, root)}</h2>"
            )
            i += 1
            continue

        # --- 引用 > → 注記（仮データ注記など） ---
        if stripped.startswith(">"):
            quote_lines = []
            while i < n and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            inner = render_inline(" ".join(quote_lines), root)
            html_parts.append(
                '<div class="bg-warm-light text-text-sub text-xs sm:text-sm rounded-xl '
                f'px-4 py-3 ring-1 ring-warm/20">{inner}</div>'
            )
            continue

        # --- 表 | a | b | （次行が区切り行なら表として処理） ---
        if (
            stripped.startswith("|")
            and (i + 1) < n
            and is_table_separator(lines[i + 1])
        ):
            table_rows = []
            while i < n and lines[i].strip().startswith("|"):
                table_rows.append(lines[i])
                i += 1
            html_parts.append(render_table(table_rows, root))
            continue

        # --- 単独行の画像 ![alt](src) → figure ---
        image_match = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if image_match:
            alt = image_match.group(1)
            src = resolve_path(image_match.group(2), root)
            html_parts.append(
                '<figure class="rounded-xl overflow-hidden ring-1 ring-border my-4">'
                f'<img src="{html.escape(src)}" alt="{html.escape(alt)}" '
                'class="w-full object-cover" loading="lazy" decoding="async">'
                f'<figcaption class="text-xs text-text-sub px-3 py-2 bg-surface">{html.escape(alt)}</figcaption>'
                "</figure>"
            )
            i += 1
            continue

        # --- 番号付きリスト 1. ---
        if re.match(r"^\d+\.\s+", stripped):
            items = []
            while i < n and re.match(r"^\d+\.\s+", lines[i].strip()):
                item_text = re.sub(r"^\d+\.\s+", "", lines[i].strip())
                items.append(item_text)
                i += 1
            list_html = [
                '<ol class="space-y-3 text-sm sm:text-base text-text-sub list-decimal list-inside">'
            ]
            for item in items:
                list_html.append(f"<li>{render_inline(item, root)}</li>")
            list_html.append("</ol>")
            html_parts.append("".join(list_html))
            continue

        # --- 箇条書きリスト - ---
        if stripped.startswith("- "):
            items = []
            while i < n and lines[i].strip().startswith("- "):
                item_text = lines[i].strip()[2:]
                items.append(item_text)
                i += 1
            list_html = [
                '<ul class="space-y-2 text-sm sm:text-base text-text-sub list-disc list-inside">'
            ]
            for item in items:
                list_html.append(f"<li>{render_inline(item, root)}</li>")
            list_html.append("</ul>")
            html_parts.append("".join(list_html))
            continue

        # --- それ以外：段落（連続する非空行を1段落にまとめる） ---
        para_lines = []
        while i < n and lines[i].strip() != "":
            # 次の行がブロック記法の始まりなら段落を打ち切る
            nxt = lines[i].strip()
            if (
                nxt.startswith("#")
                or nxt.startswith("- ")
                or re.match(r"^\d+\.\s+", nxt)
                or nxt.startswith("|")
                or nxt.startswith(">")
                or nxt.startswith(":::")
                or re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", nxt)
            ):
                break
            para_lines.append(nxt)
            i += 1
        paragraph_text = " ".join(para_lines)
        html_parts.append(
            '<p class="text-sm sm:text-base leading-relaxed text-text-sub">'
            f"{render_inline(paragraph_text, root)}</p>"
        )

    return "\n".join(html_parts), headings, faq_items


# ============================================================
# 3. 共通パーツ（ヘッダー・フッター・フローティング）
#    {root} に "../"（記事）または ""（一覧）を入れて使う
# ============================================================


def common_head_styles():
    """全ページ共通の<head>内スタイル（@theme・フォント・CSP）を返す"""
    return """  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; base-uri 'self';">
  <meta name="robots" content="index, follow">
  <link rel="icon" type="image/x-icon" href="{root}images/favicon.ico">
  <link rel="icon" type="image/png" sizes="192x192" href="{root}images/favicon-192.png">
  <link rel="apple-touch-icon" sizes="180x180" href="{root}images/favicon-180.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700;900&family=Zen+Kaku+Gothic+New:wght@400;500;700&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
  <style type="text/tailwindcss">
    @theme {{
      --color-primary: #5BBEE5;
      --color-primary-dark: #3A9FCA;
      --color-primary-light: #E8F4FD;
      --color-primary-50: #F0F9FF;
      --color-accent: #06C755;
      --color-accent-dark: #05A847;
      --color-warm: #F5A623;
      --color-warm-light: #FFF8EC;
      --color-surface: #FAFCFE;
      --color-card: #FFFFFF;
      --color-text-main: #2D3748;
      --color-text-sub: #5A6677;
      --color-text-light: #8896A6;
      --color-border: #E2EAF0;
      --font-sans: "Zen Kaku Gothic New", "Noto Sans JP", system-ui, sans-serif;
      --font-display: "Noto Sans JP", sans-serif;
    }}
  </style>
  <style>
    .line-btn{{transition:all .3s cubic-bezier(.25,.46,.45,.94)}}
    .line-btn:hover{{transform:translateY(-2px);box-shadow:0 8px 24px rgba(6,199,85,.3)}}
    .post-card{{transition:all .3s cubic-bezier(.25,.46,.45,.94)}}
    .post-card:hover{{transform:translateY(-4px);box-shadow:0 12px 28px rgba(91,190,229,.18)}}
    .ig-btn{{background:linear-gradient(45deg,#F58529 0%,#DD2A7B 50%,#8134AF 100%);transition:all .3s ease}}
    .ig-btn:hover{{transform:translateY(-2px);box-shadow:0 12px 28px rgba(221,42,123,.3)}}
    .sr-only{{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border-width:0}}
    h2,h3{{text-wrap:balance}}p,li{{text-wrap:pretty}}
    .article-body h2{{scroll-margin-top:90px}}
  </style>
  <script>
    if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
    window.addEventListener('pageshow', () => {{ window.scrollTo(0, 0); }});
  </script>"""


def common_header():
    """全ページ共通のヘッダーHTML（{root}入り）"""
    return """<header class="sticky top-0 left-0 right-0 z-50 bg-white/95 backdrop-blur-sm border-b border-border">
  <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="flex items-center justify-between h-16 sm:h-18">
      <a href="{root}index.html" class="flex items-center -ml-4 sm:-ml-6 lg:-ml-8">
        <img src="{root}images/logo-transparent.png" alt="キレイシア" class="h-10 sm:h-12 w-auto">
      </a>
      <nav class="hidden md:flex items-center gap-3 lg:gap-5" role="navigation">
        <a href="{root}index.html" class="text-xs lg:text-sm text-text-main hover:text-primary font-medium transition-colors">HOME</a>
        <a href="{root}service.html" class="text-xs lg:text-sm text-text-main hover:text-primary font-medium transition-colors">サービス一覧</a>
        <a href="{root}about.html" class="text-xs lg:text-sm text-text-main hover:text-primary font-medium transition-colors">企業理念</a>
        <a href="{root}company.html" class="text-xs lg:text-sm text-text-main hover:text-primary font-medium transition-colors">会社概要</a>
        <a href="https://en-gage.net/kireisia_saiyo/" target="_blank" rel="noopener" class="text-xs lg:text-sm text-text-main hover:text-primary font-medium transition-colors">採用情報</a>
        <a href="{root}blog.html" class="text-xs lg:text-sm text-primary font-bold transition-colors">ブログ</a>
        <a href="{root}contact.html" class="text-xs lg:text-sm text-text-main hover:text-primary font-medium transition-colors">お問い合わせ</a>
      </nav>
      <div class="flex items-center gap-2 sm:gap-3">
        <a href="tel:06-7493-0993" class="flex items-center gap-1.5 bg-primary-50 hover:bg-primary-light text-primary-dark font-bold text-sm sm:text-base px-3 py-2 sm:px-4 sm:py-2 rounded-full transition-colors">
          <svg class="w-4 h-4 sm:w-5 sm:h-5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.12.94.39 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.31 1.87.57 2.81.7A2 2 0 0 1 22 16.92z"/></svg><span class="whitespace-nowrap">06-7493-0993</span>
        </a>
        <a href="{root}contact.html" class="line-btn hidden md:inline-flex items-center gap-2 bg-primary hover:bg-primary-dark text-white text-sm font-bold px-5 py-3 rounded-full">
          <svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
          <span class="hidden sm:inline">お問い合わせ</span>
        </a>
        <button id="mobileMenuBtn" class="md:hidden p-2 -mr-2 text-text-sub hover:text-primary transition-colors" aria-label="メニュー" aria-expanded="false">
          <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
        </button>
      </div>
    </div>
  </div>
  <div id="mobileMenu" class="hidden md:hidden bg-white border-t border-border">
    <nav class="px-4 py-4 space-y-3">
      <a href="{root}index.html" class="block text-sm text-text-main hover:text-primary py-1">HOME</a>
      <a href="{root}service.html" class="block text-sm text-text-main hover:text-primary py-1">サービス一覧</a>
      <a href="{root}about.html" class="block text-sm text-text-main hover:text-primary py-1">企業理念</a>
      <a href="{root}company.html" class="block text-sm text-text-main hover:text-primary py-1">会社概要</a>
      <a href="https://en-gage.net/kireisia_saiyo/" target="_blank" rel="noopener" class="block text-sm text-text-main hover:text-primary py-1">採用情報</a>
      <a href="{root}blog.html" class="block text-sm text-primary font-bold py-1">ブログ</a>
      <a href="{root}contact.html" class="block text-sm text-text-main hover:text-primary py-1">お問い合わせ</a>
    </nav>
  </div>
</header>"""


def common_footer():
    """全ページ共通のフッター＋スクリプト＋フローティングLINE＋スマホ下部CTA（{root}入り）"""
    return """<footer class="bg-text-main text-white py-12 sm:py-16">
  <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="grid grid-cols-1 md:grid-cols-3 gap-8 mb-8">
      <div>
        <img src="{root}images/logo-footer.png" alt="キレイシア" class="h-12 w-auto mb-4">
        <p class="text-sm text-white/80 leading-relaxed mb-4">大阪市城東区を拠点に、<br>大阪・京都・兵庫・奈良エリアで<br>ハウスクリーニングを行っています。</p>
        <div class="space-y-1 text-sm text-white/70">
          <p>〒536-0023</p>
          <p>大阪府大阪市城東区東中浜7丁目2-21</p>
          <p>TEL：<a href="tel:06-7493-0993" class="hover:text-primary transition-colors">06-7493-0993</a></p>
          <p>営業時間：9:00〜20:00</p>
        </div>
      </div>
      <div>
        <h4 class="font-display font-bold text-base mb-4 text-primary">ページ一覧</h4>
        <ul class="space-y-2 text-sm text-white/80">
          <li><a href="{root}index.html" class="hover:text-primary transition-colors">HOME</a></li>
          <li><a href="{root}service.html" class="hover:text-primary transition-colors">サービス一覧</a></li>
          <li><a href="{root}about.html" class="hover:text-primary transition-colors">企業理念</a></li>
          <li><a href="{root}company.html" class="hover:text-primary transition-colors">会社概要</a></li>
          <li><a href="https://en-gage.net/kireisia_saiyo/" target="_blank" rel="noopener" class="hover:text-primary transition-colors">採用情報</a></li>
          <li><a href="{root}blog.html" class="hover:text-primary transition-colors">ブログ</a></li>
          <li><a href="{root}contact.html" class="hover:text-primary transition-colors">お問い合わせ</a></li>
          <li><a href="{root}privacy.html" class="hover:text-primary transition-colors">プライバシーポリシー</a></li>
        </ul>
      </div>
      <div>
        <h4 class="font-display font-bold text-base mb-4 text-primary">お問い合わせ</h4>
        <div class="space-y-3">
          <a href="https://page.line.me/?accountId=235yilws" class="inline-flex items-center gap-2 bg-accent hover:bg-accent-dark text-white text-sm font-bold px-4 py-2.5 rounded-full transition-colors">
            <img src="{root}images/line-brand-icon.png" alt="LINE" class="w-6 h-6 rounded">LINEで無料お見積り
          </a>
          <p class="text-sm text-white/80"><a href="tel:06-7493-0993" class="hover:text-primary transition-colors">📞 06-7493-0993</a></p>
          <p class="text-sm text-white/80"><a href="{root}contact.html" class="hover:text-primary transition-colors">✉ お問い合わせフォーム</a></p>
        </div>
      </div>
    </div>
    <div class="pt-8 border-t border-white/10 text-center text-xs text-white/60">
      <p>© 2026 株式会社キレイシア All Rights Reserved.</p>
    </div>
  </div>
</footer>

<script>
  // モバイルメニュー開閉処理（既存ページと同一）
  const mobileMenuBtn = document.getElementById('mobileMenuBtn');
  const mobileMenu = document.getElementById('mobileMenu');
  if (mobileMenuBtn && mobileMenu) {{
    mobileMenuBtn.addEventListener('click', () => {{
      const isHidden = mobileMenu.classList.contains('hidden');
      if (isHidden) {{ mobileMenu.classList.remove('hidden'); mobileMenuBtn.setAttribute('aria-expanded','true'); }}
      else {{ mobileMenu.classList.add('hidden'); mobileMenuBtn.setAttribute('aria-expanded','false'); }}
    }});
  }}
</script>

<div class="hidden md:block fixed bottom-4 right-4 z-40 sm:bottom-6 sm:right-6">
  <a href="https://page.line.me/?accountId=235yilws" class="flex items-center justify-center w-14 h-14 sm:w-16 sm:h-16 rounded-full bg-accent shadow-lg shadow-accent/30 hover:scale-110 transition-transform focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-accent/40" aria-label="LINEで予約"><img src="{root}images/line-brand-icon.png" alt="LINE" class="w-10 h-10 sm:w-11 sm:h-11 rounded-xl"></a>
</div>

<div class="md:hidden h-20" aria-hidden="true"></div>
<div class="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-white border-t border-border shadow-[0_-4px_16px_rgba(0,0,0,0.10)]" style="padding-bottom:env(safe-area-inset-bottom)">
  <div class="grid grid-cols-2">
    <a href="{root}contact.html" class="flex flex-col items-center justify-center gap-1 py-3 bg-primary hover:bg-primary-dark text-white font-bold text-xs transition-colors">
      <svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
      <span>お問い合わせ</span>
    </a>
    <a href="https://page.line.me/?accountId=235yilws" class="flex flex-col items-center justify-center gap-1 py-3 bg-accent hover:bg-accent-dark text-white font-bold text-xs transition-colors">
      <img src="{root}images/line-brand-icon.png" alt="LINE" class="w-6 h-6 rounded" loading="lazy">
      <span>LINEで見積もり</span>
    </a>
  </div>
</div>"""


def cta_section(title, lead_text):
    """記事末のお問い合わせCTAセクション（{root}入り）"""
    return f"""<section class="py-16 sm:py-20 bg-gradient-to-br from-primary-light via-white to-primary-50">
  <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
    <h2 class="font-display font-bold text-2xl sm:text-3xl text-text-main mb-4">{html.escape(title)}</h2>
    <p class="text-text-sub mb-8">{html.escape(lead_text)}</p>
    <div class="flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4">
      <a href="https://page.line.me/?accountId=235yilws" class="line-btn w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-accent hover:bg-accent-dark text-white font-bold px-8 py-4 rounded-full text-base">
        <img src="{{root}}images/line-brand-icon.png" alt="LINE" class="w-8 h-8 rounded-lg">LINEで無料お見積り
      </a>
      <a href="{{root}}contact.html" class="w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-white hover:bg-primary-50 text-text-main font-medium px-8 py-4 rounded-full text-base ring-1 ring-border hover:ring-primary/30 transition-all duration-200">
        <svg class="w-5 h-5 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
        お問い合わせフォーム
      </a>
    </div>
  </div>
</section>"""


def author_box():
    """監修者ボックス（E-E-A-T）。両テンプレ共通"""
    return """<div class="mt-12 bg-primary-50 rounded-2xl p-5 sm:p-6 flex items-start gap-4">
    <div class="flex-shrink-0 w-12 h-12 rounded-full bg-primary-light flex items-center justify-center text-primary-dark font-bold">監</div>
    <div>
      <p class="text-xs text-text-light mb-1">この記事の監修</p>
      <p class="font-bold text-text-main">株式会社キレイシア 代表取締役 出口 綱基</p>
      <p class="text-xs text-text-sub mt-1 leading-relaxed">大阪市城東区を拠点に、大阪・京都・兵庫・奈良でハウスクリーニングを提供。住宅から業務用・大規模物件まで幅広く対応。</p>
    </div>
  </div>"""


# ============================================================
# 4. JSON-LD（構造化データ）生成
# ============================================================


def build_article_jsonld(article, canonical_url):
    """Article構造化データを返す（JSON文字列）"""
    title = json_escape(article["title"])
    desc = json_escape(article["description"])
    date = article["date"]
    return f"""<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "{title}",
  "description": "{desc}",
  "author": {{"@type": "Organization", "name": "株式会社キレイシア"}},
  "publisher": {{"@type": "Organization", "name": "株式会社キレイシア", "logo": {{"@type": "ImageObject", "url": "{SITE_BASE}/images/logo-footer.png"}}}},
  "datePublished": "{date}",
  "dateModified": "{date}",
  "mainEntityOfPage": "{canonical_url}"
}}
</script>"""


def build_faq_jsonld(faq_items):
    """FAQPage構造化データを返す（FAQが無ければ空文字）"""
    if not faq_items:
        return ""
    entities = []
    for question, answer in faq_items:
        entities.append(
            '    {"@type": "Question", "name": "%s", '
            '"acceptedAnswer": {"@type": "Answer", "text": "%s"}}'
            % (json_escape(question), json_escape(answer))
        )
    body = ",\n".join(entities)
    return f"""<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
{body}
  ]
}}
</script>"""


def build_breadcrumb_jsonld(article):
    """BreadcrumbList構造化データを返す"""
    name = json_escape(article["title"])
    return f"""<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  "itemListElement": [
    {{"@type": "ListItem", "position": 1, "name": "HOME", "item": "{SITE_BASE}/"}},
    {{"@type": "ListItem", "position": 2, "name": "ブログ", "item": "{SITE_BASE}/blog.html"}},
    {{"@type": "ListItem", "position": 3, "name": "{name}"}}
  ]
}}
</script>"""


# カテゴリ→サービス種別（areaServed構造化データのserviceType用）
AREA_SERVICE_TYPE = {
    "エアコン": "エアコンクリーニング",
    "浴室・水回り": "水回りクリーニング",
    "キッチン": "キッチン・レンジフードクリーニング",
    "料金・相場": "ハウスクリーニング",
    "施工事例": "ハウスクリーニング",
    "お知らせ": "ハウスクリーニング",
}


def build_areaserved_jsonld(article):
    """対応エリア（areaServed）の構造化データを返す。
    画面には表示されない「裏側」のデータで、AI検索・ローカルSEOへ対応エリアを正式に伝える。
    """
    service = AREA_SERVICE_TYPE.get(article.get("category", ""), "ハウスクリーニング")
    return (
        '<script type="application/ld+json">\n'
        '{"@context":"https://schema.org","@type":"Service","serviceType":"'
        + service
        + '",'
        '"provider":{"@type":"LocalBusiness","name":"株式会社キレイシア","telephone":"+81-6-7493-0993",'
        '"address":{"@type":"PostalAddress","postalCode":"536-0023","addressRegion":"大阪府",'
        '"addressLocality":"大阪市城東区","streetAddress":"東中浜7丁目2-21"}},'
        '"areaServed":[{"@type":"City","name":"大阪市"},'
        '{"@type":"AdministrativeArea","name":"大阪市城東区"},'
        '{"@type":"AdministrativeArea","name":"大阪市東成区"},'
        '{"@type":"AdministrativeArea","name":"大阪市中央区"},'
        '{"@type":"City","name":"東大阪市"}]}\n'
        "</script>"
    )


def json_escape(text):
    """JSON-LD内に安全に埋め込めるよう、ダブルクオート・改行をエスケープする"""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


# ブログ一覧のジャンル別フィルター用JavaScript（通常文字列＝中括弧はそのまま）
BLOG_FILTER_SCRIPT = """<script>
  // ブログのジャンル別フィルター（ボタンで記事を絞り込む）
  (function () {
    const filterButtons = document.querySelectorAll('.blog-filter');
    const cards = document.querySelectorAll('#postGrid .post-card');
    const noPosts = document.getElementById('noPosts');
    if (!filterButtons.length || !cards.length) return;

    function setActive(activeBtn) {
      filterButtons.forEach((btn) => {
        const isActive = btn === activeBtn;
        btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        if (isActive) {
          btn.className = 'blog-filter bg-primary text-white text-sm font-bold px-4 py-2 rounded-full cursor-pointer';
        } else {
          btn.className = 'blog-filter bg-surface text-text-sub text-sm font-medium px-4 py-2 rounded-full ring-1 ring-border hover:ring-primary/40 cursor-pointer';
        }
      });
    }

    function applyFilter(category) {
      let shown = 0;
      cards.forEach((card) => {
        const badge = card.querySelector('span.rounded-full');
        const cardCategory = badge ? badge.textContent.trim() : '';
        const match = category === 'すべて' || cardCategory === category;
        card.classList.toggle('hidden', !match);
        if (match) shown++;
      });
      if (noPosts) noPosts.classList.toggle('hidden', shown !== 0);
    }

    filterButtons.forEach((btn) => {
      btn.addEventListener('click', () => {
        setActive(btn);
        applyFilter(btn.getAttribute('data-filter'));
      });
    });
  })();
</script>"""


# ============================================================
# 5. ページ生成
# ============================================================


def category_chip(category):
    """カテゴリchipのHTMLを返す（施工事例・お知らせは暖色、それ以外は水色）"""
    if category in CATEGORY_WARM:
        return (
            '<span class="inline-block bg-warm-light text-warm text-xs font-bold '
            f'px-3 py-1 rounded-full">{html.escape(category)}</span>'
        )
    return (
        '<span class="inline-block bg-primary-light text-primary-dark text-xs font-bold '
        f'px-3 py-1 rounded-full">{html.escape(category)}</span>'
    )


def format_date_ja(date_str):
    """YYYY-MM-DD を「2026年6月26日」表記にする"""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{dt.year}年{dt.month}月{dt.day}日"
    except ValueError:
        return date_str


def format_date_dot(date_str):
    """YYYY-MM-DD を「2026.06.26」表記にする（一覧カード用）"""
    return date_str.replace("-", ".")


def render_article_page(article):
    """type=article 用の記事ページHTMLを生成して返す"""
    root = "../"  # 記事は blog/ サブフォルダに出力されるため相対パスは ../
    canonical_url = f"{SITE_BASE}/blog/{article['slug']}.html"

    body_html, headings, faq_items = convert_markdown(article["body"], root)

    # 目次（H2から自動生成）
    toc_items = "".join(
        f'<li><a href="#{hid}" class="hover:underline">{html.escape(text)}</a></li>'
        for hid, text in headings
    )
    toc_html = ""
    if headings:
        toc_html = f"""<nav class="bg-surface rounded-xl ring-1 ring-border p-5 mb-10" aria-label="目次">
    <p class="font-bold text-sm text-text-main mb-3">この記事でわかること（目次）</p>
    <ol class="space-y-2 text-sm text-primary-dark list-decimal list-inside">{toc_items}</ol>
  </nav>"""

    # JSON-LD（Article + FAQPage + Breadcrumb）
    jsonld = "\n".join(
        filter(
            None,
            [
                build_article_jsonld(article, canonical_url),
                build_faq_jsonld(faq_items),
                build_breadcrumb_jsonld(article),
                build_areaserved_jsonld(article),
            ],
        )
    )

    head = common_head_styles().format(root=root)
    header = common_header().format(root=root)
    footer = common_footer().format(root=root)
    cta = cta_section(
        "エアコンクリーニングのご相談・お見積り",
        "お見積り・ご相談は無料です。お気軽にどうぞ。",
    ).format(root=root)

    page = f"""<!DOCTYPE html>
<html lang="ja">
<head>
{head}
  <title>{html.escape(article["title"])}｜キレイシア</title>
  <meta name="description" content="{html.escape(article["description"])}">
  <meta property="og:type" content="article">
  <meta property="og:url" content="{canonical_url}">
  <link rel="canonical" href="{canonical_url}">
  <meta property="og:title" content="{html.escape(article["title"])}">
  <meta property="og:description" content="{html.escape(article["description"])}">
  <meta property="og:image" content="{OGP_IMAGE}">
  <meta property="og:site_name" content="株式会社キレイシア">
  <meta property="og:locale" content="ja_JP">
{jsonld}
</head>
<body class="bg-white text-text-main font-sans antialiased scroll-smooth">

{header}

<main>
<article class="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 pt-8 pb-16">

  <nav class="text-xs text-text-light mb-6" aria-label="パンくずリスト">
    <ol class="flex flex-wrap items-center gap-1">
      <li><a href="{root}index.html" class="hover:text-primary">HOME</a></li>
      <li aria-hidden="true">›</li>
      <li><a href="{root}blog.html" class="hover:text-primary">ブログ</a></li>
      <li aria-hidden="true">›</li>
      <li class="text-text-sub">{html.escape(article["category"])}</li>
    </ol>
  </nav>

  <div class="flex flex-wrap items-center gap-3 mb-4">
    {category_chip(article["category"])}
    <time datetime="{article["date"]}" class="text-xs text-text-light">{format_date_ja(article["date"])} 更新</time>
  </div>

  <h1 class="font-display font-black text-2xl sm:text-3xl leading-snug text-text-main mb-3">
    {html.escape(article["title"])}
  </h1>

  <div class="bg-primary-50 border-l-4 border-primary rounded-r-xl p-5 sm:p-6 my-6">
    <p class="text-sm sm:text-base leading-relaxed">
      <strong class="text-text-main">{html.escape(article["lead"])}</strong>
    </p>
  </div>

  {toc_html}

  <div class="article-body space-y-8">
{body_html}
  </div>

  {author_box()}

</article>

{cta}

</main>

{footer}

</body>
</html>"""
    return page


def render_case_page(article):
    """type=case 用の施工事例ページHTMLを生成して返す"""
    root = "../"
    canonical_url = f"{SITE_BASE}/blog/{article['slug']}.html"

    body_html, headings, faq_items = convert_markdown(article["body"], root)

    # 施工概要テーブル（frontmatterのplace/work/scale/daysから生成）
    spec_rows = []
    for label, key in [
        ("場所", "place"),
        ("作業内容", "work"),
        ("台数・規模", "scale"),
        ("所要日数", "days"),
    ]:
        value = article.get(key, "")
        if value:
            spec_rows.append(
                f'<tr><th class="border border-border px-3 py-2 bg-surface text-left w-32">{label}</th>'
                f'<td class="border border-border px-3 py-2">{html.escape(value)}</td></tr>'
            )
    # 対応エリアは全社共通の固定値
    spec_rows.append(
        '<tr><th class="border border-border px-3 py-2 bg-surface text-left">対応エリア</th>'
        '<td class="border border-border px-3 py-2">大阪・京都・兵庫・奈良</td></tr>'
    )
    spec_table = f"""<section class="mb-10">
    <h2 class="font-display font-bold text-lg sm:text-xl text-text-main mb-3 pl-3 border-l-4 border-primary">施工概要</h2>
    <div class="overflow-x-auto">
      <table class="w-full text-sm border-collapse">
        <tbody>
          {"".join(spec_rows)}
        </tbody>
      </table>
    </div>
    <p class="text-xs text-text-light mt-2">※台数・日数はサンプルの数値です。本番では実際の内容を記載します。</p>
  </section>"""

    # JSON-LD（Article + Breadcrumb。施工事例にFAQがあれば追加）
    jsonld = "\n".join(
        filter(
            None,
            [
                build_article_jsonld(article, canonical_url),
                build_faq_jsonld(faq_items),
                build_breadcrumb_jsonld(article),
                build_areaserved_jsonld(article),
            ],
        )
    )

    head = common_head_styles().format(root=root)
    header = common_header().format(root=root)
    footer = common_footer().format(root=root)
    cta = cta_section(
        "ホテル・店舗・オフィスのエアコンもご相談ください",
        "台数が多い大規模物件も、まとめて対応します。お見積り・ご相談は無料です。",
    ).format(root=root)

    page = f"""<!DOCTYPE html>
<html lang="ja">
<head>
{head}
  <title>{html.escape(article["title"])}｜施工事例｜キレイシア</title>
  <meta name="description" content="{html.escape(article["description"])}">
  <meta property="og:type" content="article">
  <meta property="og:url" content="{canonical_url}">
  <link rel="canonical" href="{canonical_url}">
  <meta property="og:title" content="{html.escape(article["title"])}">
  <meta property="og:description" content="{html.escape(article["description"])}">
  <meta property="og:image" content="{OGP_IMAGE}">
  <meta property="og:site_name" content="株式会社キレイシア">
  <meta property="og:locale" content="ja_JP">
{jsonld}
</head>
<body class="bg-white text-text-main font-sans antialiased scroll-smooth">

{header}

<main>
<article class="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 pt-8 pb-16">

  <nav class="text-xs text-text-light mb-6" aria-label="パンくずリスト">
    <ol class="flex flex-wrap items-center gap-1">
      <li><a href="{root}index.html" class="hover:text-primary">HOME</a></li>
      <li aria-hidden="true">›</li>
      <li><a href="{root}blog.html" class="hover:text-primary">ブログ</a></li>
      <li aria-hidden="true">›</li>
      <li class="text-text-sub">{html.escape(article["category"])}</li>
    </ol>
  </nav>

  <div class="flex flex-wrap items-center gap-3 mb-4">
    {category_chip(article["category"])}
    <time datetime="{article["date"]}" class="text-xs text-text-light">{format_date_ja(article["date"])}</time>
  </div>

  <h1 class="font-display font-black text-2xl sm:text-3xl leading-snug text-text-main mb-3">
    {html.escape(article["title"])}
  </h1>

  <div class="bg-primary-50 border-l-4 border-primary rounded-r-xl p-5 sm:p-6 my-6">
    <p class="text-sm sm:text-base leading-relaxed">
      <strong class="text-text-main">{html.escape(article["lead"])}</strong>
    </p>
  </div>

  {spec_table}

  <div class="article-body space-y-8">
{body_html}
  </div>

  {author_box()}

</article>

{cta}

</main>

{footer}

</body>
</html>"""
    return page


def render_list_page(articles):
    """記事一覧ページ blog.html を生成して返す"""
    root = ""  # blog.html はルート直下なので相対パスのプレフィックス不要

    # 記事カードを date降順（loadで既にソート済み）で並べる
    cards = []
    for article in articles:
        thumb = resolve_path(article.get("thumbnail", "images/ogp.jpg"), root)
        link = f"blog/{article['slug']}.html"
        # 一覧では抜粋として lead を流用（line-clamp で2行に省略）
        excerpt = html.escape(article["lead"])
        chip = (
            f'<span class="bg-warm-light text-warm text-xs font-bold px-2.5 py-1 rounded-full">{html.escape(article["category"])}</span>'
            if article["category"] in CATEGORY_WARM
            else f'<span class="bg-primary-light text-primary-dark text-xs font-bold px-2.5 py-1 rounded-full">{html.escape(article["category"])}</span>'
        )
        cards.append(f"""      <a href="{link}" class="post-card bg-card rounded-2xl overflow-hidden ring-1 ring-border block">
        <div class="aspect-video overflow-hidden bg-primary-light">
          <img src="{html.escape(thumb)}" alt="{html.escape(article["title"])}のサムネイル" class="w-full h-full object-cover" loading="lazy" decoding="async">
        </div>
        <div class="p-4">
          <div class="flex items-center gap-2 mb-2">
            {chip}
            <time datetime="{article["date"]}" class="text-xs text-text-light">{format_date_dot(article["date"])}</time>
          </div>
          <h2 class="font-bold text-base text-text-main leading-snug mb-2">{html.escape(article["title"])}</h2>
          <p class="text-xs text-text-sub leading-relaxed line-clamp-2">{excerpt}</p>
          <span class="inline-block mt-3 text-xs text-primary font-bold">記事を読む →</span>
        </div>
      </a>""")
    cards_html = "\n\n".join(cards)

    head = common_head_styles().format(root=root)
    header = common_header().format(root=root)
    footer = common_footer().format(root=root)
    canonical_url = f"{SITE_BASE}/blog.html"

    page = f"""<!DOCTYPE html>
<html lang="ja">
<head>
{head}
  <title>お役立ちブログ｜大阪のハウスクリーニングのコツ・料金相場・事例｜キレイシア</title>
  <meta name="description" content="大阪のハウスクリーニング会社キレイシアのお役立ちブログ。エアコン・浴室・キッチンの掃除のコツ、料金相場、施工事例をわかりやすく解説します。">
  <meta property="og:type" content="website">
  <meta property="og:url" content="{canonical_url}">
  <link rel="canonical" href="{canonical_url}">
  <meta property="og:title" content="お役立ちブログ｜大阪のハウスクリーニング キレイシア">
  <meta property="og:description" content="掃除のコツ・料金相場・施工事例をわかりやすく解説。">
  <meta property="og:image" content="{OGP_IMAGE}">
  <meta property="og:site_name" content="株式会社キレイシア">
  <meta property="og:locale" content="ja_JP">
</head>
<body class="bg-white text-text-main font-sans antialiased scroll-smooth">

{header}

<main>

<section class="pt-12 sm:pt-16 pb-8 bg-white">
  <div class="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
    <span class="inline-block text-primary text-sm font-bold tracking-widest uppercase mb-3">BLOG</span>
    <h1 class="font-display font-black text-2xl sm:text-4xl tracking-tight text-text-main mb-4">お役立ちブログ</h1>
    <p class="text-sm sm:text-base text-text-sub leading-relaxed max-w-2xl mx-auto">
      大阪のハウスクリーニング会社キレイシアが、<strong class="text-text-main">エアコン・浴室・キッチンの掃除のコツ、料金相場、施工事例</strong>をわかりやすく解説します。プロの視点で「知っておくと得する情報」をお届けします。
    </p>
  </div>
</section>

<section class="pb-6 bg-white">
  <div class="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
    <div id="blogFilters" class="flex flex-wrap justify-center gap-2">
      <button type="button" class="blog-filter bg-primary text-white text-sm font-bold px-4 py-2 rounded-full cursor-pointer" data-filter="すべて" aria-pressed="true">すべて</button>
      <button type="button" class="blog-filter bg-surface text-text-sub text-sm font-medium px-4 py-2 rounded-full ring-1 ring-border hover:ring-primary/40 cursor-pointer" data-filter="エアコン" aria-pressed="false">エアコン</button>
      <button type="button" class="blog-filter bg-surface text-text-sub text-sm font-medium px-4 py-2 rounded-full ring-1 ring-border hover:ring-primary/40 cursor-pointer" data-filter="浴室・水回り" aria-pressed="false">浴室・水回り</button>
      <button type="button" class="blog-filter bg-surface text-text-sub text-sm font-medium px-4 py-2 rounded-full ring-1 ring-border hover:ring-primary/40 cursor-pointer" data-filter="キッチン" aria-pressed="false">キッチン</button>
      <button type="button" class="blog-filter bg-surface text-text-sub text-sm font-medium px-4 py-2 rounded-full ring-1 ring-border hover:ring-primary/40 cursor-pointer" data-filter="料金・相場" aria-pressed="false">料金・相場</button>
      <button type="button" class="blog-filter bg-surface text-text-sub text-sm font-medium px-4 py-2 rounded-full ring-1 ring-border hover:ring-primary/40 cursor-pointer" data-filter="施工事例" aria-pressed="false">施工事例</button>
      <button type="button" class="blog-filter bg-surface text-text-sub text-sm font-medium px-4 py-2 rounded-full ring-1 ring-border hover:ring-primary/40 cursor-pointer" data-filter="お知らせ" aria-pressed="false">お知らせ</button>
    </div>
  </div>
</section>

<section class="py-8 sm:py-10 bg-surface">
  <div class="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
    <div id="postGrid" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">

{cards_html}

    </div>
    <p id="noPosts" class="hidden text-center text-text-sub py-10">このジャンルの記事はまだありません。</p>
  </div>
</section>

{BLOG_FILTER_SCRIPT}

<section class="py-12 sm:py-16 bg-white">
  <div class="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="bg-gradient-to-br from-primary-50 to-white rounded-3xl p-6 sm:p-10 ring-1 ring-primary/10">
      <div class="flex flex-col sm:flex-row items-center gap-6">
        <div class="flex-shrink-0">
          <div class="w-20 h-20 sm:w-24 sm:h-24 rounded-full p-1" style="background:linear-gradient(45deg,#F58529 0%,#DD2A7B 50%,#8134AF 100%);">
            <div class="w-full h-full rounded-full bg-white flex items-center justify-center">
              <svg class="w-10 h-10" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <defs><linearGradient id="ig-g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#F58529"/><stop offset="50%" stop-color="#DD2A7B"/><stop offset="100%" stop-color="#8134AF"/></linearGradient></defs>
                <rect x="2" y="2" width="20" height="20" rx="5" stroke="url(#ig-g)" stroke-width="2"/>
                <circle cx="12" cy="12" r="4" stroke="url(#ig-g)" stroke-width="2"/>
                <circle cx="17.5" cy="6.5" r="1.2" fill="url(#ig-g)"/>
              </svg>
            </div>
          </div>
        </div>
        <div class="flex-1 text-center sm:text-left">
          <p class="text-sm text-text-sub mb-1">Instagram公式アカウント</p>
          <p class="font-display font-black text-xl sm:text-2xl text-text-main mb-2">@osouji_kireisia</p>
          <p class="text-sm text-text-sub leading-relaxed">日々の施工事例・お掃除のコツを発信中。最新の投稿はこちらから（本番ではここに自動表示）。</p>
        </div>
        <div class="flex-shrink-0">
          <a href="https://www.instagram.com/osouji_kireisia/" target="_blank" rel="noopener" class="ig-btn inline-flex items-center gap-2 text-white text-sm font-bold px-6 py-3 rounded-full">
            <svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069z"/></svg>
            <span>フォローする</span>
          </a>
        </div>
      </div>
    </div>
  </div>
</section>

<section class="py-16 sm:py-20 bg-gradient-to-br from-primary-light via-white to-primary-50">
  <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
    <h2 class="font-display font-bold text-2xl sm:text-3xl text-text-main mb-4">お気軽にお問い合わせください</h2>
    <p class="text-text-sub mb-8">お見積り・ご相談は無料です。</p>
    <div class="flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4">
      <a href="https://page.line.me/?accountId=235yilws" class="line-btn w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-accent hover:bg-accent-dark text-white font-bold px-8 py-4 rounded-full text-base">
        <img src="images/line-brand-icon.png" alt="LINE" class="w-8 h-8 rounded-lg">LINEで無料お見積り
      </a>
      <a href="contact.html" class="w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-white hover:bg-primary-50 text-text-main font-medium px-8 py-4 rounded-full text-base ring-1 ring-border hover:ring-primary/30 transition-all duration-200">
        <svg class="w-5 h-5 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
        お問い合わせフォーム
      </a>
    </div>
  </div>
</section>

</main>

{footer}

</body>
</html>"""
    return page


# ============================================================
# 5.5 sitemap.xml（検索エンジン向けURL一覧）生成
# ============================================================


def build_sitemap_xml(articles):
    """
    主要ページ＋公開済みブログ記事のURLを集めて sitemap.xml の文字列を作る。

    様式は本番LP（deploy/sitemap.xml）に準拠（urlset/url/loc/lastmod/changefreq/priority）。
    冪等性のため、記事は load_articles() でソート済みの順番のまま並べる。

    戻り値: sitemap.xml の中身（文字列）
    """
    # 主要ページの最終更新日は「ビルドした今日の日付」とする
    today = datetime.now().strftime("%Y-%m-%d")

    url_blocks = []

    # --- 主要ページ（固定リスト） ---
    for file_name, changefreq, priority in MAIN_PAGES:
        loc = f"{SITE_BASE}/{file_name}"
        url_blocks.append(
            "  <url>\n"
            f"    <loc>{html.escape(loc)}</loc>\n"
            f"    <lastmod>{today}</lastmod>\n"
            f"    <changefreq>{changefreq}</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            "  </url>"
        )

    # --- 公開済みブログ記事（lastmod は記事のdate） ---
    for article in articles:
        loc = f"{SITE_BASE}/blog/{article['slug']}.html"
        # 日付が不正な場合は今日の日付で代替する（XMLを壊さないため）
        try:
            datetime.strptime(article["date"], "%Y-%m-%d")
            lastmod = article["date"]
        except ValueError:
            lastmod = today
        url_blocks.append(
            "  <url>\n"
            f"    <loc>{html.escape(loc)}</loc>\n"
            f"    <lastmod>{lastmod}</lastmod>\n"
            "    <changefreq>monthly</changefreq>\n"
            "    <priority>0.7</priority>\n"
            "  </url>"
        )

    body = "\n".join(url_blocks)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n"
        "</urlset>\n"
    )


# ============================================================
# 6. メイン処理
# ============================================================


def write_file(path, content):
    """UTF-8でファイルを書き出す（with文を使用）"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def backup_existing_blog():
    """
    既存の blog.html を上書き前にバックアップする。

    バックアップは「CMS化する前の元のblog.html」を残すのが目的なので、
    既にバックアップが存在する場合は上書きしない（再ビルドのたびにCMS版で
    上書きしてしまうと、本当の元ファイルが失われるのを防ぐため）。
    """
    if os.path.exists(BACKUP_PATH):
        print(f"  バックアップは既に存在するため保持します → {BACKUP_PATH}")
    elif os.path.exists(BLOG_LIST_PATH):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(BLOG_LIST_PATH, BACKUP_PATH)
        print(f"  既存 blog.html をバックアップしました → {BACKUP_PATH}")
    else:
        print("  既存 blog.html が無いため、バックアップはスキップしました")


def main():
    """ビルド全体の流れを制御する"""
    print("=== キレイシア ブログCMS ビルド開始 ===")

    try:
        articles = load_articles()
    except Exception as error:
        print(f"[エラー] 記事の読み込みに失敗しました: {error}")
        sys.exit(1)

    if not articles:
        print("[エラー] published: true の記事が1件もありません。処理を中止します。")
        sys.exit(1)

    print(f"  対象記事: {len(articles)} 件")

    # 出力先フォルダを用意（無ければ作成）
    os.makedirs(BLOG_OUT_DIR, exist_ok=True)

    # 各記事ページを生成
    for article in articles:
        try:
            if article["type"] == "case":
                page_html = render_case_page(article)
            else:
                # article（既定）。未知のtypeも記事テンプレで出力する
                page_html = render_article_page(article)
            out_path = os.path.join(BLOG_OUT_DIR, f"{article['slug']}.html")
            write_file(out_path, page_html)
            print(f"  生成: blog/{article['slug']}.html （type={article['type']}）")
        except Exception as error:
            print(f"  [警告] {article.get('slug', '?')} の生成に失敗しました: {error}")

    # 一覧ページを生成（上書き前にバックアップ）
    try:
        backup_existing_blog()
        list_html = render_list_page(articles)
        write_file(BLOG_LIST_PATH, list_html)
        print("  生成: blog.html（一覧ページを再生成しました）")
    except Exception as error:
        print(f"[エラー] 一覧ページの生成に失敗しました: {error}")
        sys.exit(1)

    # サイトマップ（sitemap.xml）を生成する
    try:
        sitemap_xml = build_sitemap_xml(articles)
        write_file(SITEMAP_PATH, sitemap_xml)
        total_urls = len(MAIN_PAGES) + len(articles)
        print(
            f"  生成: sitemap.xml（主要{len(MAIN_PAGES)}ページ＋記事{len(articles)}件＝計{total_urls}URL）"
        )
    except Exception as error:
        print(f"[エラー] sitemap.xml の生成に失敗しました: {error}")
        sys.exit(1)

    print("=== ビルド完了 ===")


if __name__ == "__main__":
    main()
