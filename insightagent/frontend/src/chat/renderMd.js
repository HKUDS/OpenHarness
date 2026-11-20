// 轻量 Markdown 渲染（移植自桌面设计稿），用于助手回答的富文本展示
function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function inlineMd(s) {
  s = esc(s)
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>')
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
  return s
}

export function renderMd(src) {
  const lines = String(src || '').split('\n')
  const out = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    const fence = line.match(/^\s*(`{3,}|~{3,})/)
    if (fence) {
      const marker = fence[1][0]
      const len = fence[1].length
      const buf = []
      i++
      while (i < lines.length && !new RegExp('^\\s*' + marker + '{' + len + ',}').test(lines[i])) {
        buf.push(lines[i])
        i++
      }
      i++
      const lang = fence[1].length === 3 && line.trim().length > 3 ? line.trim().slice(3).trim() : ''
      out.push('<pre><code' + (lang ? ' data-lang="' + esc(lang) + '"' : '') + '>' + esc(buf.join('\n')) + '</code></pre>')
      continue
    }
    if (/^\s*\|/.test(line) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|?\s*$/.test(lines[i + 1])) {
      const head = line.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim())
      i += 2
      const rows = []
      while (i < lines.length && /^\s*\|/.test(lines[i])) {
        rows.push(lines[i].trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim()))
        i++
      }
      let t = '<table><thead><tr>' + head.map((h) => '<th>' + inlineMd(h) + '</th>').join('') + '</tr></thead><tbody>'
      for (const r of rows) t += '<tr>' + r.map((c) => '<td>' + inlineMd(c) + '</td>').join('') + '</tr>'
      out.push(t + '</tbody></table>')
      continue
    }
    const h = line.match(/^(#{1,6})\s+(.*)/)
    if (h) {
      const lv = Math.min(h[1].length, 3)
      out.push(`<h${lv}>${inlineMd(h[2])}</h${lv}>`)
      i++
      continue
    }
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) {
      out.push('<hr>')
      i++
      continue
    }
    if (/^\s*>\s?/.test(line)) {
      const buf = []
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        buf.push(lines[i].replace(/^\s*>\s?/, ''))
        i++
      }
      out.push('<blockquote>' + inlineMd(buf.join('\n')).replace(/\n/g, '<br>') + '</blockquote>')
      continue
    }
    if (/^\s*([-*+]|\d+\.)\s+/.test(line)) {
      const ordered = /^\s*\d+\./.test(line)
      const items = []
      let j = i
      while (j < lines.length && /^\s*([-*+]|\d+\.)\s+/.test(lines[j])) {
        items.push(lines[j].replace(/^\s*([-*+]|\d+\.)\s+/, ''))
        j++
      }
      i = j
      out.push(
        '<' + (ordered ? 'ol' : 'ul') + '>' + items.map((x) => '<li>' + inlineMd(x) + '</li>').join('') + '</' + (ordered ? 'ol' : 'ul') + '>'
      )
      continue
    }
    if (!line.trim()) {
      i++
      continue
    }
    const buf = [line]
    i++
    while (i < lines.length && lines[i].trim() && !/^\s*(#{1,6}\s|>|\||-{3,}|`{3,}|~{3,}|[-*+]\s|\d+\.\s)/.test(lines[i])) {
      buf.push(lines[i])
      i++
    }
    out.push('<p>' + inlineMd(buf.join('\n')).replace(/\n/g, '<br>') + '</p>')
  }
  return out.join('\n')
}
