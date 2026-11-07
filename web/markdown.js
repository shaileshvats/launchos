/*
 * markdown.js - a small, safe Markdown renderer for LaunchOS.
 *
 * Safety model (model output is untrusted):
 *   - Every piece of source text is HTML-escaped BEFORE any formatting markup is
 *     applied, so raw HTML in the input can never reach the DOM as markup.
 *   - Links are only emitted for http(s) URLs and relative URLs. Anything with
 *     another scheme (javascript:, data:, vbscript:, ...) is dropped to plain text.
 *   - Images are not supported (they would trigger network requests).
 *
 * Supported: headings, paragraphs, bold, italic, strikethrough, inline code,
 * fenced code, blockquotes, horizontal rules, ordered/unordered/nested lists,
 * task lists, tables (with alignment) and links.
 *
 * Headings are demoted by two levels (# -> h3) so that rendered deliverables
 * never compete with the page's own h1/h2 structure.
 */

const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export function escapeHtml(value) {
  return String(value == null ? '' : value).replace(/[&<>"']/g, (c) => ESC[c]);
}

/** Returns the URL if it is http(s) or relative, otherwise null. */
export function safeUrl(raw) {
  const url = String(raw == null ? '' : raw).trim();
  if (/^https?:\/\//i.test(url)) return /[\u0000- \\]/.test(url) ? null : url;
  if (url.startsWith('//')) return null; // protocol-relative: could point anywhere
  if (/^[a-z][a-z0-9+.\-]*:/i.test(url)) return null; // any other scheme
  if (/[\u0000-\u001f\\]/.test(url)) return null; // control chars / backslashes
  return url;
}

/* ------------------------------------------------------------------ inline */

function emphasis(s) {
  return s
    .replace(/\*\*(?=\S)([\s\S]*?\S)\*\*/g, '<strong>$1</strong>')
    .replace(/__(?=\S)([\s\S]*?\S)__/g, '<strong>$1</strong>')
    .replace(/(^|[^*\w])\*(?=[^\s*])([\s\S]*?[^\s*])\*(?!\*)/g, '$1<em>$2</em>')
    .replace(/(^|[^_\w])_(?=[^\s_])([\s\S]*?[^\s_])_(?![_\w])/g, '$1<em>$2</em>')
    .replace(/~~(?=\S)([\s\S]*?\S)~~/g, '<del>$1</del>');
}

function inline(raw) {
  // \u0000 is our placeholder delimiter; make sure the input cannot forge one.
  let s = String(raw == null ? '' : raw).replace(/\u0000/g, '');
  const stash = [];
  const keep = (html) => {
    stash.push(html);
    return '\u0000' + (stash.length - 1) + '\u0000';
  };

  // 1. inline code (content is escaped, then protected from further formatting)
  s = s.replace(/(`+)([^`]|[^`][\s\S]*?[^`])\1(?!`)/g, (m, ticks, code) =>
    keep('<code>' + escapeHtml(code.trim()) + '</code>')
  );

  // 2. escape everything else - from here on `s` contains no raw < > " ' &
  s = escapeHtml(s);

  // 3. [text](url "title")
  s = s.replace(
    /\[([^\]\n]+)\]\(([^)\s]+)(?:\s+&quot;([^\n]*?)&quot;)?\)/g,
    (m, text, url, title) => {
      const href = safeUrl(url);
      if (href == null) return emphasis(text);
      const external = /^https?:/i.test(href);
      return keep(
        '<a href="' + href + '"' +
        (title ? ' title="' + title + '"' : '') +
        (external ? ' target="_blank" rel="noopener noreferrer"' : '') +
        '>' + emphasis(text) + '</a>'
      );
    }
  );

  // 4. bare http(s) URLs
  s = s.replace(/(^|[\s(])(https?:\/\/[^\s<]+)/g, (m, lead, url) => {
    let tail = '';
    const trail = url.match(/(?:[.,;:!?)]|&quot;|&#39;)+$/);
    if (trail) {
      tail = trail[0];
      url = url.slice(0, -tail.length);
    }
    const href = safeUrl(url);
    if (!href) return m;
    return lead + keep('<a href="' + href + '" target="_blank" rel="noopener noreferrer">' + url + '</a>') + tail;
  });

  // 5. emphasis on whatever is left
  s = emphasis(s);

  // 6. restore protected fragments (a few passes handles nesting)
  for (let i = 0; i < 4 && s.indexOf('\u0000') !== -1; i++) {
    s = s.replace(/\u0000(\d+)\u0000/g, (m, n) => stash[+n] || '');
  }
  return s.replace(/\u0000/g, '');
}

/* ------------------------------------------------------------------ blocks */

const RE_FENCE = /^\s*(`{3,}|~{3,})\s*([\w+-]*)/;
const RE_HEADING = /^\s{0,3}(#{1,6})\s+(.*?)(?:\s+#+)?\s*$/;
const RE_HR = /^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/;
const RE_QUOTE = /^\s{0,3}>/;
const RE_ITEM = /^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/;
const RE_TABLE_SEP = /^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$/;

function splitRow(line) {
  let t = line.trim();
  if (t.startsWith('|')) t = t.slice(1);
  if (t.endsWith('|') && !t.endsWith('\\|')) t = t.slice(0, -1);
  return t.split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, '|'));
}

function isTableStart(lines, i) {
  return (
    i + 1 < lines.length &&
    lines[i].indexOf('|') !== -1 &&
    RE_TABLE_SEP.test(lines[i + 1]) &&
    lines[i + 1].indexOf('-') !== -1 &&
    splitRow(lines[i]).length >= 2
  );
}

function isBlockStart(lines, i) {
  const l = lines[i];
  return (
    RE_FENCE.test(l) ||
    RE_HEADING.test(l) ||
    RE_HR.test(l) ||
    RE_QUOTE.test(l) ||
    RE_ITEM.test(l) ||
    isTableStart(lines, i)
  );
}

function buildList(items) {
  let html = '';
  const stack = [];
  for (const it of items) {
    while (stack.length && it.indent < stack[stack.length - 1].indent) {
      html += '</li></' + stack.pop().tag + '>';
    }
    const top = stack[stack.length - 1];
    let text = it.text;
    let box = '';
    const task = text.match(/^\[( |x|X)\]\s+/);
    if (task) {
      box = '<input type="checkbox" disabled' + (task[1] === ' ' ? '' : ' checked') + '> ';
      text = text.slice(task[0].length);
    }
    const body = box + inline(text);
    if (!top || it.indent > top.indent) {
      const tag = it.ordered ? 'ol' : 'ul';
      stack.push({ indent: it.indent, tag });
      html += '<' + tag + (task ? ' class="task-list"' : '') + '><li>' + body;
    } else {
      html += '</li><li>' + body;
    }
  }
  while (stack.length) html += '</li></' + stack.pop().tag + '>';
  return html;
}

function renderBlocks(lines) {
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }

    // fenced code
    let m = line.match(RE_FENCE);
    if (m) {
      const ch = m[1][0];
      const closer = new RegExp('^\\s*' + ch + '{' + m[1].length + ',}\\s*$');
      const buf = [];
      i++;
      while (i < lines.length && !closer.test(lines[i])) buf.push(lines[i++]);
      i++; // closing fence (or EOF)
      out.push(
        '<pre><code' + (m[2] ? ' class="lang-' + escapeHtml(m[2]) + '"' : '') + '>' +
        escapeHtml(buf.join('\n')) + '</code></pre>'
      );
      continue;
    }

    // horizontal rule (before lists: "* * *" and "---")
    if (RE_HR.test(line)) {
      out.push('<hr>');
      i++;
      continue;
    }

    // heading
    m = line.match(RE_HEADING);
    if (m) {
      const level = Math.min(m[1].length + 2, 6);
      out.push('<h' + level + '>' + inline(m[2]) + '</h' + level + '>');
      i++;
      continue;
    }

    // blockquote
    if (RE_QUOTE.test(line)) {
      const buf = [];
      while (i < lines.length && RE_QUOTE.test(lines[i])) {
        buf.push(lines[i].replace(/^\s{0,3}>\s?/, ''));
        i++;
      }
      out.push('<blockquote>' + renderBlocks(buf) + '</blockquote>');
      continue;
    }

    // table
    if (isTableStart(lines, i)) {
      const head = splitRow(lines[i]);
      const aligns = splitRow(lines[i + 1]).map((c) => {
        const l = c.startsWith(':');
        const r = c.endsWith(':');
        return l && r ? 'center' : r ? 'right' : l ? 'left' : '';
      });
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].trim() && lines[i].indexOf('|') !== -1) {
        rows.push(splitRow(lines[i]));
        i++;
      }
      const cell = (tag, text, idx) =>
        '<' + tag + (aligns[idx] ? ' style="text-align:' + aligns[idx] + '"' : '') + '>' + inline(text) + '</' + tag + '>';
      let html = '<div class="table-wrap"><table><thead><tr>' + head.map((c, k) => cell('th', c, k)).join('') + '</tr></thead><tbody>';
      for (const r of rows) {
        html += '<tr>';
        for (let k = 0; k < head.length; k++) html += cell('td', r[k] == null ? '' : r[k], k);
        html += '</tr>';
      }
      out.push(html + '</tbody></table></div>');
      continue;
    }

    // list
    if (RE_ITEM.test(line)) {
      const items = [];
      while (i < lines.length) {
        const cur = lines[i];
        const im = cur.match(RE_ITEM);
        if (im && !RE_HR.test(cur)) {
          const ordered = /\d/.test(im[2][0]);
          // a different list type at the base indent starts a new list
          if (items.length && im[1].length <= items[0].indent && ordered !== items[0].ordered) break;
          items.push({ indent: im[1].length, ordered, text: im[3] });
          i++;
        } else if (!cur.trim()) {
          // a blank line only continues the list if another item follows
          let j = i + 1;
          while (j < lines.length && !lines[j].trim()) j++;
          if (j < lines.length && RE_ITEM.test(lines[j]) && !RE_HR.test(lines[j])) i = j;
          else break;
        } else if (/^\s/.test(cur) && items.length && !isBlockStart(lines, i)) {
          items[items.length - 1].text += ' ' + cur.trim(); // lazy continuation
          i++;
        } else {
          break;
        }
      }
      out.push(buildList(items));
      continue;
    }

    // paragraph
    const buf = [line];
    i++;
    while (i < lines.length && lines[i].trim() && !isBlockStart(lines, i)) buf.push(lines[i++]);
    out.push('<p>' + buf.map((l) => inline(l.trim())).join('\n') + '</p>');
  }
  return out.join('\n');
}

/** Render untrusted Markdown to a safe HTML string. */
export function renderMarkdown(src) {
  const text = String(src == null ? '' : src).replace(/\r\n?/g, '\n').replace(/\t/g, '    ');
  return renderBlocks(text.split('\n'));
}

export default renderMarkdown;
