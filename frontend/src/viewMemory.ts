import { inject, type InjectionKey } from 'vue'
export type ViewMemory = { values: Map<string, unknown>; owner: () => string; page: () => string }
export const viewMemoryKey: InjectionKey<ViewMemory> = Symbol('workspace-view-memory')
export function useViewMemory() { return inject(viewMemoryKey, null) }
