# site-info.md — キレイシアHPの構成情報（サーバー・GitHub・ドメイン・外部サービス）

作成：2026-11-22（制作担当の作業記録から転記。記載は2026-11-22時点）
Claude Code は作業前にこのファイルを読むこと。編集のルールは `.claude/CLAUDE.md`。

> 🔴 このリポジトリは**公開**です。ここにはパスワード・ログイン情報・個人のメールアドレスは書いていません（書き足さないこと）。
> ログイン情報は株式会社キレイシアが管理しています。

---

## 1. 全体の仕組み（1枚で）

```
担当者 ──(Claude Code で編集・push)──┐
                                      ├─→ GitHub リポジトリ kireisia/kireisia-hp（main）
担当者 ──(編集画面 Pages CMS で保存)──┘         │
                                                │ 自動（約1分）
                                                ▼
                                    GitHub Pages（無料のホームページ置き場）
                                                │
              ドメイン kireisia.co.jp（エックスサーバードメインで管理）が GitHub Pages を指している
                                                ▼
                                    https://www.kireisia.co.jp/ を見た全員に表示
```

- サーバーの契約は**ありません**。ホームページは GitHub Pages（無料）で公開しています。
- エックスサーバーは**ドメインの管理だけ**に使っています（レンタルサーバーは未契約）。

---

## 2. GitHub

| 項目 | 内容 |
|---|---|
| リポジトリ | https://github.com/kireisia/kireisia-hp |
| 公開範囲 | 公開（public）＝誰でもコードを読める |
| 持ち主のアカウント | `kireisia`（株式会社キレイシアのアカウント） |
| 本番のブランチ | `main`（main に push した内容がそのまま公開される） |
| 公開の設定 | GitHub Pages・独自ドメイン `www.kireisia.co.jp`（`CNAME` ファイル）・https 強制 ON |
| 反映までの時間 | push から約1分で公開。ブラウザ側の記憶（キャッシュ）で最大10分ほど古い表示が残ることがある |

### このリポジトリに自動で push してくるもの（だから作業前に必ず `git pull --rebase`）
| 誰が | いつ | コミットの名前 |
|---|---|---|
| 編集画面（Pages CMS） | 担当者が編集画面で保存した時 | `Update content/... (via Pages CMS)` |
| 自動処理「ブログ自動ビルド」 | `content/blog/` や `.md` が変わった時 | `ブログ生成物を自動更新する（build_blog.py）` |
| 自動処理「追加サービスの左メニュー自動生成」 | `content/extra-services/` が変わった時＋毎日朝6時 | （github-actions[bot]） |
| Dependabot | 自動処理の部品の更新がある時 | 更新の提案（プルリクエスト） |
| 制作担当 | 保守の修正をした時 | 日本語のコミット |

- ⚠️ 編集画面（Pages CMS）での保存と自動処理は、反映前の自動点検を**通らずに**本番へ出る。そこで入った不備（画像の名前の打ち間違い等）は、次に Claude Code から反映する時の点検で ❌ として見つかる（その時の担当者の変更が原因とは限らない）。

### 自動処理（`.github/workflows/`）
| 名前 | ファイル | 何をするか |
|---|---|---|
| ブログ自動ビルド | `build-blog.yml` | `content/blog/*.md` から `blog/*.html`・`blog.html`・`sitemap.xml` を作り直し、`llms.txt` のブログ記事一覧の部分を差し替える（`build_blog.py`） |
| 追加サービスの左メニュー自動生成 | `build-services-menu.yml` | 追加サービスを作ると、編集画面の左メニューと `content/extra-services-index.json` を作り直す（`build_services_menu.py`） |

- ⚠️ 画像の自動圧縮は**このリポジトリには無い**（画像は入れる前に縮小する）。

---

## 3. ドメイン・DNS

| 項目 | 内容 |
|---|---|
| ドメイン | `kireisia.co.jp`（表示は `www.kireisia.co.jp`） |
| 管理会社 | エックスサーバードメイン（名義：株式会社キレイシア） |
| 有効期限 | **2027-07-31**（自動更新を設定済み・2026-07-26）。⚠️ 2027年6月に、自動更新の設定とカードの期限を一度確認する |
| レジストラロック（勝手な移管を防ぐ鍵） | ON |
| ネームサーバー | `ns1.xdomain.ne.jp`・`ns2.xdomain.ne.jp`・`ns3.xdomain.ne.jp` |

### DNSの設定（エックスサーバーの管理画面・🔴変えるとホームページが止まる）
| 種類 | 名前 | 値 |
|---|---|---|
| A | `kireisia.co.jp` | `185.199.108.153` |
| A | `kireisia.co.jp` | `185.199.109.153` |
| A | `kireisia.co.jp` | `185.199.110.153` |
| A | `kireisia.co.jp` | `185.199.111.153` |
| CNAME | `www` | `kireisia.github.io` |

- 🔴 この5行と `CNAME` ファイルは**変えない**。Claude Code からは DNS を触れない。DNS・ドメインの変更が必要な話は「大事なこと」（`.claude/CLAUDE.md` §7）として制作担当へ連絡する。
- 予定：エリア別ページ（`area.kireisia.co.jp`）を別のリポジトリ `kireisia-area` で作る構想あり。その場合も上の5行は触らず、`area` の行を1行足すだけ（2026-11-22時点で未着手）。

