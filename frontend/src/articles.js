import { safeUrl } from './calendar.js'

// Extend subjects here without changing sources, calendar acceptance or storage.
export const ARTICLE_CATEGORIES = [
  { id: 'version', label: '版本更新说明', pattern: /版本.{0,16}(?:内容说明|更新说明|更新公告|更新内容)|版本更新一览/ },
  { id: 'maintenance', label: '维护通知', pattern: /维护|停服|预下载|更新预告/ },
  { id: 'community', label: '社区活动', pattern: /网页活动|创作(?:征集|激励)|同人|线下活动|漫展|参展|ChinaJoy|社区活动|转发抽奖|互动抽奖/i },
  { id: 'weapon-pool', label: '武器与装备卡池', pattern: /武器(?:活动)?唤取|武器卡池|弧盘研募|武库申领|装备卡池/ },
  { id: 'character-pool', label: '角色卡池', pattern: /角色(?:活动)?唤取|角色卡池|限定棋盘|特许寻访|特殊寻访|重构寻访|限定.{0,12}返场/ },
  { id: 'fix', label: '修复与补偿', pattern: /修复|补偿|异常说明|问题说明|问题处理/ },
  { id: 'check-in', label: '签到福利', pattern: /签到|七日.{0,8}奖励|登录.{0,8}(?:福利|奖励)/ },
  { id: 'event', label: '游戏内活动', pattern: /限时活动|游戏内活动|活动(?:开启|开放|时间|预告)|盲盒|调频|限时.{0,8}(?:挑战|玩法)/ },
  { id: 'esports', label: '赛事资讯', pattern: /赛事|世界赛|全球总决赛|职业联赛|赛程|LPL|LCK|MSI|S\d+.{0,8}(?:赛|对决)/i },
  { id: 'guide', label: '攻略与玩法', pattern: /攻略|玩法解析|技巧|配队|培养指南|玩法介绍/ },
  { id: 'character', label: '角色介绍', pattern: /角色(?:介绍|档案|演示)|干员(?:介绍|档案)|英雄(?:介绍|揭秘)|人物介绍/ },
  { id: 'preview', label: '前瞻与宣传', pattern: /前瞻|直播预告|宣传|PV|主题曲|预告片/i },
  { id: 'notice', label: '官方公告', pattern: /公告|通知/ },
  { id: 'other', label: '其他', pattern: null },
]
const SOURCE_CATEGORIES = { events: 'event', notices: 'notice', 公告: 'notice', news: 'other', 赛事: 'esports', 攻略: 'guide', 社区: 'community' }
const text = value => typeof value === 'string' ? value : ''
const normalizedTitle = value => text(value).normalize('NFKC').replace(/#[^#]*#/g, '').replace(/[\s\p{P}\p{S}]/gu, '').toLowerCase()
const contentRank = row => row.body || row.images.length ? row.content_status === 'full' && !row.source_stale ? 3 : row.content_status === 'stale' || row.content_status === 'full' ? 2 : 1 : 0

export function classifyArticle(item) {
  const title = text(item.title).replace(/#[^#]*#/g, '').trim(), body = text(item.body || item.summary)
  const explicit = ARTICLE_CATEGORIES.find(rule => rule.id === item.content_category || rule.label === item.category)
  const matchingTitle = ARTICLE_CATEGORIES.find(rule => rule.pattern?.test(title))
  const source = ARTICLE_CATEGORIES.find(rule => rule.id === SOURCE_CATEGORIES[item.category])
  const fallbackBody = ARTICLE_CATEGORIES.find(rule => rule.pattern?.test(body.split('\n').slice(0, 3).join('\n')))
  const main = explicit || matchingTitle || (source?.id !== 'other' ? source : null) || fallbackBody || ARTICLE_CATEGORIES.at(-1)
  const tags = ARTICLE_CATEGORIES.filter(rule => rule.id !== main.id && !['notice', 'other', 'maintenance'].includes(rule.id) && rule.pattern?.test(body)).map(rule => rule.label)
  if (/限时/.test(title + body)) tags.push('限时')
  if (/奖励|福利/.test(title + body)) tags.push('奖励')
  return { categoryId: main.id, categoryLabel: main.label, tags: [...new Set(tags)] }
}

function readable(value) {
  return text(value).replace(/<(script|style|iframe)\b[^>]*>[\s\S]*?<\/\1>/gi, '').replace(/<[^>]*>/g, '').trim()
}

export function prepareArticles(snapshots) {
  const rows = [], urls = new Map(), subjects = new Map()
  for (const snap of snapshots.filter(Boolean)) {
    for (const raw of Array.isArray(snap.payload) ? snap.payload : []) {
      if (!raw || typeof raw !== 'object') continue
      const url = safeUrl(raw.url), body = text(raw.body), published = text(raw.published_at)
      const title = text(raw.title).trim() || '未命名文章'
      const subject = normalizedTitle(title) + ':' + published.slice(0, 10)
      const key = url || `${raw.source || ''}:${raw.id || subject}`
      const row = { ...raw, title, url, body, key, fetched_at: raw.fetched_at || snap.fetched_at, category: raw.category || (snap.capability === 'announcement' ? '公告' : ''), source_stale: !!(raw.source_stale || snap.stale), links: url ? [{ url, name: raw.source_name || '原文' }] : [] }
      for (const link of Array.isArray(raw.original_links) ? raw.original_links : []) {
        const href = safeUrl(link.url)
        if (href && !row.links.some(l => l.url === href)) row.links.push({ url: href, name: link.name || '原文' })
      }
      row.content_status ||= body || (Array.isArray(raw.images) && raw.images.length) ? 'full' : 'unavailable'
      const excerpt = readable(raw.summary) || body
      row.excerpt = excerpt.replace(/\s+/g, ' ').slice(0, 180) + (excerpt.length > 180 ? '…' : '')
      row.images = [...new Set((Array.isArray(raw.images) ? raw.images : []).map(safeUrl).filter(Boolean))]
      const candidate = normalizedTitle(title) ? subjects.get(subject) : null
      const existing = urls.get(key) || (candidate && (candidate.source !== row.source || (!candidate.source && !row.source)) ? candidate : null)
      if (existing) {
        const rank = contentRank(row), oldRank = contentRank(existing)
        const newer = (Date.parse(row.fetched_at) || 0) > (Date.parse(existing.fetched_at) || 0)
        if (rank > oldRank || (rank === oldRank && newer)) {
          for (const field of ['body', 'images', 'excerpt', 'content_status', 'content_error', 'source_stale', 'fetched_at']) existing[field] = row[field]
        }
        if (row.category === '公告' && !existing.category) existing.category = '公告'
        for (const link of row.links) if (!existing.links.some(l => l.url === link.url)) existing.links.push(link)
        urls.set(key, existing)
      } else {
        rows.push(row); urls.set(key, row); subjects.set(subject, row)
      }
    }
  }
  return rows.map(row => ({ ...row, ...classifyArticle(row) })).sort((a, b) => {
    const at = Date.parse(a.published_at), bt = Date.parse(b.published_at)
    return (Number.isFinite(bt) ? bt : 0) - (Number.isFinite(at) ? at : 0)
  })
}

export function contentNote(item) {
  if (item.content_status === 'video') return '这是视频内容，请前往原文观看。'
  if (item.content_status === 'external') return '这是外部专题或活动页面，请前往原文查看完整内容。'
  if (item.content_status === 'stale') return `${item.content_error || '正文更新失败'}，以下保留上次成功正文。`
  if (item.content_status === 'error') return item.content_error || '正文暂时无法读取，请稍后刷新或查看原文。'
  if (item.content_status !== 'full') return item.content_error || '来源暂未提供可读取的正文，请查看原文。'
  return ''
}
