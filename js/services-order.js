/*
 * サービス一覧ページ（service.html）：カードの並び順と「追加サービス」の表示
 * 作成: 2026-11-11
 *
 * データの出どころ: content/modals/<サービス>.json の card（各サービスの画面で編集）＋ content/services.json
 *   - 既存12種の各カード … order（表示順の数字）
 *   - ousama.order       … 空気の王様フィルター（HTML固定カード）の表示順
 *   - extra[]            … 編集画面から追加したサービス
 *
 * 安全設計:
 *   - services.json が読めない／壊れていても、HTMLに書かれた今のカードはそのまま残る
 *   - 入力値は textContent で入れる（HTMLとして解釈しない＝スクリプト混入を防ぐ）
 *   - 純粋な計算（並び順・入力の整理）は Node でテストできるよう分けてある
 */
(function (root) {
  'use strict';

  // 数字（または数字だけの文字列）なら true。空白・true/false などは数字扱いしない
  function isFiniteNumber(value) {
    if (typeof value === 'number') return isFinite(value);
    if (typeof value !== 'string' || value.trim() === '') return false;
    return isFinite(Number(value));
  }

  // キャンセル料金の強調色（既存サービスと同じ3色：黒・オレンジ・赤）
  const CANCELLATION_COLORS = ['main', 'warm', 'red'];

  function cleanText(value) {
    return typeof value === 'string' ? value.trim() : '';
  }

  // 画像パスは「サイト内の相対パス」か「https://」だけ受け付ける
  function cleanImage(value) {
    const v = cleanText(value);
    if (!v) return '';
    if (/^https:\/\//i.test(v)) return v;
    if (/^[a-z][a-z0-9+.-]*:/i.test(v)) return ''; // javascript: data: など
    return v.replace(/^\/+/, '');
  }

  /**
   * 並び順を決める
   * entries: [{key, order}]（HTML上の並び＝配列の順）
   * ルール: 数字が入っているものを小さい順 → 同じ数字はHTML上の順 → 数字なしは最後（HTML上の順）
   */
  function sortKeys(entries) {
    return entries
      .map(function (entry, index) {
        return { key: entry.key, order: entry.order, index: index };
      })
      .sort(function (a, b) {
        const aHas = isFiniteNumber(a.order);
        const bHas = isFiniteNumber(b.order);
        if (aHas && bHas && Number(a.order) !== Number(b.order)) {
          return Number(a.order) - Number(b.order);
        }
        if (aHas !== bHas) return aHas ? -1 : 1;
        return a.index - b.index;
      })
      .map(function (entry) {
        return entry.key;
      });
  }

  /** 文字の一覧から空の行を取り除く */
  function cleanStrings(list) {
    return Array.isArray(list) ? list.map(cleanText).filter(function (text) { return text; }) : [];
  }

  /** {name, price} などの行の一覧から、全部空の行を取り除く */
  function cleanRows(list, keys) {
    if (!Array.isArray(list)) return [];
    return list
      .filter(function (row) { return row && typeof row === 'object'; })
      .map(function (row) {
        const cleaned = {};
        keys.forEach(function (key) { cleaned[key] = cleanText(row[key]); });
        return cleaned;
      })
      .filter(function (row) { return keys.some(function (key) { return row[key]; }); });
  }

  /** 追加サービスの入力を整理する（タイトルが空の行は無視） */
  function normalizeExtras(list) {
    if (!Array.isArray(list)) return [];
    const result = [];
    list.forEach(function (item) {
      if (!item || typeof item !== 'object') return;
      const title = cleanText(item.title);
      if (!title) return;
      const priceRows = cleanRows(item.detail_price_list, ['name', 'price']);
      const notes = cleanStrings(item.detail_notes);
      const lead = cleanText(item.detail_lead);
      const concerns = cleanStrings(item.concerns_list);
      const options = cleanRows(item.options_list, ['name', 'price']);
      const points = cleanStrings(item.points_list);
      // FAQ は質問が空の行は出さない（答えだけでは意味が通らないため）
      const faqs = cleanRows(item.faq_list, ['question', 'answer']).filter(function (row) { return row.question; });
      // Before/After は画像が1枚も無い行・危ない画像パスは出さない
      const slides = cleanRows(item.before_after_slides, ['caption', 'before_image', 'before_alt', 'after_image', 'after_alt'])
        .map(function (row) {
          return {
            caption: row.caption,
            beforeImage: cleanImage(row.before_image),
            beforeAlt: row.before_alt,
            afterImage: cleanImage(row.after_image),
            afterAlt: row.after_alt,
          };
        })
        .filter(function (row) { return row.beforeImage || row.afterImage; });
      const requests = cleanStrings(item.customer_request_list);
      const bookingNotes = cleanStrings(item.booking_notes_list);
      // キャンセル料金：期間か料率のどちらかがある行だけ。色は既存サービスと同じ3色だけ受け付ける
      const cancellations = cleanRows(item.cancellation_list, ['period', 'rate', 'color'])
        .filter(function (row) { return row.period || row.rate; })
        .map(function (row) {
          return {
            period: row.period,
            rate: row.rate,
            color: CANCELLATION_COLORS.indexOf(row.color) >= 0 ? row.color : 'main',
          };
        });
      // ＋項目追加（項目名と記述）：どちらかが入っていれば出す
      const customSections = cleanRows(item.custom_sections, ['heading', 'body']);
      const extra = {
        key: 'extra-' + (result.length + 1),
        title: title,
        image: cleanImage(item.image),
        description: cleanText(item.description),
        price: cleanText(item.price),
        badge: cleanText(item.badge),
        order: isFiniteNumber(item.order) ? Number(item.order) : null,
        detailLead: lead,
        detailPriceTitle: cleanText(item.detail_price_title),
        detailPriceNote: cleanText(item.detail_price_note),
        detailPriceList: priceRows,
        detailNotes: notes,
        concernsTitle: cleanText(item.concerns_title),
        concernsList: concerns,
        optionsTitle: cleanText(item.options_title),
        optionsList: options,
        pointsTitle: cleanText(item.points_title),
        pointsList: points,
        faqTitle: cleanText(item.faq_title),
        faqList: faqs,
        concernsOutro: cleanText(item.concerns_outro),
        pointsIntro: cleanText(item.points_intro),
        beforeAfterTitle: cleanText(item.before_after_title),
        beforeAfterSlides: slides,
        customerRequestTitle: cleanText(item.customer_request_title),
        customerRequestList: requests,
        bookingNotesTitle: cleanText(item.booking_notes_title),
        bookingNotesList: bookingNotes,
        cancellationTitle: cleanText(item.cancellation_title),
        cancellationList: cancellations,
        cancellationNote: cleanText(item.cancellation_note),
        customSections: customSections,
      };
      // 見出し・締めの一文・リード文だけ入っていても中身が空なら「詳細」ボタンは出さない
      extra.hasDetail = Boolean(lead || priceRows.length || notes.length || concerns.length ||
        options.length || points.length || faqs.length || slides.length || requests.length ||
        bookingNotes.length || cancellations.length || customSections.length);
      result.push(extra);
    });
    return result;
  }

  /**
   * 追加サービス1件のファイル（content/extra-services/*.json）を、カードを作る形に直す
   * 下書き（published が false）は null を返す＝ページに出さない
   */
  function fromExtraFile(data) {
    if (!data || typeof data !== 'object') return null;
    if (data.published === false) return null;
    const card = data.card && typeof data.card === 'object' ? data.card : {};
    return {
      title: data.title,
      image: card.image,
      badge: card.badge,
      description: card.description,
      price: card.price,
      order: card.order,
      detail_lead: data.detail_lead,
      detail_price_title: data.detail_price_title,
      detail_price_note: data.detail_price_note,
      detail_price_list: data.detail_price_list,
      detail_notes: data.detail_notes,
      concerns_title: data.concerns_title,
      concerns_list: data.concerns_list,
      options_title: data.options_title,
      options_list: data.options_list,
      points_title: data.points_title,
      points_list: data.points_list,
      faq_title: data.faq_title,
      faq_list: data.faq_list,
      concerns_outro: data.concerns_outro,
      points_intro: data.points_intro,
      before_after_title: data.before_after_title,
      before_after_slides: data.before_after_slides,
      customer_request_title: data.customer_request_title,
      customer_request_list: data.customer_request_list,
      booking_notes_title: data.booking_notes_title,
      booking_notes_list: data.booking_notes_list,
      cancellation_title: data.cancellation_title,
      cancellation_list: data.cancellation_list,
      cancellation_note: data.cancellation_note,
      custom_sections: data.custom_sections,
    };
  }

  /**
   * カードの値を1つにまとめる
   * servicesData   : content/services.json（空気の王様・追加サービス。古い形なら12種のカードも入っている）
   * modalDataByKey : {aircon: content/modals/aircon.json の中身, ...}
   * 各サービスのファイルに card があればそれを使い、無ければ services.json 側の値を残す（移行中の安全策）
   */
  function mergeCards(servicesData, modalDataByKey) {
    const merged = {};
    if (servicesData && typeof servicesData === 'object') {
      Object.keys(servicesData).forEach(function (key) {
        merged[key] = servicesData[key];
      });
    }
    if (modalDataByKey && typeof modalDataByKey === 'object') {
      Object.keys(modalDataByKey).forEach(function (key) {
        const modalData = modalDataByKey[key];
        if (modalData && typeof modalData === 'object' && modalData.card && typeof modalData.card === 'object') {
          merged[key] = modalData.card;
        }
      });
    }
    return merged;
  }

  // ---------------- ここから下はブラウザ専用（画面の組み立て） ----------------

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function arrowIcon() {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('class', 'w-4 h-4');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    svg.setAttribute('aria-hidden', 'true');
    const path = document.createElementNS(ns, 'path');
    path.setAttribute('d', 'M5 12h14M12 5l7 7-7 7');
    svg.appendChild(path);
    return svg;
  }

  function closeIcon() {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('class', 'w-5 h-5 text-text-light');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    svg.setAttribute('aria-hidden', 'true');
    const path = document.createElementNS(ns, 'path');
    path.setAttribute('d', 'M18 6L6 18M6 6l12 12');
    svg.appendChild(path);
    return svg;
  }

  function buildCard(extra) {
    const card = el('div', 'service-card bg-card rounded-2xl ring-1 ring-border overflow-hidden group');
    card.setAttribute('data-service-key', extra.key);

    if (extra.image) {
      const imageWrap = el('div', 'relative h-48 sm:h-52 overflow-hidden');
      const img = el('img', 'w-full h-full object-cover group-hover:scale-105 transition-transform duration-500');
      img.src = extra.image;
      img.alt = extra.title;
      img.loading = 'lazy';
      imageWrap.appendChild(img);
      if (extra.badge) {
        const badgeWrap = el('div', 'absolute top-3 left-3');
        badgeWrap.appendChild(el('span', 'inline-flex items-center bg-text-main text-white text-xs font-bold px-3 py-1.5 rounded-full', extra.badge));
        imageWrap.appendChild(badgeWrap);
      }
      card.appendChild(imageWrap);
    }

    const body = el('div', 'p-6');
    body.appendChild(el('h3', 'font-display font-bold text-lg tracking-tight mb-2', extra.title));
    if (extra.description) {
      body.appendChild(el('p', 'text-sm text-text-sub leading-relaxed mb-4', extra.description));
    }
    const bottom = el('div', 'flex items-center justify-between');
    bottom.appendChild(el('span', 'text-primary font-bold text-sm', extra.price || 'お見積り'));
    if (extra.hasDetail) {
      const button = el('button', 'inline-flex items-center gap-1 text-sm font-medium text-primary hover:text-primary-dark transition-colors cursor-pointer', '詳細');
      button.type = 'button';
      button.setAttribute('data-modal', extra.key);
      button.appendChild(arrowIcon());
      bottom.appendChild(button);
    }
    body.appendChild(bottom);
    card.appendChild(body);
    return card;
  }

  // ページにある部品（<template>）で箇条書きの1行を作る。部品が無ければ素の行にする
  function listItem(templateId, text) {
    const template = document.getElementById(templateId);
    if (template && template.content) {
      const clone = template.content.firstElementChild.cloneNode(true);
      const target = clone.querySelector('[data-content]');
      if (target) {
        target.textContent = text;
        return clone;
      }
    }
    return el('li', 'text-sm text-text-sub', text);
  }

  // 料金表（行が1つも無ければ何も出さない）
  function appendPriceTable(container, title, note, rows) {
    if (!rows.length) return;
    const titleRow = el('div', 'flex items-baseline gap-3 mb-3');
    titleRow.appendChild(el('h3', 'font-display font-bold text-base', title));
    if (note) titleRow.appendChild(el('span', 'text-[10px] text-text-light', note));
    container.appendChild(titleRow);
    const table = el('div', 'rounded-xl ring-1 ring-border overflow-hidden mb-6');
    rows.forEach(function (row) {
      const line = el('div', 'price-row flex justify-between items-center px-5 py-3.5 text-sm');
      line.appendChild(el('span', 'text-text-main font-medium', row.name));
      line.appendChild(el('span', 'text-primary font-bold', row.price));
      table.appendChild(line);
    });
    container.appendChild(table);
  }

  // 見出し＋箱入りの箇条書き（お客様へお願い・ご予約に関する注意事項）。行が無ければ何も出さない
  function appendNoteBox(container, title, items, boxClass, templateId) {
    if (!items.length) return;
    container.appendChild(el('h3', 'font-display font-bold text-base mb-3', title));
    const box = el('div', boxClass);
    const ul = el('ul', 'space-y-2');
    items.forEach(function (text) { ul.appendChild(listItem(templateId, text)); });
    box.appendChild(ul);
    container.appendChild(box);
  }

  // Before/After：既存サービスと同じ部品。ページの initBeforeAfterCarousels が説明と点の切り替えを受け持つ
  function appendBeforeAfter(container, extra) {
    container.appendChild(el('h3', 'font-display font-bold text-base mb-3', extra.beforeAfterTitle || 'Before / After'));
    const gallery = el('div', 'mb-6');
    const slider = el('div', 'flex overflow-x-auto snap-x snap-mandatory rounded-xl');
    slider.style.scrollbarWidth = 'none';
    // 初期化の目印（ページ側は data-cms-list が before_after_slides で終わる枠を探す）
    slider.setAttribute('data-cms-list', extra.key + '.before_after_slides');
    extra.beforeAfterSlides.forEach(function (slide) {
      const slideNode = el('div', 'ba-slide flex-shrink-0 w-full snap-center');
      slideNode.setAttribute('data-caption', slide.caption);
      const grid = el('div', 'grid grid-cols-2 gap-2');
      [['Before', slide.beforeImage, slide.beforeAlt, 'rounded-l-xl', 'top-2 left-2 bg-black/50'],
        ['After', slide.afterImage, slide.afterAlt, 'rounded-r-xl', 'top-2 right-2 bg-primary']].forEach(function (side) {
        const half = el('div', 'relative ' + side[3] + ' overflow-hidden bg-surface');
        half.appendChild(el('span', 'absolute ' + side[4] + ' text-white text-[10px] font-bold px-2 py-0.5 rounded z-10', side[0]));
        if (side[1]) {
          const img = el('img', 'w-full aspect-[4/3] object-cover');
          img.src = side[1];
          img.alt = side[2] || (extra.title + ' ' + side[0]);
          img.loading = 'lazy';
          half.appendChild(img);
        } else {
          half.appendChild(el('div', 'w-full aspect-[4/3]'));
        }
        grid.appendChild(half);
      });
      slideNode.appendChild(grid);
      slider.appendChild(slideNode);
    });
    gallery.appendChild(slider);
    gallery.appendChild(el('p', 'ba-caption text-center text-xs text-text-sub mt-2', extra.beforeAfterSlides[0].caption));
    if (extra.beforeAfterSlides.length > 1) {
      const dots = el('div', 'ba-dots-container flex justify-center gap-1.5 mt-2');
      extra.beforeAfterSlides.forEach(function (slide, index) {
        dots.appendChild(el('span', 'ba-dot w-2 h-2 rounded-full transition-all ' + (index === 0 ? 'bg-primary' : 'bg-border')));
      });
      gallery.appendChild(dots);
    }
    container.appendChild(gallery);
  }

  // キャンセル料金の表（色は main＝黒・warm＝オレンジ・red＝赤）
  function appendCancellation(container, extra) {
    const colorClass = { main: 'text-text-main', warm: 'text-warm', red: 'text-red-500' };
    container.appendChild(el('h3', 'font-display font-bold text-base mb-3', extra.cancellationTitle || 'キャンセル料金'));
    const table = el('div', 'rounded-xl ring-1 ring-border overflow-hidden ' + (extra.cancellationNote ? 'mb-2' : 'mb-6'));
    extra.cancellationList.forEach(function (row) {
      const line = el('div', 'price-row flex justify-between items-center px-5 py-3 text-sm');
      line.appendChild(el('span', 'text-text-main font-medium', row.period));
      const right = el('span', 'text-text-sub', row.rate ? '予約金額の' : '');
      right.appendChild(el('strong', colorClass[row.color], row.rate));
      line.appendChild(right);
      table.appendChild(line);
    });
    container.appendChild(table);
    if (extra.cancellationNote) {
      container.appendChild(el('p', 'text-[10px] text-text-light mb-6', extra.cancellationNote));
    }
  }

  function buildModal(extra) {
    const overlay = el('div', 'modal-overlay fixed inset-0 z-[60] flex items-end sm:items-center justify-center bg-black/50 backdrop-blur-sm');
    overlay.id = 'modal-' + extra.key;
    overlay.setAttribute('aria-hidden', 'true');
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-label', extra.title + '詳細');

    const panel = el('div', 'modal-panel bg-white w-full sm:max-w-2xl sm:rounded-2xl rounded-t-2xl max-h-[90vh] overflow-y-auto shadow-2xl');
    const header = el('div', 'sticky top-0 bg-white z-10 flex items-center justify-between px-6 py-4 border-b border-border');
    header.appendChild(el('h2', 'font-display font-bold text-lg tracking-tight', extra.title));
    const closeButton = el('button', 'modal-close w-8 h-8 flex items-center justify-center rounded-full hover:bg-surface transition-colors');
    closeButton.type = 'button';
    closeButton.setAttribute('aria-label', '閉じる');
    closeButton.appendChild(closeIcon());
    header.appendChild(closeButton);
    panel.appendChild(header);

    const content = el('div', 'p-6 sm:p-8');
    if (extra.image) {
      const img = el('img', 'w-full rounded-xl mb-6 object-cover');
      img.src = extra.image;
      img.alt = extra.title;
      img.loading = 'lazy';
      content.appendChild(img);
    }
    // ① お悩みリスト（今の13サービスと同じ「！」付きの箱）
    if (extra.concernsList.length) {
      const box = el('div', 'bg-surface rounded-xl p-5 mb-6 ring-1 ring-border');
      box.appendChild(el('p', 'font-display font-bold text-sm text-text-main mb-3', extra.concernsTitle || 'こんなお悩みございませんか？'));
      const ul = el('ul', 'space-y-2');
      extra.concernsList.forEach(function (text) { ul.appendChild(listItem('tpl-concern-item-warm', text)); });
      box.appendChild(ul);
      content.appendChild(box);
      // お悩みの締めの一文（今の13サービスと同じ青の中央寄せ）
      if (extra.concernsOutro) {
        const outro = el('div', 'text-center mb-6');
        outro.appendChild(el('p', 'font-display font-bold text-base text-primary', extra.concernsOutro));
        content.appendChild(outro);
      }
    }
    if (extra.detailLead) {
      content.appendChild(el('p', 'text-sm text-text-sub leading-relaxed mb-6 whitespace-pre-line', extra.detailLead));
    }
    // ② 料金表・③ オプション（同じ表の形）
    appendPriceTable(content, extra.detailPriceTitle || '料金', extra.detailPriceNote, extra.detailPriceList);
    appendPriceTable(content, extra.optionsTitle || 'オプション', '', extra.optionsList);
    // ④ キレイシアのポイント（チェック付きの箱）
    if (extra.pointsList.length) {
      content.appendChild(el('h3', 'font-display font-bold text-base mb-3', extra.pointsTitle || 'キレイシアのポイント'));
      const box = el('div', 'bg-primary-50 rounded-xl p-5 mb-6');
      if (extra.pointsIntro) box.appendChild(el('p', 'font-bold text-sm text-primary mb-3', extra.pointsIntro));
      const ul = el('ul', 'space-y-2');
      extra.pointsList.forEach(function (text) { ul.appendChild(listItem('tpl-point-item', text)); });
      box.appendChild(ul);
      content.appendChild(box);
    }
    // ⑤ Before/After（左右にスワイプ・下に説明と点）
    if (extra.beforeAfterSlides.length) {
      appendBeforeAfter(content, extra);
    }
    // ⑥ お客様へお願い（オレンジの箱）・⑦ ご予約に関する注意事項（灰色の箱）
    appendNoteBox(content, extra.customerRequestTitle || 'お客様へお願い', extra.customerRequestList,
      'bg-warm-light rounded-xl p-5 mb-6', 'tpl-warning-item-warm');
    appendNoteBox(content, extra.bookingNotesTitle || 'ご予約に関する注意事項', extra.bookingNotesList,
      'bg-surface rounded-xl p-5 mb-6 ring-1 ring-border', 'tpl-warning-item-primary');
    // ⑧ よくある質問（押すと開く）
    if (extra.faqList.length) {
      content.appendChild(el('h3', 'font-display font-bold text-base mb-3', extra.faqTitle || 'よくある質問'));
      const list = el('div', 'space-y-2 mb-6');
      extra.faqList.forEach(function (row) {
        const details = el('details', 'group bg-surface rounded-lg ring-1 ring-border');
        details.appendChild(el('summary', 'cursor-pointer px-4 py-3 text-xs font-medium text-text-main hover:text-primary transition-colors', row.question));
        details.appendChild(el('div', 'px-4 pb-3 text-xs text-text-sub leading-relaxed whitespace-pre-line', row.answer));
        list.appendChild(details);
      });
      content.appendChild(list);
    }
    // ⑨ キャンセル料金（今の13サービスと同じ表）
    if (extra.cancellationList.length) {
      appendCancellation(content, extra);
    }
    if (extra.detailNotes.length) {
      const noteBox = el('div', 'bg-warm-light rounded-lg p-3 mb-6');
      const ul = el('ul', 'space-y-1');
      extra.detailNotes.forEach(function (note) {
        ul.appendChild(el('li', 'text-xs text-text-sub leading-relaxed', note));
      });
      noteBox.appendChild(ul);
      content.appendChild(noteBox);
    }
    // ⑩ ＋項目追加（項目名と記述）：詳細画面の一番下に、入れた順で出す
    extra.customSections.forEach(function (section) {
      if (section.heading) content.appendChild(el('h3', 'font-display font-bold text-base mb-3', section.heading));
      if (section.body) content.appendChild(el('p', 'text-sm text-text-sub leading-relaxed mb-6 whitespace-pre-line', section.body));
    });
    panel.appendChild(content);
    overlay.appendChild(panel);

    function close() {
      if (typeof root.closeModal === 'function') {
        root.closeModal(overlay);
      } else {
        overlay.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = '';
      }
    }
    closeButton.addEventListener('click', close);
    overlay.addEventListener('click', function (event) {
      if (event.target === overlay) close();
    });
    return overlay;
  }

  function open(id) {
    if (typeof root.openModal === 'function') {
      root.openModal(id);
      return;
    }
    const modal = document.getElementById('modal-' + id);
    if (modal) {
      modal.setAttribute('aria-hidden', 'false');
      document.body.style.overflow = 'hidden';
    }
  }

  // 既存カードの「名前」を読み取る（services.json のキー。空気の王様は "ousama"）
  function keyOfCard(card) {
    if (card.getAttribute('data-service-key')) return card.getAttribute('data-service-key');
    const img = card.querySelector('img[data-cms-field^="services."]');
    if (img) {
      const match = img.getAttribute('data-cms-field').match(/^services\.([^.]+)\./);
      if (match) return match[1];
    }
    const button = card.querySelector('[data-modal]');
    return button ? button.getAttribute('data-modal') : '';
  }

  /** services.json の内容で、追加カードを作り、全カードとフッターを並べ替える */
  function apply(data) {
    if (!data || typeof data !== 'object') return;
    const firstCard = document.querySelector('#services .service-card');
    if (!firstCard) return;
    const grid = firstCard.parentElement;

    // 既存カード（HTMLに書かれたもの）
    const cardByKey = {};
    const modalIdByKey = {};
    const entries = [];
    Array.prototype.slice.call(grid.querySelectorAll(':scope > .service-card')).forEach(function (card) {
      const key = keyOfCard(card);
      if (!key || cardByKey[key]) return;
      card.setAttribute('data-service-key', key);
      cardByKey[key] = card;
      const button = card.querySelector('[data-modal]');
      if (button) modalIdByKey[key] = button.getAttribute('data-modal');
      const setting = data[key];
      entries.push({ key: key, order: setting && typeof setting === 'object' ? setting.order : null });
    });

    // 追加サービス
    const extras = normalizeExtras(data.extra);
    extras.forEach(function (extra) {
      const card = buildCard(extra);
      cardByKey[extra.key] = card;
      if (extra.hasDetail) {
        document.body.appendChild(buildModal(extra));
        modalIdByKey[extra.key] = extra.key;
        const button = card.querySelector('[data-modal]');
        button.addEventListener('click', function (event) {
          event.preventDefault();
          open(extra.key);
        });
      }
      entries.push({ key: extra.key, order: extra.order });
    });

    const orderedKeys = sortKeys(entries);
    orderedKeys.forEach(function (key) {
      grid.appendChild(cardByKey[key]);
    });

    // フッターの「サービス」リンクも同じ順番に
    const footerLink = document.querySelector('footer a[data-modal]');
    if (!footerLink) return;
    const nav = footerLink.parentElement;
    const linkByModal = {};
    Array.prototype.slice.call(nav.querySelectorAll(':scope > a[data-modal]')).forEach(function (link) {
      linkByModal[link.getAttribute('data-modal')] = link;
    });
    extras.forEach(function (extra) {
      if (!extra.hasDetail) return;
      const link = el('a', footerLink.className, extra.title);
      link.href = 'javascript:void(0)';
      link.setAttribute('data-modal', extra.key);
      link.addEventListener('click', function (event) {
        event.preventDefault();
        open(extra.key);
      });
      linkByModal[extra.key] = link;
    });
    orderedKeys.forEach(function (key) {
      const link = linkByModal[modalIdByKey[key]];
      if (link) nav.appendChild(link);
    });
  }

  const api = { sortKeys: sortKeys, normalizeExtras: normalizeExtras, mergeCards: mergeCards, fromExtraFile: fromExtraFile, apply: apply };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    root.KireisiaServices = api;
  }
})(typeof window !== 'undefined' ? window : this);