---

## 4. 関係するリポジトリ・旧サイト

| リポジトリ | 役割 | 触ってよいか |
|---|---|---|
| `kireisia/kireisia-hp` | **今のホームページ**（このリポジトリ） | ✅ |
| `kireisia/kireisia.github.io` | 旧LP（`kireisia.github.io`）。今は**新ホームページへの転送専用**（`index.html`・`404.html`） | ❌ 触らない（外部に残る古いリンクの受け皿。消すと古いリンクが全部「ページが見つかりません」になる） |

---

## 5. 外部サービス

| サービス | 用途 | ホームページ側の設定 | 注意 |
|---|---|---|---|
| Pages CMS（pagescms.org） | 文字・料金・ブログ・画像の編集画面 | `.pages.yml` | 編集画面で保存すると、すぐ本番に出る（下書き機能なし） |
| SSGform | お問い合わせフォームの送信先 | `contact.html`（送信後は `thanks.html`） | 無料枠は**月100件**。超えると受け付けなくなる。項目は `content/form.json`（編集画面から変えられる） |
| LINE公式アカウント | 予約・相談の窓口 | リンク `https://page.line.me/?accountId=235yilws`（全ページ共通） | — |
| 電話 | 予約・相談 | `06-7493-0993`（全ページ共通） | 変える時は全ページ・構造化データ（`<script type="application/ld+json">`）も一緒に |
| Google アナリティクス（GA4） | アクセス数 | 測定ID `G-ZFKLS69SQD`（各ページの head） | 消さない |
| Google Search Console | 検索での表示状況 | 所有確認ファイル `googleed253135e72c7780.html`・`sitemap.xml` を登録済み | ファイルを消さない |

- ⚠️ `content/settings.json` の営業時間の欄は、2026-11-23 時点でどのページにも表示されていない（電話番号だけ読まれている）。営業時間を変える時は、各ページのフッターなどを直接直す。
- 表示用の部品：Tailwind CSS（CDN から読込）・BudouX（日本語の改行を整える・`js/budoux-ja.min.js`）。
- GitHub Pages の仕様で、サーバー側のセキュリティ設定（セキュリティヘッダー）は付けられない。

---

## 6. ファイルの地図

| ファイル | 中身 |
|---|---|
| `index.html` | トップページ |
| `service.html` | サービス一覧と各サービスの詳細（料金・FAQ を含む） |
| `about.html`・`company.html` | 私たちについて・会社概要 |
| `blog.html`・`blog/` | ブログ一覧・記事（**自動生成**。直すのは `content/blog/*.md`） |
| `contact.html`・`thanks.html` | お問い合わせ・送信後のお礼ページ |
| `privacy.html` | プライバシーポリシー |
| `content/*.json`・`content/modals/` | 編集画面で直せる文字・料金のデータ |
| `content/blog/`・`content/blog-categories/` | ブログ記事（マークダウン）とカテゴリ |
| `content/extra-services/` | 編集画面の「＋ サービスを追加」で作ったサービス |
| `images/` | 画像（約130枚） |
| `js/services-order.js` | サービスカードの並び替え・追加サービスの表示 |
| `robots.txt`・`sitemap.xml`・`llms.txt` | 検索エンジン・AI検索向け（`sitemap.xml` は自動生成。`llms.txt` はブログ記事一覧の部分だけ自動） |
| `check_site.py`・`.githooks/pre-push`・`.gitattributes` | 反映前の自動点検（反映の直前に必ず走る）と、Windows でも動かすための設定 |
| `.claude/CLAUDE.md`・`.claude/page-guide.md`・`.claude/site-info.md` | Claude Code 向けの編集ルール・ページ追加の手順・この構成情報 |
| `CNAME` | 独自ドメインの設定（🔴触らない） |
| `_backup_blog_cms/`・`_backup_pages_yml_before_group.yml` | 制作時の控え。表示には使われていない（触らない・直さない） |

---

## 7. 自動テスト（`tests/`）

仕組みのファイルを変えた時に、壊していないかを確かめるためのテスト。ホームページの表示には使われない。

| ファイル | 確かめる対象 |
|---|---|
| `tests/test_check_site.py` | 反映前の自動点検（`check_site.py`） |
| `tests/test_blog_categories.py`・`tests/test_blog_frontmatter.py` | ブログの作り直し（`build_blog.py`） |
| `tests/test_blog_ga.py` | ブログのページにアクセス計測（GA4）のタグと、その許可設定が入っていること |
| `tests/test_services_menu.py` | 追加サービスの左メニュー（`build_services_menu.py`・`.pages.yml`） |
| `tests/test_services_order.py` | サービスカードの並び替え・追加サービスの表示（`js/services-order.js`） |

- 流し方：`python3 -m pytest tests -q`（使い方は `.claude/CLAUDE.md` §7）。
- `node`（JavaScript を動かす道具）や `yaml`（設定を読む部品）が無い環境では、一部が「skipped」になる。
