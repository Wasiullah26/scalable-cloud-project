import type { LanguageToolMatch } from '../api/services'

export function applyLanguageToolFixes(text: string, matches: LanguageToolMatch[]): string {
  const sorted = [...matches]
    .filter((m) => m.replacements && m.replacements.length > 0 && m.length > 0)
    .sort((a, b) => b.offset - a.offset)

  let result = text
  for (const m of sorted) {
    const rep = m.replacements![0].value
    const { offset, length } = m
    if (offset < 0 || offset + length > result.length) continue
    result = result.slice(0, offset) + rep + result.slice(offset + length)
  }
  return result
}
