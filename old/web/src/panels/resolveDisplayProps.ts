// gui-inspector-props-payload-redesign spec §4's own render walk: reconstructs the SAME
// EffectiveProp[] tree effectiveProps.ts/groupByCategory.ts/Inspector.tsx's PropRow already know how
// to render, from a resolved ClassResolution (class shape + per-class defaults, classResolver.ts)
// and one actor's flat sparse props map (SceneActor.props). Neither effectiveProps.ts nor
// groupByCategory.ts nor PropRow change at all -- only WHERE the EffectiveProp[] they consume comes
// from changes (this function, instead of the server).
import type { ClassResolution, DefaultValue, EffectiveProp, ResolvedProp, TypeMember, TypeShape } from '../api'

function buildMember(m: TypeMember, category: string, types: Record<string, TypeShape>,
                     path: string, sparse: Record<string, string>, defaultsAt: DefaultValue): EffectiveProp {
  if (m.kind === 'struct') {
    const shape = types[m.struct_type]
    const members = shape && shape.kind === 'struct' ? shape.members : []
    return {
      kind: 'struct', name: m.name, category,
      members: members.map((mm) =>
        buildMember(mm, category, types, `${path}.${mm.name}`, sparse,
          (defaultsAt as Record<string, DefaultValue>)[mm.name])),
    }
  }
  if (m.kind === 'enum') {
    return { kind: 'enum', name: m.name, category, enum_type: m.enum_type,
             stored_value: sparse[path] ?? null, default_value: defaultsAt as string }
  }
  if (m.kind === 'array') {
    const shape = types[m.element_type]
    const elKind = shape?.kind === 'struct' ? 'struct' : 'enum'
    const defaults = defaultsAt as DefaultValue[]
    const elements: EffectiveProp[] = []
    for (let i = 0; i < m.array_dim; i++) {
      const elPath = `${path}.${i}`
      if (elKind === 'struct') {
        const struct: TypeMember = { kind: 'struct', name: m.name, struct_type: m.element_type }
        elements.push(buildMember(struct, category, types, elPath, sparse, defaults[i]))
      } else {
        const en: TypeMember = { kind: 'enum', name: m.name, enum_type: m.element_type }
        elements.push(buildMember(en, category, types, elPath, sparse, defaults[i]))
      }
    }
    return { kind: 'array', name: m.name, category, element_kind: elKind, elements }
  }
  // Plain scalar member, optionally an array of them (array_dim present, no shared type at all).
  if (m.array_dim !== undefined) {
    const defaults = defaultsAt as DefaultValue[]
    const elements: EffectiveProp[] = []
    for (let i = 0; i < m.array_dim; i++) {
      const elPath = `${path}.${i}`
      elements.push({ kind: m.kind, name: m.name, category,
        stored_value: sparse[elPath] ?? null, default_value: defaults[i] as string })
    }
    return { kind: 'array', name: m.name, category, element_kind: m.kind, elements }
  }
  return { kind: m.kind, name: m.name, category,
           stored_value: sparse[path] ?? null, default_value: defaultsAt as string }
}

function buildTopLevel(p: ResolvedProp, types: Record<string, TypeShape>,
                       sparse: Record<string, string>): EffectiveProp {
  if (p.kind === 'struct') {
    const shape = types[p.struct_type]
    const members = shape && shape.kind === 'struct' ? shape.members : []
    return {
      kind: 'struct', name: p.name, category: p.category,
      members: members.map((m) =>
        buildMember(m, p.category, types, `${p.name}.${m.name}`, sparse,
          (p.default_value as Record<string, DefaultValue>)[m.name])),
    }
  }
  if (p.kind === 'array') {
    const elKind: EffectiveProp['kind'] = p.element_type !== undefined
      ? (types[p.element_type]?.kind === 'struct' ? 'struct' : 'enum')
      : (p.element_kind as EffectiveProp['kind'])
    const elements: EffectiveProp[] = []
    for (let i = 0; i < p.array_dim; i++) {
      const elPath = `${p.name}.${i}`
      if (elKind === 'struct' && p.element_type !== undefined) {
        const struct: TypeMember = { kind: 'struct', name: p.name, struct_type: p.element_type }
        elements.push(buildMember(struct, p.category, types, elPath, sparse, p.default_value[i]))
      } else if (elKind === 'enum' && p.element_type !== undefined) {
        const en: TypeMember = { kind: 'enum', name: p.name, enum_type: p.element_type }
        elements.push(buildMember(en, p.category, types, elPath, sparse, p.default_value[i]))
      } else {
        elements.push({ kind: elKind, name: p.name, category: p.category,
          stored_value: sparse[elPath] ?? null, default_value: p.default_value[i] as string } as EffectiveProp)
      }
    }
    return { kind: 'array', name: p.name, category: p.category, element_kind: elKind, elements }
  }
  if (p.kind === 'enum') {
    return { kind: 'enum', name: p.name, category: p.category, enum_type: p.enum_type,
             stored_value: sparse[p.name] ?? null, default_value: p.default_value }
  }
  return { kind: p.kind, name: p.name, category: p.category,
           stored_value: sparse[p.name] ?? null, default_value: p.default_value }
}

/** The whole render walk: cr's own top-level props (already in normative order -- typed fields
 * first, then the generic schema walk, spec §1), each rendered against sparse's own stated leaves.
 * A leaf present in `sparse` renders explicit; one absent renders cr's own per-class default at the
 * same path -- never types[...]'s shape-only entry, which carries no default at all (spec's C1
 * fix). */
export function buildDisplayProps(cr: ClassResolution, sparse: Record<string, string>): EffectiveProp[] {
  return cr.class.props.map((p) => buildTopLevel(p, cr.types, sparse))
}
