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
      };
      // 見出しだけ入っていても中身が空なら「詳細」ボタンは出さない
      extra.hasDetail = Boolean(lead || priceRows.length || notes.length || concerns.length ||
        options.length || points.length || faqs.length);
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
      const ul = el('ul', 'space-y-2');
      extra.pointsList.forEach(function (text) { ul.appendChild(listItem('tpl-point-item', text)); });
      box.appendChild(ul);
      content.appendChild(box);
    }
    // ⑤ よくある質問（押すと開く）
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
    if (extra.detailNotes.length) {
      const noteBox = el('div', 'bg-warm-light rounded-lg p-3 mb-6');
      const ul = el('ul', 'space-y-1');
      extra.detailNotes.forEach(function (note) {
        ul.appendChild(el('li', 'text-xs text-text-sub leading-relaxed', note));
      });
      noteBox.appendChild(ul);
      content.appendChild(noteBox);
    }
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
