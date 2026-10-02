// Client-side folder-tree/label-facet/find filter logic (quad-layout Part 6, Task 22) -- mirrors
// `actor find`'s matching rules so the org panel's tree/facets/find box behave exactly like the CLI
// verb they front. Pure, framework-free (no DOM), so it's testable without a browser.
//
// Folder matching is a faithful port of `uedcli/folderlib.py`'s NORMATIVE algorithm (read directly,
// not re-derived): case-insensitive, `.`-segmented, a wildcard-free pattern matches its whole
// subtree, a wildcarded pattern (`*` = one segment, `**` = any depth) has NO subtree extension.
// Name/class glob matching mirrors `uedcli/query.py`'s use of Python's `fnmatch.fnmatch` (lower-
// cased both sides) -- ported to TypeScript since the client has no Python runtime.
import type { SceneActor } from '../api'

export interface FolderNode {
  path: string | null // null = the root; also the "(no folder)" bucket's own literal value is null
  children: FolderNode[]
  actors: SceneActor[]
}

/** Builds the folder tree: one node per distinct folder path (plus intermediate ancestors implied
 * by a dotted path, even if no actor sits directly on them) and a root-level `(no folder)` bucket
 * for `folder === null` actors -- `actor find --no-folder`'s "only way to query them" story,
 * translated to a UI bucket rather than a glob (folderlib.py's `matches` never matches `null`). */
export function buildFolderTree(actors: SceneActor[]): FolderNode {
  const root: FolderNode = { path: null, children: [], actors: [] }
  const byPath = new Map<string, FolderNode>()

  const nodeFor = (path: string): FolderNode => {
    const existing = byPath.get(path)
    if (existing) return existing
    const segments = path.split('.')
    const parentPath = segments.slice(0, -1).join('.')
    const parent = segments.length > 1 ? nodeFor(parentPath) : root
    const node: FolderNode = { path, children: [], actors: [] }
    parent.children.push(node)
    byPath.set(path, node)
    return node
  }

  for (const actor of actors) {
    if (actor.folder === null) {
      root.actors.push(actor)
      continue
    }
    nodeFor(actor.folder).actors.push(actor)
  }

  return root
}

/** OR-combined label match: empty `activeLabels` matches everything (no facet active). */
export function matchesLabelFacets(actor: SceneActor, activeLabels: ReadonlySet<string>): boolean {
  if (activeLabels.size === 0) return true
  return actor.labels.some((l) => activeLabels.has(l))
}

/** The "(no label)" bucket's own predicate -- mirrors the folder tree's "(no folder)" bucket: reached
 * only this way, never via a label glob (an actor with zero labels can never satisfy `some()` above). */
export function hasNoLabel(actor: SceneActor): boolean {
  return actor.labels.length === 0
}

// ----- folder pattern matching (folderlib.py port) -------------------------------------------

function isWildcardFree(pattern: string): boolean {
  return !pattern.includes('*')
}

function segMatch(pat: string[], path: string[]): boolean {
  if (pat.length === 0) return path.length === 0
  const [head, ...patRest] = pat
  if (head === '**') {
    for (let k = 0; k <= path.length; k++) {
      if (segMatch(patRest, path.slice(k))) return true
    }
    return false
  }
  if (path.length === 0) return false
  if (head === '*') return segMatch(patRest, path.slice(1))
  return head === path[0] && segMatch(patRest, path.slice(1))
}

/** Does `folder` match the query `pattern`? `folder === null` matches no pattern. */
export function matchesFolderPattern(pattern: string, folder: string | null): boolean {
  if (folder === null) return false
  const p = pattern.toLowerCase()
  const f = folder.toLowerCase()
  if (isWildcardFree(pattern)) {
    return f === p || f.startsWith(p + '.')
  }
  return segMatch(p.split('.'), f.split('.'))
}

// ----- name/class glob matching (fnmatch.fnmatch port) ----------------------------------------

/** Translates an `fnmatch`-style glob (`*`, `?`, `[seq]`/`[!seq]`) into an anchored, case-
 * insensitive `RegExp` -- the same three wildcard forms Python's `fnmatch.translate` supports.
 * Every other character is matched literally (regex-escaped). */
function globToRegExp(glob: string): RegExp {
  let out = ''
  let i = 0
  while (i < glob.length) {
    const c = glob[i]
    if (c === '*') {
      out += '.*'
      i += 1
    } else if (c === '?') {
      out += '.'
      i += 1
    } else if (c === '[') {
      let j = i + 1
      let negate = false
      if (glob[j] === '!') {
        negate = true
        j += 1
      }
      const start = j
      while (j < glob.length && glob[j] !== ']') j += 1
      if (j >= glob.length) {
        // No closing ']' -- fnmatch treats a stray '[' as a literal.
        out += '\\['
        i += 1
      } else {
        const body = glob.slice(start, j).replace(/\\/g, '\\\\')
        out += `[${negate ? '^' : ''}${body}]`
        i = j + 1
      }
    } else {
      out += c.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      i += 1
    }
  }
  return new RegExp(`^${out}$`, 'is')
}

export interface FindQuery {
  name?: string
  cls?: string
  folder?: string
  label?: string
}

/** Mirrors `actor find`'s combined predicate (`--name`-equivalent glob, `--exact-class`-equivalent
 * glob, `--folder`, `--label`): every stated field must match; an absent field imposes no
 * constraint. */
export function matchesFind(actor: SceneActor, query: FindQuery): boolean {
  if (query.name !== undefined && !globToRegExp(query.name).test(actor.name)) return false
  if (query.cls !== undefined && !globToRegExp(query.cls).test(actor.cls)) return false
  if (query.folder !== undefined && !matchesFolderPattern(query.folder, actor.folder)) return false
  if (query.label !== undefined) {
    const re = globToRegExp(query.label)
    if (!actor.labels.some((l) => re.test(l))) return false
  }
  return true
}
