#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
キレイシアHP 反映前の自動点検（作成: 2026-11-23）

本番に反映（git push）する前に、ホームページが壊れていないかを機械で確かめる。
外部ライブラリは使わない（Python 標準ライブラリのみ・Mac / Windows 共通）。

使い方:
    python3 check_site.py                      # 点検する（❌が1つでもあれば反映しない）
    python3 check_site.py --confirm-protected build_blog.py  # 仕組みのファイルの変更に、担当者が OK を出した時に記録する
    python3 check_site.py --shots about.html   # スマホ幅・PC幅の画像を撮る（見た目の確認用・複数ページ可）

結果の読み方:
    ❌ 止める   … このまま反映すると壊れる。直すまで反映しない
    ⚠️ 要確認 … 担当者に内容を確かめてから反映する
"""

import argparse
import functools
import hashlib
import html
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unicodedata
import urllib.parse
from collections import namedtuple
from html.parser import HTMLParser

# ===== 基本設定（全環境共通の固定値） =====

SITE_BASE = "https://www.kireisia.co.jp"
EXPECTED_CNAME = "www.kireisia.co.jp"
GA_ID = "G-ZFKLS69SQD"
# 画像1枚の上限（これより大きい画像は縮小してから入れる）
MAX_IMAGE_BYTES = 500 * 1024

NG = "NG"  # 止める
CONFIRM = "CONFIRM"  # 担当者に確認
Result = namedtuple("Result", "level code message")

# 無くなるとホームページ・編集画面・自動処理が止まるファイル
REQUIRED_FILES = [
    "CNAME",
    ".pages.yml",
    "robots.txt",
    "sitemap.xml",
    "index.html",
    "googleed253135e72c7780.html",
    "build_blog.py",
    "build_services_menu.py",
    "js/services-order.js",
    ".github/workflows/build-blog.yml",
    ".github/workflows/build-services-menu.yml",
]
# 仕組みのファイル（変える時は担当者の確認が要る）
PROTECTED_FILES = {
    "CNAME",
    ".pages.yml",
    "build_blog.py",
    "build_services_menu.py",
    "check_site.py",
    "js/services-order.js",
    "googleed253135e72c7780.html",
    "robots.txt",
    ".gitattributes",
}
PROTECTED_DIRS = (".github/", ".githooks/", ".claude/")
# 自動で作り直されるファイル（手で直しても消える）
GENERATED_FILES = {"blog.html", "sitemap.xml", "content/extra-services-index.json"}
GENERATED_DIRS = ("blog/",)
GENERATED_SOURCES = (
    "content/blog/",
    "content/blog-categories/",
    "content/extra-services/",
    "build_blog.py",
)

# 点検のプログラムとそのテスト（鍵・表現の「見本」が書いてあるので、文字の点検から外す）
SELF_FILES = {"check_site.py", "tests/test_check_site.py"}

# ページではないので点検しない HTML
VERIFICATION_FILES = {"googleed253135e72c7780.html"}

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg")
TEXT_EXTENSIONS = (
    ".html",
    ".md",
    ".json",
    ".js",
    ".css",
    ".yml",
    ".yaml",
    ".txt",
    ".py",
    ".xml",
)
# 点検しないフォルダ
SKIP_DIRS = {
    ".git",
    ".claude",
    ".github",
    ".githooks",
    "__pycache__",
    "_backup_blog_cms",
    ".ruff_cache",
}

# パスワード・鍵らしい文字列（このリポジトリは公開なので、入っていたら止める）
SECRET_PATTERNS = [
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY"),
    re.compile(
        r"(?i)(password|passwd|パスワード|secret|api[_-]?key)\s*[:=：]\s*[^\s<\"']{6,}"
    ),
]
# 根拠の確認が要る表現（景品表示法）
CLAIM_PATTERN = re.compile(
    r"No\.?\s*[1１]|ナンバー\s*(ワン|1)|最安|日本一|地域一|業界初|満足度|口コミ|お客様の声|受賞|"
    r"[0-9０-９,，]+\s*(件|名|社|世帯)\s*(以上|突破|の実績|超)|★|"
    r"[0-9０-９.．]+\s*[%％]|リピート率|再利用率|継続率|成約率|顧客満足"
)
# content/ の中の JSON・マークダウンに書かれた画像の場所
IMAGE_REF_PATTERN = re.compile(
    r"/?images/[^\s\"'()<>?#]+\.(?:jpg|jpeg|png|gif|webp|avif|svg)", re.IGNORECASE
)


# ============================================================
# HTML を読む
# ============================================================


class PageParser(HTMLParser):
    """1ページ分の HTML から、点検に使う情報だけを集める"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []  # href / src の値
        self.images_without_alt = []
        self.title = ""
        self.metas = {}  # name / property / http-equiv → content
        self.canonical = None
        self.jsonld_blocks = []
        self.script_srcs = []
        self._in_title = False
        self._in_jsonld = False
        self._buffer = []
        self._template_depth = 0  # <template>（JS が後から中身を入れる型）の中にいるか

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "template":
            self._template_depth += 1
        for key in ("href", "src", "poster"):
            if attributes.get(key):
                self.links.append(attributes[key])
        if tag == "img" and "alt" not in attributes and self._template_depth == 0:
            self.images_without_alt.append(attributes.get("src", "（srcなし）"))
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            key = (
                attributes.get("name")
                or attributes.get("property")
                or attributes.get("http-equiv")
            )
            if key:
                self.metas[key.lower()] = attributes.get("content") or ""
        if tag == "link" and (attributes.get("rel") or "").lower() == "canonical":
            self.canonical = attributes.get("href")
        if tag == "script":
            if attributes.get("src"):
                self.script_srcs.append(attributes["src"])
            if (attributes.get("type") or "").lower() == "application/ld+json":
                self._in_jsonld = True
                self._buffer = []

    def handle_endtag(self, tag):
        if tag == "template" and self._template_depth > 0:
            self._template_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag == "script" and self._in_jsonld:
            self._in_jsonld = False
            self.jsonld_blocks.append("".join(self._buffer))

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_jsonld:
            self._buffer.append(data)


