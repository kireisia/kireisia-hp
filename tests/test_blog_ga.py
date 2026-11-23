"""
ブログのページ（一覧・記事）にアクセス計測（GA4）のタグが入ることのテスト
作成: 2026-11-23（他のページには入っていたが、ブログだけ抜けていた）
"""

import os
import sys

DEPLOY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.abspath(DEPLOY_DIR))

import build_blog  # noqa: E402

GA_ID = "G-ZFKLS69SQD"


def head(root=""):
    return build_blog.common_head_styles().format(root=root)


def test_blog_head_loads_ga_script():
    assert (
        f'<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>'
        in head()
    )


def test_blog_head_has_ga_config_with_valid_braces():
    """波かっこが正しく出る（format の二重かっこの書き間違いで JS が壊れない）"""
    text = head("../")
    assert "function gtag(){dataLayer.push(arguments);}" in text
    assert f"gtag('config','{GA_ID}');" in text


def test_blog_csp_allows_ga():
    """安全設定（CSP）が計測の読込と送信を止めない（他のページと同じ許可）"""
    text = head()
    line = [x for x in text.splitlines() if "Content-Security-Policy" in x][0]
    assert (
        "https://www.googletagmanager.com" in line.split("script-src")[1].split(";")[0]
    )
    assert "connect-src" in line
    connect = line.split("connect-src")[1].split(";")[0]
    assert (
        "https://www.google-analytics.com" in connect
        and "https://*.google-analytics.com" in connect
    )


def test_blog_csp_matches_other_pages():
    """ブログの安全設定が、会社概要ページと同じ内容になっている"""
    with open(os.path.join(DEPLOY_DIR, "company.html"), encoding="utf-8") as f:
        company = [
            x.strip() for x in f.read().splitlines() if "Content-Security-Policy" in x
        ][0]
    blog = [x.strip() for x in head().splitlines() if "Content-Security-Policy" in x][0]
    assert blog == company


def test_generated_blog_pages_have_ga():
    """作り直した後の一覧と全記事に、計測のタグが入っている"""
    pages = [os.path.join(DEPLOY_DIR, "blog.html")]
    blog_dir = os.path.join(DEPLOY_DIR, "blog")
    # 名前の先頭に空白がある物は、昔の不具合の残骸（今は作り直されない）なので対象外
    names = [
        n
        for n in sorted(os.listdir(blog_dir))
        if n.endswith(".html") and n == n.strip()
    ]
    pages += [os.path.join(blog_dir, n) for n in names]
    missing = []
    for path in pages:
        with open(path, encoding="utf-8") as f:
            if GA_ID not in f.read():
                missing.append(os.path.basename(path))
    assert missing == []
