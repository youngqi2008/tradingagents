/**
 * 轻量 Markdown → HTML，供小程序 rich-text 渲染。
 * 覆盖标题、加粗/斜体、代码、链接、图片、列表、引用、分隔线、表格。
 */

function escapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function inlineFormat(s) {
  s = escapeHtml(s)
  s = s.replace(/!\[([^\]]*)\]\((https?:\/\/[^)\s]+)\)/g, '<img src="$2" alt="$1" style="max-width:100%;display:block;margin:8px 0;"/>')
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" style="color:#d4202a;">$1</a>')
  s = s.replace(/`([^`]+)`/g, '<code style="background:#f3f5fa;padding:0 4px;border-radius:4px;font-size:13px;">$1</code>')
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  s = s.replace(/__([^_]+)__/g, '<strong>$1</strong>')
  s = s.replace(/(^|[^\*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>')
  s = s.replace(/(^|[^_])_([^_\n]+)_(?!_)/g, '$1<em>$2</em>')
  return s
}

function isTableSep(line) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line)
}

function renderTable(headerLine, rows) {
  function cells(line) {
    var t = line.trim()
    if (t.charAt(0) === '|') t = t.slice(1)
    if (t.charAt(t.length - 1) === '|') t = t.slice(0, -1)
    return t.split('|').map(function (c) { return c.trim() })
  }
  var heads = cells(headerLine)
  var html = '<table style="width:100%;border-collapse:collapse;margin:10px 0;font-size:13px;">'
  html += '<thead><tr>'
  for (var i = 0; i < heads.length; i++) {
    html += '<th style="border:1px solid #e5e7eb;padding:6px 8px;background:#f8f9fc;text-align:left;">' + inlineFormat(heads[i]) + '</th>'
  }
  html += '</tr></thead><tbody>'
  for (var r = 0; r < rows.length; r++) {
    var cols = cells(rows[r])
    html += '<tr>'
    for (var c = 0; c < heads.length; c++) {
      html += '<td style="border:1px solid #e5e7eb;padding:6px 8px;">' + inlineFormat(cols[c] || '') + '</td>'
    }
    html += '</tr>'
  }
  html += '</tbody></table>'
  return html
}

function mdToHtml(src) {
  var text = String(src == null ? '' : src).replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  if (!text.trim()) return '<p style="color:#9ca3af;">暂无正文</p>'

  var lines = text.split('\n')
  var html = []
  var i = 0
  var inCode = false
  var codeBuf = []
  var listType = ''
  var listBuf = []

  function flushList() {
    if (!listBuf.length) return
    var tag = listType === 'ol' ? 'ol' : 'ul'
    html.push('<' + tag + ' style="padding-left:22px;margin:8px 0 12px;">')
    for (var n = 0; n < listBuf.length; n++) {
      html.push('<li style="margin:4px 0;line-height:1.7;">' + inlineFormat(listBuf[n]) + '</li>')
    }
    html.push('</' + tag + '>')
    listBuf = []
    listType = ''
  }

  while (i < lines.length) {
    var line = lines[i]

    if (line.indexOf('```') === 0) {
      flushList()
      if (inCode) {
        html.push(
          '<pre style="background:#f3f5fa;padding:10px 12px;border-radius:8px;overflow:auto;font-size:12px;line-height:1.6;margin:8px 0 12px;"><code>' +
          escapeHtml(codeBuf.join('\n')) +
          '</code></pre>'
        )
        codeBuf = []
        inCode = false
      } else {
        inCode = true
      }
      i += 1
      continue
    }
    if (inCode) {
      codeBuf.push(line)
      i += 1
      continue
    }

    if (i + 1 < lines.length && /\|/.test(line) && isTableSep(lines[i + 1])) {
      flushList()
      var rows = []
      i += 2
      while (i < lines.length && /\|/.test(lines[i]) && lines[i].trim()) {
        rows.push(lines[i])
        i += 1
      }
      html.push(renderTable(line, rows))
      continue
    }

    var heading = line.match(/^(#{1,6})\s+(.+)$/)
    if (heading) {
      flushList()
      var level = heading[1].length
      var size = [28, 24, 20, 18, 16, 15][level - 1]
      html.push(
        '<div style="font-size:' + size + 'px;font-weight:700;color:#111111;margin:14px 0 8px;line-height:1.4;">' +
        inlineFormat(heading[2]) +
        '</div>'
      )
      i += 1
      continue
    }

    if (/^\s*([-*_])\s*\1\s*\1[\s\1-]*$/.test(line) && line.replace(/\s/g, '').length >= 3) {
      flushList()
      html.push('<hr style="border:none;border-top:1px solid #e5e7eb;margin:14px 0;"/>')
      i += 1
      continue
    }

    var bq = line.match(/^\s*>\s?(.*)$/)
    if (bq) {
      flushList()
      html.push(
        '<div style="border-left:3px solid #d4202a;padding:4px 0 4px 12px;margin:8px 0;color:#4b5563;line-height:1.7;">' +
        inlineFormat(bq[1]) +
        '</div>'
      )
      i += 1
      continue
    }

    var ul = line.match(/^\s*[-*+]\s+(.+)$/)
    if (ul) {
      if (listType && listType !== 'ul') flushList()
      listType = 'ul'
      listBuf.push(ul[1])
      i += 1
      continue
    }
    var ol = line.match(/^\s*\d+\.\s+(.+)$/)
    if (ol) {
      if (listType && listType !== 'ol') flushList()
      listType = 'ol'
      listBuf.push(ol[1])
      i += 1
      continue
    }

    if (!line.trim()) {
      flushList()
      i += 1
      continue
    }

    flushList()
    html.push('<p style="margin:0 0 12px;line-height:1.75;color:#374151;font-size:15px;">' + inlineFormat(line) + '</p>')
    i += 1
  }

  if (inCode) {
    html.push(
      '<pre style="background:#f3f5fa;padding:10px 12px;border-radius:8px;overflow:auto;font-size:12px;line-height:1.6;"><code>' +
      escapeHtml(codeBuf.join('\n')) +
      '</code></pre>'
    )
  }
  flushList()
  return html.join('') || '<p style="color:#9ca3af;">暂无正文</p>'
}

function stripToPlain(src) {
  var s = String(src == null ? '' : src)
  s = s.replace(/```[\s\S]*?```/g, ' ')
  s = s.replace(/`([^`]+)`/g, '$1')
  s = s.replace(/!\[[^\]]*\]\([^)]+\)/g, '')
  s = s.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
  s = s.replace(/^#{1,6}\s+/gm, '')
  s = s.replace(/^\s*[-*+]\s+/gm, '')
  s = s.replace(/^\s*\d+\.\s+/gm, '')
  s = s.replace(/^\s*>\s?/gm, '')
  s = s.replace(/\*\*([^*]+)\*\*/g, '$1')
  s = s.replace(/__([^_]+)__/g, '$1')
  s = s.replace(/\*([^*]+)\*/g, '$1')
  s = s.replace(/_([^_]+)_/g, '$1')
  s = s.replace(/\s+/g, ' ').trim()
  return s
}

module.exports = {
  mdToHtml: mdToHtml,
  stripToPlain: stripToPlain,
}
