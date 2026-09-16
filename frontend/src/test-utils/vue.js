import { readFileSync } from 'node:fs'
import { createRenderer, h } from 'vue'
import { compileScript, parse } from '@vue/compiler-sfc'

const modules = new Map()
export async function loadVue(url) {
  if (modules.has(url.href)) return modules.get(url.href)
  const { descriptor } = parse(readFileSync(url, 'utf8'), { filename: url.pathname })
  let code = compileScript(descriptor, { id: url.pathname, inlineTemplate: true, templateOptions: { compilerOptions: { hoistStatic: false } } }).content
  for (const [, name] of [...code.matchAll(/from ['"]([^'"]+)['"]/g)]) {
    let resolved
    if (name.endsWith('.vue')) {
      const child = new URL(name, url); await loadVue(child); resolved = modules.get(child.href + ':url')
    } else resolved = name.startsWith('.') ? new URL(name, url).href : import.meta.resolve(name)
    code = code.replaceAll(`'${name}'`, `'${resolved}'`).replaceAll(`"${name}"`, `"${resolved}"`)
  }
  const encoded = `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
  modules.set(url.href + ':url', encoded)
  const result = (await import(encoded)).default
  modules.set(url.href, result)
  return result
}
export function mount(t, component, props) {
  const node = (type, text = '') => ({ type, text, props: {}, children: [], parent: null,
    addEventListener() {}, get options() { return this.children.filter(child => child.type === 'option') },
    getRootNode() { return { activeElement: null } },
  })
  const renderer = createRenderer({
    createElement: type => node(type), createText: text => node('#text', text), createComment: () => node('#comment'),
    setText(n, text) { n.text = text }, setElementText(n, text) { n.text = text; n.children = [] },
    patchProp(n, key, _old, value) { n.props[key] = value },
    insert(n, parent, anchor) {
      if (n.parent) n.parent.children.splice(n.parent.children.indexOf(n), 1)
      const index = anchor ? parent.children.indexOf(anchor) : -1
      parent.children.splice(index < 0 ? parent.children.length : index, 0, n); n.parent = parent
    }, remove(n) { n.parent?.children.splice(n.parent.children.indexOf(n), 1) },
    parentNode: n => n.parent, nextSibling: n => n.parent?.children[n.parent.children.indexOf(n) + 1],
  })
  const root = node('root'), app = renderer.createApp({ render: () => h(component, props) })
  app.mount(root); t.after(() => app.unmount()); return root
}
export const content = n => [n.text, ...n.children.map(content)].filter(Boolean).join(' ').replace(/\s+/g, ' ')
export const nodes = (n, type) => [...(n.type === type ? [n] : []), ...n.children.flatMap(child => nodes(child, type))]
