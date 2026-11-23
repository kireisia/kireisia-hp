"""
反映前の自動点検（deploy_hp/check_site.py）のテスト
作成: 2026-11-23
"""

import json
import os
import sys

DEPLOY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.abspath(DEPLOY_DIR))

import check_site as cs  # noqa: E402

PAGE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'">
<title>テスト</title>
<meta name="description" content="説明">
{robots}
<link rel="canonical" href="https://www.kireisia.co.jp/{name}">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-ZFKLS69SQD"></script>
<script type="application/ld+json">{jsonld}</script>
</head>
<body>{body}</body>
</html>
"""


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def page(name, body="<p>本文</p>", robots="", jsonld='{"@type":"WebPage"}'):
    return PAGE.format(name=name, body=body, robots=robots, jsonld=jsonld)


def make_site(tmp_path, pages=None):
    """点検に通る最小のサイトを作る"""
    root = str(tmp_path)
    write(root, "CNAME", "www.kireisia.co.jp")
    for rel in cs.REQUIRED_FILES:
        if rel != "CNAME" and not rel.endswith(".html"):
            write(root, rel, "x")
    write(root, "googleed253135e72c7780.html", "")
    pages = pages or {"index.html": page("index.html")}
    for name, text in pages.items():
        write(root, name, text)
    locs = "".join(
        f"<url><loc>https://www.kireisia.co.jp/{n}</loc></url>" for n in pages
    )
    write(root, "sitemap.xml", f"<urlset>{locs}</urlset>")
    write(root, "content/settings.json", json.dumps({"phone": "06"}))
    return root


def codes(results, level=None):
    return [r.code for r in results if level is None or r.level == level]


# ---------- 正常系 ----------


def test_clean_site_has_no_ng(tmp_path):
    root = make_site(tmp_path)
    assert codes(cs.run_checks(root, changed=[]), cs.NG) == []


def test_real_site_has_no_ng():
    """今の本番と同じ中身は点検に通る（通らない点検は使い物にならない）"""
    results = cs.run_checks(os.path.abspath(DEPLOY_DIR), changed=[])
    assert [r for r in results if r.level == cs.NG] == []


# ---------- 異常系：サイトが止まる・壊れる ----------


def test_cname_changed_is_ng(tmp_path):
    root = make_site(tmp_path)
    write(root, "CNAME", "example.com")
    assert "CNAME" in codes(cs.run_checks(root, changed=[]), cs.NG)


def test_cname_missing_is_ng(tmp_path):
    root = make_site(tmp_path)
    os.remove(os.path.join(root, "CNAME"))
    assert "CNAME" in codes(cs.run_checks(root, changed=[]), cs.NG)


def test_required_file_missing_is_ng(tmp_path):
    root = make_site(tmp_path)
    os.remove(os.path.join(root, ".pages.yml"))
    assert "REQUIRED" in codes(cs.run_checks(root, changed=[]), cs.NG)


def test_broken_json_is_ng(tmp_path):
    root = make_site(tmp_path)
    write(root, "content/faq.json", '{"a": 1,}')
    assert "JSON" in codes(cs.run_checks(root, changed=[]), cs.NG)


def test_broken_link_is_ng(tmp_path):
    root = make_site(
        tmp_path, {"index.html": page("index.html", '<a href="nai.html">x</a>')}
    )
    assert "LINK" in codes(cs.run_checks(root, changed=[]), cs.NG)


def test_missing_image_is_ng(tmp_path):
    root = make_site(
        tmp_path,
        {"index.html": page("index.html", '<img src="images/nai.jpg" alt="x">')},
    )
    assert "LINK" in codes(cs.run_checks(root, changed=[]), cs.NG)


def test_link_with_query_and_anchor_is_ok(tmp_path):
    body = '<img src="images/a.jpg?v=3" alt="x"><a href="index.html#top">x</a><a href="tel:06">t</a><a href="https://example.com/">e</a><a href="#x">a</a>'
    root = make_site(tmp_path, {"index.html": page("index.html", body)})
    write(root, "images/a.jpg", "x")
    assert "LINK" not in codes(cs.run_checks(root, changed=[]))


def test_broken_jsonld_is_ng(tmp_path):
    root = make_site(tmp_path, {"index.html": page("index.html", jsonld='{"@type": }')})
    assert "JSONLD" in codes(cs.run_checks(root, changed=[]), cs.NG)


# ---------- 異常系：ページ追加で抜けやすい物 ----------


def test_new_page_not_in_sitemap_is_ng(tmp_path):
    root = make_site(tmp_path)
    write(root, "new.html", page("new.html"))
    assert "SITEMAP" in codes(cs.run_checks(root, changed=[]), cs.NG)


def test_noindex_page_need_not_be_in_sitemap(tmp_path):
    root = make_site(tmp_path)
    write(
        root,
        "thanks.html",
        page("thanks.html", robots='<meta name="robots" content="noindex">'),
    )
    assert "SITEMAP" not in codes(cs.run_checks(root, changed=[]))


def test_page_missing_head_items_is_ng(tmp_path):
    root = make_site(
        tmp_path, {"index.html": "<html><head></head><body></body></html>"}
    )
    got = codes(cs.run_checks(root, changed=[]), cs.NG)
    assert (
        got.count("HEAD") >= 5
    )  # title・説明文・viewport・canonical・アクセス計測・CSP


def test_wrong_canonical_is_ng(tmp_path):
    root = make_site(tmp_path, {"index.html": page("other.html")})
    assert "HEAD" in codes(cs.run_checks(root, changed=[]), cs.NG)


def test_changed_image_without_alt_is_ng(tmp_path):
    root = make_site(
        tmp_path, {"index.html": page("index.html", '<img src="images/a.jpg">')}
    )
    write(root, "images/a.jpg", "x")
    assert "ALT" in codes(cs.run_checks(root, changed=["index.html"]), cs.NG)


# ---------- 変えたファイルの点検 ----------


def test_protected_file_changed_is_ng_until_confirmed(tmp_path):
    root = make_site(tmp_path)
    assert "PROTECTED" in codes(cs.run_checks(root, changed=[".pages.yml"]), cs.NG)
    confirmed = cs.run_checks(root, changed=[".pages.yml"], confirmed_protected=True)
    assert "PROTECTED" not in codes(confirmed, cs.NG)
    assert "PROTECTED" in codes(confirmed, cs.CONFIRM)


def test_workflow_changed_is_protected(tmp_path):
    root = make_site(tmp_path)
    assert "PROTECTED" in codes(
        cs.run_checks(root, changed=[".github/workflows/build-blog.yml"]), cs.NG
    )


def test_big_image_is_ng(tmp_path):
    root = make_site(tmp_path)
    with open(os.path.join(root, "images_big.jpg"), "wb") as f:
        f.write(b"0" * (cs.MAX_IMAGE_BYTES + 1))
    assert "IMAGE_SIZE" in codes(cs.run_checks(root, changed=["images_big.jpg"]), cs.NG)


def test_image_at_limit_is_ok(tmp_path):
    root = make_site(tmp_path)
    with open(os.path.join(root, "ok.jpg"), "wb") as f:
        f.write(b"0" * cs.MAX_IMAGE_BYTES)
    assert "IMAGE_SIZE" not in codes(cs.run_checks(root, changed=["ok.jpg"]))


def test_secret_in_changed_file_is_ng(tmp_path):
    root = make_site(
        tmp_path, {"index.html": page("index.html", "<p>password = hunter2secret</p>")}
    )
    assert "SECRET" in codes(cs.run_checks(root, changed=["index.html"]), cs.NG)


def test_secret_message_does_not_show_the_secret(tmp_path):
    root = make_site(
        tmp_path,
        {
            "index.html": page(
                "index.html", "<p>ghp_abcdefghijklmnopqrstuvwxyz0123456789</p>"
            )
        },
    )
    results = [
        r for r in cs.run_checks(root, changed=["index.html"]) if r.code == "SECRET"
    ]
    assert results and all("ghp_abc" not in r.message for r in results)


def test_generated_file_edited_by_hand_needs_confirm(tmp_path):
    root = make_site(tmp_path, {"index.html": page("index.html"), "blog.html": page("blog.html")})
    assert "GENERATED" in codes(cs.run_checks(root, changed=["blog.html"]), cs.CONFIRM)


def test_generated_file_with_source_change_is_quiet(tmp_path):
    root = make_site(tmp_path, {"index.html": page("index.html"), "blog.html": page("blog.html")})
    write(root, "content/blog/a.md", "x")
    got = codes(cs.run_checks(root, changed=["blog.html", "content/blog/a.md"]))
    assert "GENERATED" not in got


def test_deleted_file_needs_confirm(tmp_path):
    root = make_site(tmp_path)
    assert "DELETED" in codes(
        cs.run_checks(root, changed=["images/gone.jpg"]), cs.CONFIRM
    )


def test_claim_words_in_added_lines_need_confirm(tmp_path):
    root = make_site(tmp_path)
    results = cs.run_checks(
        root,
        changed=[],
        added_lines={"index.html": ["<p>お客様満足度98%・地域No.1</p>"]},
    )
    assert "CLAIM" in codes(results, cs.CONFIRM)


def test_plain_added_lines_are_quiet(tmp_path):
    root = make_site(tmp_path)
    results = cs.run_checks(
        root, changed=[], added_lines={"index.html": ["<p>営業時間：9:00〜20:00</p>"]}
    )
    assert "CLAIM" not in codes(results)


# ---------- 終了コード ----------


def test_exit_code(tmp_path):
    root = make_site(tmp_path)
    assert cs.exit_code(cs.run_checks(root, changed=[])) == 0
    write(root, "CNAME", "x")
    assert cs.exit_code(cs.run_checks(root, changed=[])) == 1


# ---------- 予行演習（2026-11-23）で見つかった点 ----------


def test_image_in_template_does_not_need_alt(tmp_path):
    """JS が後から中身を入れる型（template）の中の画像は、alt が無くても止めない"""
    body = '<template id="t"><img class="ba"></template><img src="images/a.jpg" alt="x">'
    root = make_site(tmp_path, {"index.html": page("index.html", body)})
    write(root, "images/a.jpg", "x")
    assert "ALT" not in codes(cs.run_checks(root, changed=["index.html"]))


def test_image_after_template_still_needs_alt(tmp_path):
    body = '<template><img class="ba"></template><img src="images/a.jpg">'
    root = make_site(tmp_path, {"index.html": page("index.html", body)})
    write(root, "images/a.jpg", "x")
    assert "ALT" in codes(cs.run_checks(root, changed=["index.html"]), cs.NG)


def test_claim_word_that_was_already_there_is_quiet(tmp_path):
    """直した行に前からあった表現では止めない（増えた言葉だけ拾う）"""
    root = make_site(tmp_path)
    results = cs.run_checks(
        root,
        changed=[],
        added_lines={"index.html": ["<p>人気No.1 料金は10,000円</p>"]},
        removed_lines={"index.html": ["<p>人気No.1 料金は9,000円</p>"]},
    )
    assert "CLAIM" not in codes(results)


def test_claim_word_newly_added_on_edited_line_needs_confirm(tmp_path):
    root = make_site(tmp_path)
    results = cs.run_checks(
        root,
        changed=[],
        added_lines={"index.html": ["<p>人気No.1 地域最安</p>"]},
        removed_lines={"index.html": ["<p>人気No.1</p>"]},
    )
    claim = [r for r in results if r.code == "CLAIM"]
    assert claim and "最安" in claim[0].message and "No.1" not in claim[0].message


def test_og_url_left_from_copied_page_is_ng(tmp_path):
    text = page("new.html").replace(
        "<title>", '<meta property="og:url" content="https://www.kireisia.co.jp/company.html"><title>'
    )
    root = make_site(tmp_path, {"index.html": page("index.html"), "new.html": text})
    assert "HEAD" in codes(cs.run_checks(root, changed=["new.html"], new_files=["new.html"]), cs.NG)


def test_og_url_problem_on_existing_page_does_not_block(tmp_path):
    """前からあるページの og:url の不備では止めない（そのページを直すたびに止まるのを防ぐ）"""
    text = page("old.html").replace(
        "<title>", '<meta property="og:url" content="https://www.kireisia.co.jp/"><title>'
    )
    root = make_site(tmp_path, {"index.html": page("index.html"), "old.html": text})
    assert "HEAD" not in codes(cs.run_checks(root, changed=["old.html"], new_files=[]))


def test_protected_confirmation_is_per_file(tmp_path):
    root = make_site(tmp_path)
    results = cs.run_checks(root, changed=[".pages.yml", "build_blog.py"], confirmed_protected={"build_blog.py"})
    ng = [r.message for r in results if r.code == "PROTECTED" and r.level == cs.NG]
    assert len(ng) == 1 and ".pages.yml" in ng[0]


def test_confirmation_record_expires_when_file_changes_again(tmp_path):
    """担当者の確認の後にもう一度変えたら、確認し直しになる"""
    root = make_site(tmp_path)
    assert cs.record_confirmation(root, ["build_blog.py"]) == ["build_blog.py"]
    assert cs.confirmed_files(root, ["build_blog.py"]) == {"build_blog.py"}
    write(root, "build_blog.py", "changed again")
    assert cs.confirmed_files(root, ["build_blog.py"]) == set()


def test_non_protected_file_cannot_be_recorded(tmp_path):
    root = make_site(tmp_path)
    assert cs.record_confirmation(root, ["index.html"]) == []


def test_broken_confirmation_record_is_treated_as_empty(tmp_path):
    root = make_site(tmp_path)
    write(root, ".claude/confirmed-protected.json", "{broken")
    assert cs.confirmed_files(root, ["build_blog.py"]) == set()


# ---------- コードレビュー・予行演習2周目（2026-11-23）で見つかった点 ----------

import subprocess  # noqa: E402


def test_json_image_path_missing_is_ng(tmp_path):
    """content/ の JSON に書かれた画像が無ければ止める（表示の時に JSON の値が使われる）"""
    root = make_site(tmp_path)
    write(root, "content/modals/washer.json", json.dumps({"card": {"image": "images/nai.jpg"}}))
    assert "IMAGE_REF" in codes(cs.run_checks(root, changed=[]), cs.NG)


def test_json_image_path_existing_is_ok(tmp_path):
    root = make_site(tmp_path)
    write(root, "images/aru.jpg", "x")
    write(root, "content/modals/washer.json", json.dumps({"items": [{"image": "images/aru.jpg?v=2"}], "text": "images の説明"}))
    assert "IMAGE_REF" not in codes(cs.run_checks(root, changed=[]))


def test_blog_markdown_image_missing_is_ng(tmp_path):
    root = make_site(tmp_path)
    write(root, "content/blog/a.md", "---\nthumbnail: images/nai-thumb.jpg\n---\n本文 ![写真](images/nai2.png)\n")
    results = [r for r in cs.run_checks(root, changed=[]) if r.code == "IMAGE_REF"]
    assert len(results) == 2


def test_url_encoded_link_is_ok(tmp_path):
    """ブラウザでは正しく出る書き方（日本語のファイル名を記号に変えた書き方）で止めない"""
    root = make_site(tmp_path, {"index.html": page("index.html", '<img src="images/%E5%86%99%E7%9C%9F%201.jpg" alt="x">')})
    write(root, "images/写真 1.jpg", "x")
    assert "LINK" not in codes(cs.run_checks(root, changed=[]))


def test_link_with_different_letter_case_is_ng(tmp_path):
    """Mac では表示されるが、本番（GitHub Pages）では出ない書き方を止める"""
    root = make_site(tmp_path, {"index.html": page("index.html", '<img src="images/staff.jpg" alt="x">')})
    write(root, "images/Staff.JPG", "x")
    assert "LINK" in codes(cs.run_checks(root, changed=[]), cs.NG)


def test_percent_claim_needs_confirm(tmp_path):
    root = make_site(tmp_path)
    results = cs.run_checks(root, changed=[], added_lines={"index.html": ["<p>リピート率95％のお店です</p>"]})
    assert "CLAIM" in codes(results, cs.CONFIRM)


def test_deleted_protected_file_points_to_the_maker(tmp_path):
    """消した仕組みのファイルは記録できないので、記録のコマンドを案内しない"""
    root = make_site(tmp_path)
    os.remove(os.path.join(root, ".pages.yml"))
    messages = [r.message for r in cs.run_checks(root, changed=[".pages.yml"]) if r.code == "PROTECTED" and r.level == cs.NG]
    assert messages and "制作担当" in messages[0] and "--confirm-protected" not in messages[0]


def test_new_google_verification_file_is_not_a_page(tmp_path):
    root = make_site(tmp_path)
    write(root, "google1234567890abcdef.html", "google-site-verification: google1234567890abcdef.html")
    got = codes(cs.run_checks(root, changed=[]))
    assert "HEAD" not in got and "SITEMAP" not in got


def git(root, *arguments):
    environment = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    return subprocess.run(["git", *arguments], cwd=root, capture_output=True, text=True, env=environment, check=True)


def make_repo(tmp_path):
    """点検に通るサイトを git に登録した状態で作る"""
    root = make_site(tmp_path)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "first")
    return root


def test_collect_changes_finds_edited_untracked_and_japanese_names(tmp_path):
    root = make_repo(tmp_path)
    with open(os.path.join(root, "index.html"), "a", encoding="utf-8") as f:
        f.write("<p>地域最安</p>\n")
    write(root, "images/写真 1.jpg", "x")
    changes = cs.collect_changes(root)
    assert "index.html" in changes.changed and "images/写真 1.jpg" in changes.changed
    assert changes.added_lines["index.html"] == ["<p>地域最安</p>"]
    assert "images/写真 1.jpg" in changes.new_files and "index.html" not in changes.new_files


def test_collect_changes_without_git_returns_none(tmp_path):
    root = make_site(tmp_path)
    assert cs.collect_changes(root) is None


def test_pre_push_clean_repo_is_ok(tmp_path):
    root = make_repo(tmp_path)
    assert cs.check_pre_push(root) == []


def test_pre_push_untracked_file_is_ng(tmp_path):
    """git に入れ忘れた画像があると、手元では表示されても本番では出ない → 反映を止める"""
    root = make_repo(tmp_path)
    write(root, "images/new.jpg", "x")
    results = cs.check_pre_push(root)
    assert codes(results, cs.NG) == ["UNCOMMITTED"] and "images/new.jpg" in results[0].message


def test_pre_push_uncommitted_edit_is_ng(tmp_path):
    root = make_repo(tmp_path)
    write(root, "index.html", page("index.html", "<p>直した</p>"))
    assert codes(cs.check_pre_push(root), cs.NG) == ["UNCOMMITTED"]


def test_pre_push_without_git_is_ng(tmp_path):
    """変更点を調べられない時に、点検なしで通さない"""
    root = make_site(tmp_path)
    assert codes(cs.check_pre_push(root), cs.NG) == ["GIT"]
