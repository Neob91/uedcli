import type { EffectiveProp } from '../api'

export function shownValue(p: EffectiveProp): string | null {
  if (p.kind === 'struct' || p.kind === 'array') return null
  return p.stored_value ?? p.default_value
}

export function isExplicit(p: EffectiveProp): boolean {
  if (p.kind === 'struct') return p.members.some(isExplicit)
  if (p.kind === 'array') return p.elements.some(isExplicit)
  return p.stored_value !== null
}

export function searchMatch(p: EffectiveProp, query: string): boolean {
  return p.name.toLowerCase().includes(query.toLowerCase())
}

export function filterOverridesOnly(props: EffectiveProp[]): EffectiveProp[] {
  return props.filter(isExplicit)
}
