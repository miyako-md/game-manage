// Drive shapes by the role API's piece ID (`cell<N>_style<M>_<level>_<colour>`). The game has twelve
// shapes; each style number names one of them (game facts, cross-checked against the official geometry
// table that NTE Drive Calc's release database carries). Rows read top to bottom, `#` is a filled cell.
const SHAPES = {
  cell2_style1: ['##'],
  cell2_style2: ['#', '#'],
  cell3_style1: ['###'],
  cell3_style2: ['#', '#', '#'],
  cell3_style3: ['#.', '##'],
  cell3_style4: ['##', '#.'],
  cell3_style5: ['##', '.#'],
  cell3_style6: ['.#', '##'],
  cell4_style1: ['####'],
  cell4_style2: ['#', '#', '#', '#'],
  cell4_style5: ['.##', '##.'],
  cell4_style6: ['.#', '##', '#.'],
}

/** The piece's shape as rows of filled/empty cells, or null for a core piece or an unknown style. */
export function driveShape(id) {
  const match = /^(cell[1-9]_style\d+)_/.exec(String(id ?? ''))
  const rows = match && SHAPES[match[1]]
  return rows ? rows.map(row => [...row].map(cell => cell === '#')) : null
}

/** The piece's cell count from its ID, for a style the table does not know. */
export function driveCells(id) {
  const match = /^cell([1-9])_/.exec(String(id ?? ''))
  return match ? Number(match[1]) : null
}

/** The piece's quality colour from its ID suffix, as the score adapter reads it. */
export function driveQuality(id) {
  const match = /_(orange|purple|blue)$/i.exec(String(id ?? ''))
  return match ? match[1].toLowerCase() : null
}
