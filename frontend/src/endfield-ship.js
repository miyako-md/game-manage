export const SHIP_CONVERSION_MODEL = Object.freeze({
  id: 'endfield-plugin-spaceship-v3.5.0', kind: 'static_observation',
  source_url: 'https://github.com/Entropy-Increase-Team/endfield-plugin/blob/main/API.md#L6089-L6123',
})
const owns = (value, key) => Object.prototype.hasOwnProperty.call(value, key)
const decimal = /^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$/
const number = value => (typeof value === 'number' || typeof value === 'string' && decimal.test(value.trim())) && Number.isFinite(Number(value)) && Number(value) >= 0 ? Number(value) : null
const bounded = (value, maximum) => { const result = number(value); return result != null && result <= maximum ? result : null }
const rows = value => Array.isArray(value) ? value.filter(item => item && typeof item === 'object' && !Array.isArray(item)) : []

const md5Shifts = [7,12,17,22,5,9,14,20,4,11,16,23,6,10,15,21]
const md5Constants = Array.from({length:64}, (_, index) => Math.floor(Math.abs(Math.sin(index + 1)) * 0x100000000))

// Live ship charId values use this ASCII template form; the same roster stores
// their lowercase MD5 digest. Keep this exact relation for saved observations.
function residentRosterId(id) {
  if (typeof id !== 'string' || /^chr_[0-9]{4}_[a-z0-9_]+$/.exec(id)?.[0] !== id) return null
  const words = new Int32Array((((id.length + 8) >>> 6) + 1) * 16)
  for (let index = 0; index < id.length; index++) words[index >>> 2] |= id.charCodeAt(index) << ((index % 4) * 8)
  words[id.length >>> 2] |= 0x80 << ((id.length % 4) * 8)
  words[words.length - 2] = id.length * 8
  words[words.length - 1] = Math.floor(id.length / 0x20000000)
  const state = [0x67452301,0xefcdab89,0x98badcfe,0x10325476]
  for (let offset = 0; offset < words.length; offset += 16) {
    let [a,b,c,d] = state
    for (let index = 0; index < 64; index++) {
      let mix, word
      if (index < 16) { mix = (b & c) | (~b & d); word = index }
      else if (index < 32) { mix = (d & b) | (~d & c); word = (5 * index + 1) % 16 }
      else if (index < 48) { mix = b ^ c ^ d; word = (3 * index + 5) % 16 }
      else { mix = c ^ (b | ~d); word = (7 * index) % 16 }
      const shift = md5Shifts[(index >>> 4) * 4 + index % 4]
      const sum = (a + mix + md5Constants[index] + words[offset + word]) | 0
      const previousD = d
      d = c; c = b; b = (b + ((sum << shift) | (sum >>> (32 - shift)))) | 0; a = previousD
    }
    for (const [index, value] of [a,b,c,d].entries()) state[index] = (state[index] + value) | 0
  }
  return state.flatMap(word => [0,8,16,24].map(shift => ((word >>> shift) & 0xff).toString(16).padStart(2,'0'))).join('')
}

// Compatibility for saved observations predating the shared backend fields.
// Explicit values (including null) from the new report remain authoritative.
export function shipResident(operator) {
  const mood = number(owns(operator, 'mood_raw') ? operator.mood_raw : operator.physicalStrength)
  const trust = number(owns(operator, 'trust_raw') ? operator.trust_raw : operator.favorability)
  const trustPercent = trust == null ? null : trust < 300 ? Math.floor(trust / 3) : trust < 1500 ? 100 + Math.floor((trust - 300) / 12) : 200
  const trustLevel = trust == null ? null : trust < 300 ? '友好' : trust < 1500 ? '亲近' : '信任'
  return { ...operator, mood_raw: mood, trust_raw: trust,
    mood_percent: owns(operator, 'mood_percent') ? bounded(operator.mood_percent, 100) : mood != null && mood <= 10000 ? mood / 100 : null,
    trust_percent: owns(operator, 'trust_percent') ? bounded(operator.trust_percent, 200) : trustPercent,
    trust_level_name: owns(operator, 'trust_level_name') ? ['友好', '亲近', '信任'].includes(operator.trust_level_name) ? operator.trust_level_name : null : trustLevel,
  }
}

export function shipReport(value, operators = []) {
  if (!value) return value
  const index = new Map()
  for (const operator of rows(operators)) for (const key of ['id', 'char_id']) if (operator[key] != null) index.set(String(operator[key]), operator)
  const rooms = rows(value.rooms).map(room => ({ ...room,
    operators_available: typeof room.operators_available === 'boolean' ? room.operators_available : rows(room.operators).length ? true : null,
    operators: rows(room.operators).map(operator => {
      const id = operator.id ?? operator.charId ?? operator.char_id
      const record = index.get(String(id)) || index.get(residentRosterId(id))
      return shipResident({ ...operator, id, name: operator.name || operator.charData?.name || record?.name,
        avatar_url: operator.avatar_url || record?.avatar_url || operator.charData?.avatarSqUrl })
    }) }))
  const available = typeof value.available === 'boolean' ? value.available : rooms.length ? true : null
  const staffAvailable = available === true && rooms.every(room => room.operators_available === true)
  return { ...value, available, conversion_model: value.conversion_model ?? SHIP_CONVERSION_MODEL, rooms,
    summary: { room_count: available === true ? rooms.length : null,
      staffed_rooms: staffAvailable ? rooms.filter(room => room.operators.length).length : null,
      operator_slots: staffAvailable ? rooms.reduce((total, room) => total + room.operators.length, 0) : null,
      ...value.summary } }
}

// The trust ring fills within the current stage: 友好 0–100%, 亲近 100–200%; 信任 is full.
// The text keeps the overall percentage; only the ring and its accessible value use the stage.
export function trustStage(percent, level) {
  const value = bounded(percent, 200)
  if (value == null) return null
  const stage = ['友好', '亲近', '信任'].includes(level) ? level : value < 100 ? '友好' : value < 200 ? '亲近' : '信任'
  return { level: stage, value: stage === '信任' ? 100 : Math.min(100, Math.max(0, stage === '亲近' ? value - 100 : value)), max: 100 }
}

// Match the report/QQ display rule, including half-up decimal boundaries.
export function shipPercent(value) {
  const percent = number(value)
  return percent == null ? '未知' : `${Math.floor(percent * 10 + 0.5) / 10}%`
}
