import test from 'node:test'
import assert from 'node:assert/strict'
import { driveCells, driveQuality, driveShape } from './nte-drive-shapes.js'

const draw = id => driveShape(id)?.map(row => row.map(cell => cell ? '#' : '.').join(''))

test('each of the twelve drive styles draws its own shape with its cell count', () => {
  const styles = { 2: [1, 2], 3: [1, 2, 3, 4, 5, 6], 4: [1, 2, 5, 6] }
  const seen = new Set()
  for (const [cells, list] of Object.entries(styles)) for (const style of list) {
    const shape = draw(`cell${cells}_style${style}_1_orange`)
    assert.ok(shape, `cell${cells}_style${style}`)
    assert.equal(shape.join('').replace(/\./g, '').length, Number(cells))
    seen.add(shape.join('/'))
  }
  assert.equal(seen.size, 12)
  assert.deepEqual(draw('cell3_style1_9_blue'), ['###'])
  assert.deepEqual(draw('cell2_style2_1_purple'), ['#', '#'])
})

test('a core piece or an unknown style has no shape; the cell count and colour still read from the ID', () => {
  assert.equal(driveShape('Street_orange'), null)
  assert.equal(driveShape('cell4_style3_1_orange'), null)
  assert.equal(driveCells('cell4_style3_1_orange'), 4)
  assert.equal(driveCells('Street_orange'), null)
  assert.deepEqual(['cell2_style1_1_Orange', 'x_purple', 'cell3_style1_1_gold', null].map(driveQuality), ['orange', 'purple', null, null])
})
