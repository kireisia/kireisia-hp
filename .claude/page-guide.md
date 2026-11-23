# page-guide.md — ページを足す時の手順と、見た目の決まり

作成：2026-11-23（今のサイトの実物から書き出したもの）
新しいページを作る時・見た目を変える時に、Claude Code が作業の前に読む。

---

## 1. ページを足す前に、担当者に聞くこと（1つずつ）

1. **何のページか**（例：採用・料金表・キャンペーン・エリア紹介）と、載せたい内容
2. **載せる文章・写真は手元にあるか**（無い物を作らない。お客様の声・実績の数字は実物だけ）
3. **どこからそのページへ行けるようにするか**
   - A：トップなど特定のページにボタン・リンクを1つ置く（おすすめ。変える所が少なく安全）
   - B：全ページの上のメニュー・下のページ一覧に足す（**全ページ＋ブログの型を直す**ので範囲が広い。下の §4）
4. **検索に出したいか**（出したくない確認用のページは `noindex` にして sitemap に入れない）

- ブログ記事を足したいだけなら、ページを作らない。`content/blog/` にマークダウンを1つ足す（編集画面 Pages CMS でもできる）。
- サービスを足したいだけなら、編集画面の「＋ サービスを追加」で足せる（ページを作らない）。

---

## 2. ページの作り方（この順番）

1. **`company.html` を複製して、新しい名前で保存する**（一番シンプルなページ。ヘッダー・フッター・固定ボタンが全部入っている）
   - ファイル名は**半角の英小文字・数字・ハイフンだけ**（例：`price.html`・`recruit-guide.html`）。日本語・空白は使わない
2. **頭の部分（`<head>`）を、新しいページ用に書き換える**
   - 自動点検が止めるのは：`<title>`・説明文・`viewport`・安全設定・アクセス計測が無い／`canonical`・`og:url` が別のページを指している、だけ。**`og:title`・`twitter:`・構造化データの中身が複製元のままでも点検は通ってしまう**ので、下の表を1行ずつ自分で確かめる（全ページ共通の上のメニューと一番下のフッターに「会社概要」「company.html」が出るのは正常。それ以外の所に残っていないかを見る。最後に、新しいファイルの中を複製元のページ名・ファイル名で検索して、残っていないか見る）

| 直す所 | 内容 |
|---|---|
| `<title>` | `ページ名｜株式会社キレイシア` の形（複製元に付いている「（大阪のハウスクリーニング）」は付けなくてよい） |
| `meta name="description"` | このページの説明（80〜120字ほど） |
| `link rel="canonical"` | `https://www.kireisia.co.jp/新しいファイル名.html` |
| `og:url`・`og:title`・`og:description` | 上と同じ内容に |
| `twitter:title`・`twitter:description` | 上と同じ内容に |
| 構造化データ（`application/ld+json`） | 1つ目の `@type` を `WebPage` にして、`name`・`description`・`url` をこのページに（`isPartOf`・`about` はそのまま残す）。パンくず（`BreadcrumbList`）の2番目をこのページに。種類は必要な時だけ増やす（質問と答えのページで `FAQPage` を足す時は、**ページに実際に表示している質問と答えと同じ文**だけを入れる。表示していない内容を入れない）。`Product`・`Review`・`AggregateRating` は足さない |
| そのまま残す物 | `viewport`・`Content-Security-Policy`・アクセス計測（`G-ZFKLS69SQD` の2行）・フォントの読込・Tailwind の読込・`@theme` の色の定義・ファビコン |

3. **ヘッダーの「今いるページ」の色を直す**：複製元（会社概要）の項目が青太字（`text-primary font-bold`）になっている。**すぐ隣の項目と同じ書き方**に戻す（PC用メニューとスマホ用メニューの2か所。2か所で書き方が違うので、それぞれの隣を見て合わせる）
4. **`<main>` の中身を書き換える**（§3 の決まりに合わせる）。複製元だけの部分（会社概要の表・「企業理念ページへの案内」・地名入りの説明文）は消す。聞いていない事実（所要時間・支払い方法・料金など）を足さない
5. **sitemap に入れる**（検索に出すページだけ）：`build_blog.py` の `MAIN_PAGES` に1行足す → `python3 build_blog.py` を実行（`sitemap.xml` が作り直される）
   - 例：`("price.html", "monthly", "0.7"),  # 料金表`
   - `build_blog.py` は仕組みのファイル。**この1行を足すことだけ**は、担当者に「検索に出すための登録です」と伝えて OK をもらえば行ってよい。OK の後に `python3 check_site.py --confirm-protected build_blog.py` を1回実行して記録する（記録しないと点検が ❌ で止める）
   - 実行後、`git status` で `blog/`・`blog.html` に意図しない変更が出ていないか見る（`sitemap.xml` の主要ページの日付が全部今日になるのは正常）
6. **`llms.txt`（AI検索向けの案内）にページを1行足す**（ブログ記事一覧の部分は自動なので触らない。それ以外の所に足す）
7. **リンクを置く**（§1 の 3 で決めた場所）。A の時の置き場所の目安：トップページの一番下の「お問い合わせ」のボタンの下に文字のリンクを1つ、または内容が近いセクションの最後
8. **点検する**：`python3 check_site.py` → `python3 check_site.py --shots 新しいファイル名.html リンクを置いたページ.html`（スマホ幅・PC幅の画像と、横はみ出しの測定。画像はページの一番下まで写る）。画像を自分で見て、崩れ・重なり・はみ出しを直す
9. 担当者に手元の表示を見てもらう → OK → 反映 → 本番で確認（`.claude/CLAUDE.md` §2 の流れ）