def read_text(path):
    """文字ファイルを読む。読めない時は None を返す"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def parse_page(path):
    """HTML ファイルを読んで PageParser を返す。読めない時は None"""
    text = read_text(path)
    if text is None:
        return None
    parser = PageParser()
    parser.feed(text)
    return parser


def is_verification_file(root, rel_page):
    """Google などの所有確認ファイルか（ページではないので点検しない）"""
    if rel_page in VERIFICATION_FILES:
        return True
    text = read_text(os.path.join(root, rel_page)) or ""
    is_google_name = os.path.basename(rel_page).startswith("google")
    return is_google_name and text.strip().startswith("google-site-verification")


def list_html_pages(root):
    """点検する HTML の一覧（ルート直下と blog/ の中）を、ルートからの相対パスで返す"""
    pages = sorted(name for name in os.listdir(root) if name.endswith(".html"))
    blog_dir = os.path.join(root, "blog")
    if os.path.isdir(blog_dir):
        pages += sorted(
            "blog/" + name for name in os.listdir(blog_dir) if name.endswith(".html")
        )
    return pages


# ============================================================
# 点検（サイト全体）
# ============================================================


def check_cname(root):
    """独自ドメインの設定が変わっていないか"""
    text = read_text(os.path.join(root, "CNAME"))
    if text is None:
        return [
            Result(
                NG,
                "CNAME",
                "CNAME ファイルがありません。無いとホームページが表示されなくなります",
            )
        ]
    if text.strip() != EXPECTED_CNAME:
        return [
            Result(
                NG,
                "CNAME",
                f"CNAME の中身が「{EXPECTED_CNAME}」ではありません。変えるとホームページが表示されなくなります",
            )
        ]
    return []


def check_required_files(root):
    """無くなると止まるファイルが残っているか"""
    results = []
    for rel in REQUIRED_FILES:
        if rel != "CNAME" and not os.path.exists(os.path.join(root, rel)):
            results.append(Result(NG, "REQUIRED", f"必要なファイルがありません: {rel}"))
    return results


def check_json_files(root):
    """content/ の中のデータが壊れていないか"""
    results = []
    content_dir = os.path.join(root, "content")
    for folder, _dirs, files in os.walk(content_dir):
        for name in files:
            if not name.endswith(".json"):
                continue
            path = os.path.join(folder, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    json.load(f)
            except (OSError, ValueError) as error:
                results.append(
                    Result(NG, "JSON", f"データが壊れています: {rel}（{error}）")
                )
    return results


def is_external(link):
    """サイトの外へのリンク・ページ内リンクなど、ファイルの有無を調べない物か"""
    lowered = link.strip().lower()
    return lowered.startswith(
        (
            "http://",
            "https://",
            "//",
            "mailto:",
            "tel:",
            "#",
            "data:",
            "javascript:",
            "sms:",
            "line:",
        )
    )


def exists_exact(root, path):
    """ファイルがあるか（大文字・小文字まで一致するか）。Mac や Windows では違っても開けるが、本番では出ない"""
    relative = os.path.relpath(path, root)
    if relative.startswith(".."):
        return os.path.exists(path)
    current = root
    for part in relative.split(os.sep):
        if part in ("", "."):
            continue
        try:
            names = {unicodedata.normalize("NFC", name) for name in os.listdir(current)}
        except OSError:
            return False
        if unicodedata.normalize("NFC", part) not in names:
            return False
        current = os.path.join(current, part)
    return True


def iter_strings(value):
    """JSON の中の文字列を全部取り出す"""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_strings(item)


def check_content_images(root):
    """content/ の JSON・マークダウンに書かれた画像が実在するか（表示の時にここの値が使われる）"""
    results = []
    content_dir = os.path.join(root, "content")
    for folder, _dirs, files in os.walk(content_dir):
        for name in sorted(files):
            path = os.path.join(folder, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            if name.endswith(".json"):
                try:
                    with open(path, "r", encoding="utf-8-sig") as f:
                        texts = list(iter_strings(json.load(f)))
                except (OSError, ValueError):
                    continue  # 壊れた JSON は check_json_files が知らせる
            elif name.endswith(".md"):
                text = read_text(path)
                texts = [text] if text is not None else []
            else:
                continue
            for text in texts:
                for match in IMAGE_REF_PATTERN.finditer(text):
                    target = urllib.parse.unquote(match.group(0)).lstrip("/")
                    if not exists_exact(root, os.path.join(root, target)):
                        message = (
                            f"{rel}: 書かれている画像がありません → {match.group(0)}"
                            "（名前の打ち間違い・大文字小文字・入れ忘れを確認）"
                        )
                        results.append(Result(NG, "IMAGE_REF", message))
    return results


def check_links(root, rel_page, parser):
    """リンク先・画像のファイルが実在するか"""
    results = []
    page_dir = os.path.dirname(os.path.join(root, rel_page))
    for link in parser.links:
        if is_external(link) or "${" in link or "{{" in link:
            continue
        target = urllib.parse.unquote(link.split("#")[0].split("?")[0].strip())
        if not target:
            continue
        base = root if target.startswith("/") else page_dir
        path = os.path.normpath(os.path.join(base, target.lstrip("/")))
        if not exists_exact(root, path):
            results.append(
                Result(NG, "LINK", f"{rel_page}: リンク先・画像がありません → {link}")
            )
    return results


def check_jsonld(rel_page, parser):
    """検索エンジン向けのデータ（構造化データ）が壊れていないか"""
    results = []
    for block in parser.jsonld_blocks:
        try:
            json.loads(block)
        except ValueError as error:
            results.append(
                Result(
                    NG,
                    "JSONLD",
                    f"{rel_page}: 検索エンジン向けのデータが壊れています（{error}）",
                )
            )
    return results


def is_noindex(parser):
    return "noindex" in parser.metas.get("robots", "").lower()


def check_head(rel_page, parser, is_new=False):
    """ページの頭の部分に、必要な設定がそろっているか（ページ追加で抜けやすい）"""
    missing = []
    if not parser.title.strip():
        missing.append("ページの題名（title）")
    if not parser.metas.get("description", "").strip():
        missing.append("説明文（meta description）")
    if "viewport" not in parser.metas:
        missing.append("スマホ表示の設定（viewport）")
    if "content-security-policy" not in parser.metas:
        missing.append("安全設定（Content-Security-Policy）")
    # 自動で作られるページ（blog.html）は build_blog.py の型どおりなので、ここでは求めない
    if not is_generated(rel_page) and not any(GA_ID in src for src in parser.script_srcs):
        missing.append(f"アクセス計測（{GA_ID}）")
    results = [
        Result(NG, "HEAD", f"{rel_page}: {item} がありません") for item in missing
    ]

    allowed = {f"{SITE_BASE}/{rel_page}"}
    if rel_page == "index.html":
        allowed.add(f"{SITE_BASE}/")
    if not parser.canonical:
        results.append(
            Result(NG, "HEAD", f"{rel_page}: 正式なURLの宣言（canonical）がありません")
        )
    elif parser.canonical not in allowed:
        results.append(
            Result(
                NG,
                "HEAD",
                f"{rel_page}: 正式なURLの宣言（canonical）が別のページを指しています → {parser.canonical}",
            )
        )
    # 新しく足したページだけ見る（複製元のURLが残っていないか。前からあるページの不備では止めない）
    og_url = parser.metas.get("og:url")
    if is_new and og_url and og_url not in allowed:
        results.append(
            Result(
                NG,
                "HEAD",
                f"{rel_page}: SNS用のURL（og:url）が別のページを指しています → {og_url}（複製元のままになっていないか確認）",
            )
        )
    return results


def check_sitemap(root, root_pages):
    """検索に出すページが sitemap.xml に入っているか"""
    sitemap = read_text(os.path.join(root, "sitemap.xml")) or ""
    results = []
    for rel_page, parser in root_pages:
        if is_noindex(parser):
            continue
        urls = [f"{SITE_BASE}/{rel_page}<"]
        if rel_page == "index.html":
            urls.append(f"{SITE_BASE}/<")
        if not any(url in sitemap for url in urls):
            results.append(
                Result(
                    NG,
                    "SITEMAP",
                    f"{rel_page} が sitemap.xml に入っていません。"
                    "build_blog.py の MAIN_PAGES に1行足して python3 build_blog.py を実行してください",
                )
            )
    return results


# ============================================================
# 点検（今回変えたファイル）
# ============================================================


def is_protected(rel):
    return rel in PROTECTED_FILES or rel.startswith(PROTECTED_DIRS)


def is_generated(rel):
    return rel in GENERATED_FILES or rel.startswith(GENERATED_DIRS)


def is_confirmed(rel, confirmed_protected):
    """仕組みのファイルの変更が、担当者の確認済みか（True＝全部確認済み／集まり＝その中のファイルだけ）"""
    if confirmed_protected is True:
        return True
    return bool(confirmed_protected) and rel in confirmed_protected


def check_changed_files(root, changed, confirmed_protected):
    """変えたファイルの種類ごとの点検"""
    results = []
    source_changed = any(rel.startswith(GENERATED_SOURCES) for rel in changed)
    for rel in changed:
        path = os.path.join(root, rel)
        if is_protected(rel):
            if not os.path.exists(path):
                message = (
                    f"仕組みのファイルが消えています: {rel}。消すとホームページ・編集画面・自動処理が壊れるおそれがあります。"
                    "元に戻してください。どうしても消したい時は制作担当へ相談してください"
                )
                results.append(Result(NG, "PROTECTED", message))
            elif is_confirmed(rel, confirmed_protected):
                message = (
                    f"仕組みのファイルが変わっています: {rel}（担当者の確認済みとして記録されています。"
                    "もう一度聞き直さなくて構いません）"
                )
                results.append(Result(CONFIRM, "PROTECTED", message))
            else:
                message = (
                    f"仕組みのファイルが変わっています: {rel}。担当者に「何が変わるか」を説明して OK をもらってから、"
                    f"python3 check_site.py --confirm-protected {rel} を実行してください"
                    "（確認の後にもう一度変えたら、確認し直しになります）"
                )
                results.append(Result(NG, "PROTECTED", message))
        if not os.path.exists(path):
            results.append(
                Result(
                    CONFIRM,
                    "DELETED",
                    f"ファイルが消えています: {rel}。消してよいか担当者に確認してください",
                )
            )
            continue
        if is_generated(rel) and not source_changed:
            results.append(
                Result(
                    CONFIRM,
                    "GENERATED",
                    f"{rel} は自動で作り直されるファイルです。手で直した内容は消えます（元のデータを直してください）",
                )
            )
        if (
            rel.lower().endswith(IMAGE_EXTENSIONS)
            and os.path.getsize(path) > MAX_IMAGE_BYTES
        ):
            size_kb = os.path.getsize(path) // 1024
            results.append(
                Result(
                    NG,
                    "IMAGE_SIZE",
                    f"画像が大きすぎます: {rel}（{size_kb}KB）。{MAX_IMAGE_BYTES // 1024}KB 以下に縮小してから入れてください",
                )
            )
    return results


def check_alt(root, changed):
    """変えたページの画像に、説明（alt）が付いているか"""
    results = []
    for rel in changed:
        if not rel.endswith(".html") or is_generated(rel):
            continue
        parser = parse_page(os.path.join(root, rel))
        if parser is None:
            continue
        for src in parser.images_without_alt:
            results.append(
                Result(NG, "ALT", f"{rel}: 画像の説明（alt）がありません → {src}")
            )
    return results


def count_claim_words(lines):
    """行の集まりの中の「根拠の確認が要る表現」を、言葉ごとに数える"""
    counts = {}
    for line in lines:
        for match in CLAIM_PATTERN.finditer(line):
            counts[match.group(0)] = counts.get(match.group(0), 0) + 1
    return counts


def check_added_text(root, changed, added_lines, removed_lines=None):
    """足した文字に、鍵らしい文字列や、根拠の確認が要る表現が無いか"""
    removed_lines = removed_lines or {}
    results = []
    targets = dict(added_lines)
    for rel in changed:
        if rel in targets or not rel.lower().endswith(TEXT_EXTENSIONS):
            continue
        text = read_text(os.path.join(root, rel))
        if text is not None:
            targets[rel] = text.splitlines()
    for rel, lines in targets.items():
        if rel in SELF_FILES:
            continue  # 点検そのものと、そのテスト（見本の文字列が入っている）
        joined = "\n".join(lines)
        if any(pattern.search(joined) for pattern in SECRET_PATTERNS):
            # 見つけた文字列そのものは表示しない
            results.append(
                Result(
                    NG,
                    "SECRET",
                    f"{rel}: パスワードや鍵のような文字列が入っています。このリポジトリは公開なので、入れてはいけません",
                )
            )
        if is_generated(rel) or rel.startswith(".") or not rel.lower().endswith((".html", ".md", ".json")):
            continue
        # 直した行に前からあった表現は数えない（足した数が消した数より多い言葉だけ）
        before = count_claim_words(removed_lines.get(rel, []))
        after = count_claim_words(lines)
        words = sorted(word for word, count in after.items() if count > before.get(word, 0))
        if words:
            results.append(
                Result(
                    CONFIRM,
                    "CLAIM",
                    f"{rel}: 今回足した文に、根拠の確認が要る表現があります（{'・'.join(words[:5])}）。"
                    "数字・評価・お客様の声は、担当者から実物をもらった物だけ載せてください",
                )
            )
    return results


# ============================================================
# まとめて実行
# ============================================================


def run_checks(
    root,
    changed=None,
    added_lines=None,
    confirmed_protected=False,
    removed_lines=None,
    new_files=None,
):
    """全部の点検を実行して、結果の一覧を返す"""
    changed = [rel.replace(os.sep, "/") for rel in (changed or [])]
    added_lines = added_lines or {}
    new_files = set(new_files or [])
    results = []
    results += check_cname(root)
    results += check_required_files(root)
    results += check_json_files(root)
    results += check_content_images(root)

    root_pages = []
    for rel_page in list_html_pages(root):
        if is_verification_file(root, rel_page):
            continue  # Google の所有確認ファイル（ページではない）
        parser = parse_page(os.path.join(root, rel_page))
        if parser is None:
            results.append(
                Result(
                    NG,
                    "HTML",
                    f"{rel_page} を読めません（文字コードが UTF-8 ではない可能性）",
                )
            )
            continue
        results += check_links(root, rel_page, parser)
        results += check_jsonld(rel_page, parser)
        if "/" not in rel_page:
            results += check_head(rel_page, parser, rel_page in new_files)
            root_pages.append((rel_page, parser))
    results += check_sitemap(root, root_pages)

    results += check_changed_files(root, changed, confirmed_protected)
    results += check_alt(root, changed)
    results += check_added_text(root, changed, added_lines, removed_lines)
    return results


def exit_code(results):
    return 1 if any(result.level == NG for result in results) else 0


# ============================================================
# git から「今回変えたファイル」を調べる
# ============================================================


def run_git(root, *arguments):
    """git を実行して出力を返す。失敗したら None"""
    try:
        completed = subprocess.run(
            ["git", "-c", "core.quotepath=false", *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout if completed.returncode == 0 else None


Changes = namedtuple("Changes", "changed added_lines removed_lines new_files")
# 利用者の git の設定に左右されないよう、差分の形を固定する
DIFF_OPTIONS = [
    "--no-color",
    "--no-ext-diff",
    "--no-textconv",
    "--src-prefix=a/",
    "--dst-prefix=b/",
]


def find_base(root):
    """比べる相手（本番と分かれた所）を決める。他の人が後から足した変更を「自分の変更」に数えないため"""
    if not run_git(root, "rev-parse", "--verify", "--quiet", "origin/main"):
        return "HEAD"
    merge_base = (run_git(root, "merge-base", "HEAD", "origin/main") or "").strip()
    return merge_base or "origin/main"


def split_names(output):
    """git の -z 付きの出力（区切りが NUL）を、名前の一覧にする"""
    return [name for name in (output or "").split("\0") if name]


def collect_changes(root):
    """本番と比べて変わったファイル・足した行・消した行・新しいファイルを返す。git が使えない時は None"""
    if run_git(root, "rev-parse", "--verify", "--quiet", "HEAD") is None:
        return None
    base = find_base(root)
    names = run_git(root, "diff", "--name-only", "-z", base)
    added = run_git(root, "diff", "--name-only", "-z", "--diff-filter=A", base)
    untracked = run_git(root, "ls-files", "--others", "--exclude-standard", "-z")
    diff = run_git(root, "diff", "-U0", *DIFF_OPTIONS, base)
    if names is None or added is None or untracked is None or diff is None:
        return None
    untracked_list = split_names(untracked)
    changed = split_names(names) + untracked_list
    new_files = set(split_names(added)) | set(untracked_list)

    added_lines = {}
    removed_lines = {}
    current = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            # 名前に空白がある時は末尾に TAB が付く
            name = line[4:].rstrip("\t")
            current = name[2:] if name.startswith("b/") else None
            if current:
                added_lines.setdefault(current, [])
                removed_lines.setdefault(current, [])
        elif line.startswith("--- "):
            continue
        elif line.startswith("+") and current:
            added_lines[current].append(line[1:])
        elif line.startswith("-") and current:
            removed_lines[current].append(line[1:])
    return Changes(changed, added_lines, removed_lines, new_files)


def check_pre_push(root):
    """反映の直前だけの点検：手元のフォルダと、実際に反映される中身が同じか"""
    status = run_git(root, "status", "--porcelain", "--untracked-files=all", "-z")
    if status is None:
        message = "git で変更点を調べられません。点検できないので反映を止めました。制作担当へ相談してください"
        return [Result(NG, "GIT", message)]
    names = [entry[3:] for entry in split_names(status) if len(entry) > 3]
    if not names:
        return []
    message = (
        f"まだ反映に含まれていないファイルがあります: {'、'.join(names[:10])}。"
        "このまま反映すると、手元では表示されても本番では出ません（画像の入れ忘れなど）。"
        "使うファイルは反映に含め（登録して記録する）、使わないファイル（縮小前の元画像など）はこのフォルダの外へ移してください"
    )
    return [Result(NG, "UNCOMMITTED", message)]


# ============================================================
# 仕組みのファイルの「担当者の確認済み」を記録する
# ============================================================

# 記録の置き場（.claude/ の中＝GitHub には上がらない。このパソコンの中だけ）
CONFIRM_RECORD = os.path.join(".claude", "confirmed-protected.json")


def file_hash(path):
    """ファイルの中身の指紋（sha256）。読めない時は None"""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def load_confirm_record(root):
    """確認済みの記録（ファイル名 → 中身の指紋）を読む。無い・壊れている時は空"""
    try:
        with open(os.path.join(root, CONFIRM_RECORD), "r", encoding="utf-8") as f:
            record = json.load(f)
    except (OSError, ValueError):
        return {}
    return record if isinstance(record, dict) else {}


def record_confirmation(root, rel_paths):
    """担当者が確認した仕組みのファイルを、今の中身の指紋つきで記録する。記録できた名前の一覧を返す"""
    record = load_confirm_record(root)
    done = []
    for rel in rel_paths:
        rel = rel.replace(os.sep, "/")
        digest = file_hash(os.path.join(root, rel))
        if digest is None or not is_protected(rel):
            print(f"[C001] 記録できません（仕組みのファイルではない、または読めません）: {rel}")
            continue
        record[rel] = digest
        done.append(rel)
    path = os.path.join(root, CONFIRM_RECORD)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return done


def confirmed_files(root, changed):
    """変えた仕組みのファイルのうち、確認した時から中身が変わっていない物の集まりを返す"""
    record = load_confirm_record(root)
    return {
        rel
        for rel in changed
        if rel in record and record[rel] == file_hash(os.path.join(root, rel))
    }


# ============================================================
# 見た目の確認用の画像を撮る
# ============================================================

BROWSER_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]
BROWSER_COMMANDS = [
    "google-chrome",
    "chromium",
    "chromium-browser",
    "microsoft-edge",
    "chrome",
    "msedge",
]
# 画像の高さの上限（これより長いページは、上からここまでが写る）
MAX_SHOT_HEIGHT = 14000
# （名前, 幅, 高さ）
SHOT_SIZES = [
    ("sp390", 390, 3000),
    ("sp320", 320, 3000),
    ("pc1280", 1280, 2400),
]


def browser_candidates():
    """Chrome・Edge がありそうな場所の一覧（Windows で自分のユーザーだけに入れた場合も含む）"""
    candidates = list(BROWSER_CANDIDATES)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base = local_app_data.rstrip("\\/")
        candidates.append(base + "\\Google\\Chrome\\Application\\chrome.exe")
        candidates.append(base + "\\Microsoft\\Edge\\Application\\msedge.exe")
    return candidates


def find_browser():
    """Chrome か Edge の場所を探す。無ければ None"""
    for path in browser_candidates():
        if os.path.exists(path):
            return path
    for command in BROWSER_COMMANDS:
        found = shutil.which(command)
        if found:
            return found
    return None


# 画像を撮る時だけ使う「枠」のページ。指定した幅の枠の中にページを表示し、横はみ出しを測る
# （ブラウザは窓を約500pxより狭くできないため、枠の幅でスマホの幅を再現する）
FRAME_PATH = "/__frame__"
FRAME_HTML = """<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8"><title>frame</title>
<style>html,body{{margin:0;background:#888}}iframe{{display:block;border:0;background:#fff;width:{width}px;height:{height}px}}</style>
</head><body>
<iframe id="page" src="/{page}"></iframe>
<pre id="measure">MEASURE:pending</pre>
<script>
var frame = document.getElementById('page');
function measure() {{
  var doc = frame.contentDocument;
  var view = doc.documentElement.clientWidth;
  var wide = [];
  doc.querySelectorAll('body *').forEach(function (el) {{
    var box = el.getBoundingClientRect();
    if (box.width > 0 && box.right > view + 1 && wide.length < 5) {{
      wide.push(el.tagName.toLowerCase() + '.' + String(el.className).split(' ').slice(0, 3).join('.'));
    }}
  }});
  var height = Math.max(doc.documentElement.scrollHeight, doc.body ? doc.body.scrollHeight : 0);
  var result = {{view: view, content: doc.documentElement.scrollWidth, height: height, wide: wide}};
  document.getElementById('measure').textContent = 'MEASURE:' + JSON.stringify(result) + ':END';
}}
frame.addEventListener('load', function () {{ setTimeout(measure, 3000); }});
</script>
</body></html>
"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """表示用サーバー。アクセスの記録は画面に出さない。/__frame__ では枠のページを返す"""

    def log_message(self, format, *args):  # noqa: A002
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != FRAME_PATH:
            return super().do_GET()
        query = urllib.parse.parse_qs(parsed.query)
        try:
            width = int(query.get("w", ["390"])[0])
            height = int(query.get("h", ["3000"])[0])
        except ValueError:
            width, height = 390, 3000
        page = html.escape(query.get("page", ["index.html"])[0], quote=True)
        body = FRAME_HTML.format(width=width, height=height, page=page).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return None


def run_browser(browser, arguments, url):
    """ブラウザを画面なしで動かす。標準出力を返す（失敗したら None）"""
    profile = tempfile.mkdtemp(prefix="kireisia-profile-")
    command = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-first-run",
        f"--user-data-dir={profile}",
        "--virtual-time-budget=10000",
        *arguments,
        url,
    ]
    try:
        completed = subprocess.run(command, capture_output=True, timeout=120, check=False)
        return completed.stdout.decode("utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError) as error:
        print(f"[S003] ブラウザを動かせませんでした: {error}")
        return None
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def parse_measure(dom_text):
    """枠のページの出力から、横はみ出しの測定結果を取り出す。取れない時は None"""
    match = re.search(r"MEASURE:(\{.*?\}):END", html.unescape(dom_text or ""), re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except ValueError:
        return None


def describe_overflow(name, width, measure):
    """横はみ出しの測定結果を1行の文にする"""
    if measure is None:
        return f"⚠️ 横はみ出しを測れませんでした（{name}）。画像を見て確かめてください"
    if measure["content"] > measure["view"] + 1:
        parts = "、".join(measure["wide"]) or "不明"
        return f"❌ 横はみ出しあり（{name}）: 中身の幅 {measure['content']}px ＞ 画面の幅 {measure['view']}px。はみ出している部品: {parts}"
    return f"✅ 横はみ出しなし（{name}・画面の幅 {measure['view']}px）"


def take_shots(root, page, out_dir=None):
    """ページをスマホ幅・PC幅で撮り、横はみ出しを測る。画像ファイルの場所の一覧を返す"""
    browser = find_browser()
    if browser is None:
        print("[S001] Chrome か Edge が見つかりません。画像は撮れないので、担当者にブラウザで見てもらってください")
        return []
    if not os.path.exists(os.path.join(root, page.split("?")[0].split("#")[0])):
        print(f"[S002] ページがありません: {page}")
        return []
    out_dir = out_dir or tempfile.mkdtemp(prefix="kireisia-shots-")
    os.makedirs(out_dir, exist_ok=True)

    handler = functools.partial(QuietHandler, directory=root)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}{FRAME_PATH}"
    shots = []
    try:
        for name, width, height in SHOT_SIZES:
            # 1回目：横はみ出しとページの長さを測る
            query = urllib.parse.urlencode({"page": page, "w": width, "h": height})
            url = f"{base_url}?{query}"
            window = f"--window-size={max(width, 600)},{height}"
            measure = parse_measure(run_browser(browser, [window, "--dump-dom"], url))
            # 2回目：ページの一番下まで写る高さで撮る（長すぎるページは上限まで）
            if measure and measure.get("height"):
                height = min(max(int(measure["height"]) + 40, 600), MAX_SHOT_HEIGHT)
                query = urllib.parse.urlencode({"page": page, "w": width, "h": height})
                url = f"{base_url}?{query}"
                window = f"--window-size={max(width, 600)},{height}"
            stem = page.split("?")[0].split("#")[0].rsplit(".", 1)[0].replace("/", "_")
            out_path = os.path.join(out_dir, f"{stem}_{name}.png")
            run_browser(browser, [window, f"--screenshot={out_path}"], url)
            if os.path.exists(out_path):
                shots.append(out_path)
                print(f"撮りました（{name}・幅{width}px）: {out_path}")
            else:
                print(
                    f"[S004] 画像ができませんでした（{name}）。ブラウザを画面なしで動かせない環境です。"
                    "担当者にパソコンの画面で見てもらい、反映した直後にスマホでも必ず見てもらってください"
                )
            print(describe_overflow(name, width, measure))
    finally:
        server.shutdown()
        server.server_close()
    return shots


# ============================================================
# 入口
# ============================================================


def print_results(results, changed):
    blocked = [result for result in results if result.level == NG]
    confirms = [result for result in results if result.level == CONFIRM]
    if changed is None:
        print("⚠️ git で変更点を調べられませんでした（サイト全体の点検だけ行いました）")
    else:
        print(
            f"今回変えたファイル: {len(changed)}件"
            + (f"（{'、'.join(changed[:10])}）" if changed else "")
        )
    for result in blocked:
        print(f"❌ 止める [{result.code}] {result.message}")
    for result in confirms:
        print(f"⚠️ 要確認 [{result.code}] {result.message}")
    print("-" * 40)
    if blocked:
        print(
            f"結果: ❌ 反映できません（止める {len(blocked)}件・要確認 {len(confirms)}件）。❌を直してからもう一度点検してください"
        )
    elif confirms:
        print(
            f"結果: ⚠️ 壊れている所はありません。要確認 {len(confirms)}件を担当者に確かめてから反映してください"
        )
    else:
        print("結果: ✅ 点検に通りました")


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(
                encoding="utf-8"
            )  # Windows でも日本語と記号を出せるようにする
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description="キレイシアHP 反映前の自動点検")
    parser.add_argument(
        "--confirm-protected",
        nargs="+",
        metavar="FILE",
        help="担当者が OK を出した仕組みのファイルを記録する（例: build_blog.py）",
    )
    parser.add_argument(
        "--pre-push",
        action="store_true",
        help="反映の直前の点検（.githooks/pre-push から呼ばれる。手で付けなくてよい）",
    )
    parser.add_argument(
        "--shots",
        nargs="+",
        metavar="PAGE",
        help="スマホ幅・PC幅の画像を撮るページ（例: about.html index.html）",
    )
    parser.add_argument(
        "--out", metavar="DIR", help="画像の保存先（省略時は一時フォルダ）"
    )
    arguments = parser.parse_args()

    root = os.path.dirname(os.path.abspath(__file__))
    if arguments.shots:
        shot_lists = [take_shots(root, page, arguments.out) for page in arguments.shots]
        return 0 if all(shot_lists) else 1
    if arguments.confirm_protected:
        done = record_confirmation(root, arguments.confirm_protected)
        print(f"担当者の確認済みとして記録しました: {'、'.join(done) or 'なし'}")

    changes = collect_changes(root)
    if changes is None:
        results = run_checks(root, [])
        changed = None
    else:
        changed = changes.changed
        confirmed = confirmed_files(root, changed)
        results = run_checks(
            root,
            changed,
            changes.added_lines,
            confirmed,
            changes.removed_lines,
            changes.new_files,
        )
    if arguments.pre_push:
        results = check_pre_push(root) + results
    print_results(results, changed)
    return exit_code(results)


if __name__ == "__main__":
    sys.exit(main())
