import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick, reactive } from 'vue'
import { loadVue, mount, nodes, content } from '../test-utils/vue.js'
import { calendarRange, calendarDaysRange, collectVersionCalendars } from '../calendar.js'

const Page = await loadVue(new URL('./CalendarPage.vue', import.meta.url))
const Version = await loadVue(new URL('./VersionCalendarContent.vue', import.meta.url))
const Timeline = await loadVue(new URL('./CalendarTimelineContent.vue', import.meta.url))
const games = [{ game_id: 'nte', display_name: '异环' }]
const snapshots = { nte: { events: { version: '1.4', payload: [
  { name: '跨年活动', version: '1.4', start_at: '2026-12-20T10:00:00+08:00', end_at: '2027-02-05T10:00:00+08:00' },
  { name: '异常日期', version: '1.4', start_at: '2027-02-05T10:00:00+08:00', end_at: '2026-12-20T10:00:00+08:00' },
  { name: '未公布日期', version: '1.4' },
] } } }

test('dense screen headers separate months from numeric days while retaining true boundary dates and compact images', t => {
  const asOf=Date.parse('2026-10-01T12:00:00+08:00')
  const range=calendarDaysRange(Date.parse('2026-09-24T00:00:00+08:00'),Date.parse('2026-12-04T00:00:00+08:00'))
  const events=[{id:'cross-month',gameId:'nte',gameName:'异环',name:'跨月活动',
    start_at:'2026-09-30T12:00:00+08:00',end_at:'2026-10-01T12:00:00+08:00'}]
  const screen=mount(t,Timeline,{events,range,asOf,rangeMode:'version'})
  const cells=nodes(screen,'div').filter(n=>n.props.class?.split(' ').includes('date-cell'))
  assert.equal(cells.length,71)
  assert.deepEqual(nodes(screen,'span').filter(n=>n.props.class==='day-month').map(content),['9月','10月','11月','12月'])
  assert.deepEqual(cells.map(cell=>content(nodes(cell,'strong')[0])),range.days.map(day=>String(day.day)))
  const first=cells.find(cell=>cell.props.title==='10 月 1 日')
  assert.match(first.props.class,/is-month-start/)
  assert.match(first.props.class,/is-today/)
  assert.match(first.props.class,/is-boundary/)
  assert.equal(content(nodes(first,'small')[0]),'四')
  assert.equal(content(nodes(first,'span').find(n=>n.props.class==='day-today')),'今天')
  assert.deepEqual(cells.filter(cell=>cell.props.class?.split(' ').includes('is-boundary')).map(cell=>cell.props.title),['9 月 30 日','10 月 1 日'])
  const image=mount(t,Timeline,{events,range,asOf,rangeMode:'version',mode:'image'})
  assert.equal(nodes(image,'span').filter(n=>n.props.class==='day-month').length,0)
  const imageFirst=nodes(image,'div').find(n=>n.props.title==='10 月 1 日')
  assert.equal(content(nodes(imageFirst,'strong')[0]),'10/ 1')
  assert.equal(nodes(imageFirst,'br').length,1)
  assert.equal(nodes(image,'div').filter(n=>n.props.class?.split(' ').includes('date-cell')).length,71)
})

test('switching game or range resets timeline scrolling but refreshing the same window preserves it', async t => {
  const asOf=Date.parse('2026-10-17T12:00:00+08:00')
  const event={id:'event',gameId:'nte',gameName:'异环',name:'活动',start_at:'2026-10-01',end_at:'2026-11-01'}
  const props=reactive({events:[event],range:calendarRange(asOf,'month'),rangeMode:'month',asOf})
  const root=mount(t,Timeline,props)
  const viewport=nodes(root,'div').find(node=>node.props.class==='calendar-content')
  viewport.scrollLeft=450;viewport.scrollTop=180
  props.events=[{...event}];props.asOf+=60000;await nextTick()
  assert.deepEqual([viewport.scrollLeft,viewport.scrollTop],[450,180])
  props.events=[{...event,gameId:'wuthering_waves',gameName:'鸣潮'}];await nextTick()
  assert.deepEqual([viewport.scrollLeft,viewport.scrollTop],[0,0])
  viewport.scrollLeft=300;viewport.scrollTop=80
  props.range=calendarRange(asOf,'fortnight');props.rangeMode='fortnight';await nextTick()
  assert.deepEqual([viewport.scrollLeft,viewport.scrollTop],[0,0])
})