---

## 3. 見た目の決まり（今のサイトと同じにする）

### 色（`@theme` で定義済みの名前を使う。新しい色を足さない）
| 名前 | 色 | 使いどころ |
|---|---|---|
| `primary`／`primary-dark` | 水色 `#5BBEE5`／`#3A9FCA` | 見出しの飾り・ボタン・リンク |
| `primary-light`／`primary-50` | 薄い水色 `#E8F4FD`／`#F0F9FF` | セクションの背景 |
| `accent`／`accent-dark` | 緑 `#06C755`／`#05A847` | **LINE のボタンだけ** |
| `warm`／`warm-light` | オレンジ `#F5A623`／`#FFF8EC` | 注意・キャンペーンの強調 |
| `text-main`／`text-sub`／`text-light` | 濃い灰〜薄い灰 | 本文の文字 |
| `surface`・`border` | `#FAFCFE`・`#E2EAF0` | 薄い背景・枠線 |

- ロゴの色・形は変えない。

### 文字
- 本文：`font-sans`（Zen Kaku Gothic New）／見出し：`font-display font-bold`（Noto Sans JP）
- 明朝体（`.font-mincho`）は、代表名・企業理念の題名だけ

### 型（そのまま写して使う）
```html
<!-- ページの最初の見出し（ヘッダーが固定なので上の余白 pt-28 sm:pt-32 が必要） -->
<section class="pt-28 sm:pt-32 pb-10 sm:pb-12 bg-gradient-to-b from-primary-50 to-white">
  <div class="max-w-4xl mx-auto px-6 sm:px-10 lg:px-16 text-center">
    <span class="inline-block text-primary text-sm font-bold tracking-widest uppercase mb-3">ENGLISH LABEL</span>
    <h1 class="font-display font-bold text-3xl sm:text-4xl lg:text-5xl tracking-tight text-text-main">ページ名</h1>
    <p class="mt-5 text-sm sm:text-base text-text-sub leading-relaxed">このページの説明。</p>
  </div>
</section>

<!-- 2つ目以降のセクション（背景は bg-white と bg-surface を交互に） -->
<section class="py-16 sm:py-24 bg-white">
  <div class="max-w-6xl mx-auto px-6 sm:px-10 lg:px-16">
    <div class="text-center mb-12">
      <span class="inline-block text-primary text-sm font-bold tracking-widest uppercase mb-3">LABEL</span>
      <h2 class="font-display font-bold text-3xl sm:text-4xl tracking-tight text-text-main mb-4">見出し</h2>
    </div>
    <!-- 中身 -->
  </div>
</section>

<!-- 表・一覧の箱 -->
<div class="bg-surface rounded-2xl overflow-hidden ring-1 ring-border"> ... </div>
```
- 横幅：文章中心のページは `max-w-4xl`、カードが並ぶページは `max-w-6xl`。左右の余白は `px-6 sm:px-10 lg:px-16`
- ページの最後（フッターの前）には、既存の「お問い合わせCTA」（LINE と電話のボタン）をそのまま置く
- ページの一番下の「フローティングLINEボタン」「スマホ専用 下部固定CTAバー」「モバイルメニューの処理」は消さない

### やってはいけない見た目
- スマホ幅（390px・320px）で横にはみ出す・文字が重なる
- 12px より小さい文字／薄い灰色の文字を白地の本文に使う
- 画像に `alt`（説明）を付けない／500KB を超える画像を入れる
- 文字を画像にして載せる（検索に出ない・スマホで読めない）

---

## 4. 全ページのメニューに足す時（範囲が広いので、担当者に範囲を伝えてから）

メニューとページ一覧は、**各ページに同じ物が書いてある**（共通ファイルではない）。直す所：

| 場所 | 対象 |
|---|---|
| 上のメニュー（PC用）・スマホ用メニュー・下の「ページ一覧」 | `index.html`・`service.html`・`about.html`・`company.html`・`contact.html`・`privacy.html`・`thanks.html`＋新しいページ |
| ブログの一覧・記事 | `build_blog.py` の中のヘッダー・フッターの型（直した後に `python3 build_blog.py`）。`blog.html`・`blog/` は直接直さない |

- 上のメニューは今7項目で、PCの幅にほぼ一杯。**足すなら下の「ページ一覧」だけ**をまず提案する
- 直したら、全ページで `python3 check_site.py --shots ページ名` を1ページずつ実行して、メニューが崩れていないか見る

---

## 5. 外部の部品を足す時の注意（安全設定＝Content-Security-Policy）

各ページの頭に、読み込んでよい外部サイトの一覧（`Content-Security-Policy`）がある。
一覧に無いサイトの**プログラム（script）・フォント・埋め込み（地図・動画・SNS）**は、ブラウザが止めるので表示されない。

- 今、許可されている物：自分のサイト／jsDelivr（Tailwind）／Google アナリティクス／Google フォント／画像は https なら全部
- 地図・YouTube・Instagram などを埋め込みたい時は、この一覧を変える必要がある。担当者に「外部の部品を読み込めるように、安全設定を少し広げます」と伝えて OK をもらい、**埋め込むページだけ・必要なサイトだけ**を足す（`*` などで全部許可しない）。足した後、手元の表示でコンソールにエラーが無いことと、埋め込みが実際に表示されることを確かめる
- 手元の表示で、ブラウザのコンソールに `Content Security Policy` の赤いエラーが出ていないかを必ず見る