test('all three games illustrate undated activities without inventing a time bar or adding pictures to bot output', t => {
  const asOf=Date.parse('2026-10-17T12:00:00+08:00')
  for (const gameId of ['wuthering_waves','nte','endfield']) {
    const event={id:gameId,gameId,gameName:gameId,name:'日期待定的活动',category:'角色活动',source_post_id:'notice'}
    const snapshots={[gameId]:{news:{payload:[{id:'notice',images:[`https://example.com/${gameId}.jpg`]}]}}}
    const root=mount(t,Timeline,{events:[event],snapshots,range:calendarRange(asOf,'month'),asOf})
    const unplaced=nodes(root,'button').find(node=>node.props.class==='unplaced-event')
    assert.equal(nodes(unplaced,'img')[0].props.src,`https://example.com/${gameId}.jpg`)
    assert.match(content(unplaced),/日期待定的活动.*时间待定/)
    assert.equal(nodes(root,'button').filter(node=>node.props.class?.includes('timeline-event')).length,0)
    const image=mount(t,Timeline,{events:[event],snapshots,range:calendarRange(asOf,'month'),asOf,mode:'image'})
    assert.equal(nodes(image,'img').length,0)
  }
})

test('screen and image compact bars retain category, uncertain states and confirmed remaining days without detailed dates', t => {
  const asOf=Date.parse('2026-10-15T12:00:00+08:00')
  const rows=[
    {name:'完整活动',start_at:'2026-10-01T10:00:00+08:00',end_at:'2026-11-01T12:00:00+08:00'},
    {name:'短时间活动',start_at:'2026-10-29T10:00:00+08:00',end_at:'2026-10-30T12:00:00+08:00'},
    {name:'仅知日期',start_date:'2026-10-03',start_precision:'day',end_date:'2026-10-04',end_precision:'day'},
    {name:'预计更新活动',start_date:'2026-10-12',start_precision:'relative',start_estimated:true,end_at:'2026-11-01T12:00:00+08:00'},
    {name:'永久活动',start_date:'2026-10-05',start_precision:'day',permanent:true,end_precision:'permanent'},
    {name:'开始未知',end_at:'2026-10-16T12:00:00+08:00'},
  ]
  const calendars=collectVersionCalendars(games,{nte:{events:{payload:rows}}},'',asOf)
  for(const mode of ['screen','image']) {
    const root=mount(t,Version,{calendars,asOf,mode})
    const bars=nodes(root,mode==='screen'?'button':'article').filter(node=>node.props.class?.includes('timeline-event'))
    assert.equal(bars.length,rows.length)
    assert.ok(bars.every(bar=>!nodes(bar,'small').some(node=>node.props.class==='event-boundaries')))
    const byName=name=>bars.find(bar=>bar.props['aria-label']===`查看活动详情：${name}`)
    assert.doesNotMatch(content(root),/2026-10-03|2026-10-04|10:00 —|12:00/)
    assert.match(content(byName('完整活动')),/剩 17 天/)
    assert.match(content(byName('预计更新活动')),/预计/)
    assert.match(content(byName('永久活动')),/常驻开放/)
    assert.equal(nodes(byName('永久活动'),'small').filter(n=>n.props.class?.includes('event-remaining')).length,0)
    assert.match(content(byName('开始未知')),/开始未知/)
    assert.ok(byName('短时间活动').props.class.includes('is-short'))
  }
})

test('version uses daily grid across the full cross-year source range and retains unplaced dates', async t => {
  const root = mount(t, Page, { games, snapshots })
  const days = nodes(root, 'div').filter(n => n.props.class?.includes('date-cell'))
  assert.equal(days.length, 48, 'Dec 20 through Feb 5 inclusive, without a 30-day cutoff')
  assert.equal(nodes(root, 'div').filter(n => n.props.class === 'timeline-group').length, 1)
  const bar = nodes(root, 'button').find(n => n.props['aria-label'] === '查看活动详情：跨年活动')
  assert.ok(bar.props.class.includes('timeline-event'))
  assert.ok(nodes(root, 'button').find(n => n.props['aria-label'] === '查看活动详情：异常日期'))
  assert.match(content(root), /日期异常/)
  assert.match(content(root), /未公布日期/)
  assert.doesNotMatch(content(root), /覆盖待核验|当前性待核验|不代表版本边界/)
  for (const label of ['近 30 天', '整月', '14 天']) {
    nodes(root, 'button').find(n => n.text === label).props.onClick()
    await nextTick()
    assert.equal(nodes(root, 'div').filter(n => n.props.class === 'timeline-header').length, 1)
    assert.ok(nodes(root, 'div').some(n => n.props.class?.includes('date-cell')))
  }
})

test('image calendar uses the full website date axis once and preserves unknown dates', t => {
  const asOf = Date.parse('2027-01-01T12:00:00+08:00')
  const calendars = collectVersionCalendars(games, snapshots, '', asOf)
  const root = mount(t, Version, { calendars, asOf, mode: 'image' })
  const headers = nodes(root, 'div').filter(n => n.props.class === 'timeline-header')
  assert.equal(headers.length, 1)
  assert.equal(nodes(headers[0], 'div').filter(d => d.props.class?.includes('date-cell')).length, 48)
  assert.equal(nodes(root, 'button').length, 0)
  const blocks = nodes(root, 'div').filter(n => n.props.class === 'event-lane')
  assert.equal(blocks.length, 1, 'the activity appears once on the full source date axis')
  assert.ok(blocks.every(n => Object.hasOwn(n.props, 'data-render-block')))
  assert.match(content(root), /异常日期.*日期异常/)
  assert.match(content(root), /未公布日期/)
  assert.doesNotMatch(content(root), /覆盖待核验|时间窗口|当前性待核验|不代表版本边界/)
})

test('image presents its date axis and activities without technical source disclosures', t => {
  const calendars = collectVersionCalendars(games, snapshots, '', Date.parse('2027-01-01T12:00:00+08:00'))
  const root = mount(t, Version, { calendars, asOf:Date.parse('2027-01-01T12:00:00+08:00'), mode:'image' })
  const text = content(root)
  assert.match(text,/跨年活动/)
  assert.match(text,/版本活动时间轴/)
  assert.doesNotMatch(text,/数据来源详情|来源与读取状态|来源未提供/)
  assert.equal(nodes(root,'details').length,0)
})

test('calendar artwork follows event sources on screen and never adds external images to bot rendering', async t => {
  const asOf=Date.parse('2026-10-17T12:00:00+08:00')
  const rows={nte:{events:{payload:[{name:'带配图活动',version:'1.4',source_post_id:'p1',start_at:'2026-10-01T12:00:00+08:00',end_at:'2026-11-01T12:00:00+08:00'}]},news:{payload:[{id:'p1',images:['https://example.com/event.jpg']}]}}}
  const calendars=collectVersionCalendars(games,rows,'',asOf)
  const screen=mount(t,Version,{calendars,snapshots:rows,asOf})
  assert.ok(nodes(screen,'img').some(img=>img.props.src==='https://example.com/event.jpg'))
  const image=mount(t,Version,{calendars,snapshots:rows,asOf,mode:'image'})
  assert.ok(!nodes(image,'img').some(img=>img.props.src==='https://example.com/event.jpg'))
  const root=mount(t,Page,{games,snapshots:rows})
  const agenda=nodes(root,'button').find(n=>n.props.class==='agenda-item')
  assert.equal(nodes(agenda,'img')[0].props.src,'https://example.com/event.jpg')
  agenda.props.onClick({currentTarget:{isConnected:true,focus(){}}});await nextTick()
  const detail=nodes(root,'section').find(n=>n.props['aria-labelledby']==='calendar-detail-title')
  assert.equal(nodes(detail,'img')[0].props.src,'https://example.com/event.jpg')
  assert.match(content(detail),/带配图活动/)
})

test('screen presents category sections and recorded boundary accents while bot calendar retains compact original sections', t => {
  const asOf=Date.parse('2026-10-17T12:00:00+08:00')
  const snapshots={nte:{events:{payload:[
    {name:'寻访横幅',category:'特许寻访',banner:'https://example.com/character.jpg',start_at:'2026-10-15T12:00:00+08:00',end_at:'2026-11-01T12:00:00+08:00'},
    {name:'武器横幅',category:'武库申领',banner:'https://example.com/weapon.jpg',start_at:'2026-10-29T12:00:00+08:00',end_at:'2026-11-01T12:00:00+08:00'},
    {name:'单点日期',category:'限时活动',banner:'https://example.com/event.jpg',end_date:'2026-10-22'},
  ]}}}
  const calendars=collectVersionCalendars(games,snapshots,'',asOf)
  const screen=mount(t,Version,{calendars,snapshots,asOf})
  assert.equal(nodes(screen,'div').filter(node=>node.props.class==='timeline-group').length,3)
  assert.match(content(screen),/寻访与角色.*武器与装备.*活动与玩法/)
  const boundaries=nodes(screen,'div').filter(node=>node.props.class?.split(' ').includes('is-boundary'))
  assert.ok(boundaries.some(node=>node.props.title==='10 月 15 日'))
  assert.ok(boundaries.some(node=>node.props.title==='10 月 22 日'))
  const short=nodes(screen,'button').find(node=>node.props['aria-label']==='查看活动详情：武器横幅')
  assert.ok(short.props.class.includes('is-short'))
  assert.match(content(short),/武器横幅.*武库申领/)
  const point=nodes(screen,'button').find(node=>node.props['aria-label']==='查看活动详情：单点日期')
  assert.ok(point.props.class.includes('is-point'))
  assert.match(content(point),/单点日期/)
  const image=mount(t,Version,{calendars,snapshots,asOf,mode:'image'})
  assert.equal(nodes(image,'div').filter(node=>node.props.class==='timeline-group').length,1)
  assert.ok(!nodes(image,'img').some(img=>img.props.src?.startsWith('https://example.com/')))
  assert.ok(!nodes(image,'div').some(node=>node.props.class?.split(' ').includes('is-boundary')))
})
