export type CalculationReceipt = {
  id: string
  tool: 'calculate_expression' | 'translate_page_address' | 'trace_binary_search' | 'simulate_page_replacement' | 'unsupported'
  title: string
  origin: 'assistant' | 'manual'
  status: 'completed' | 'error'
  reference?: string | null
  arguments: Record<string, string>
  steps: Array<{ label: string; expression: string; result: string }>
  result: string | null
  exact_result: string | null
  error: string | null
  boundary: string
}

export const calculationFieldLabels: Record<string, string> = {
  expression: '算式',
  virtual_address: '虚拟地址',
  page_size_bytes: '页大小（字节）',
  physical_page_number: '物理页号',
  values: '有序数组', target: '目标值', algorithm: '置换算法', frames: '页框数量', references: '访问序列',
}

export function calculationsMarkdown(records: CalculationReceipt[]): string {
  if (!records.length) return ''
  return '\n\n## 工具计算回执\n\n仅按给定参数复算，不代表完整答案已核实。\n\n' + records.map(record => {
    if (record.status !== 'completed') return `### ${record.title}\n\n计算未完成，请核对参数。`
    return `### ${record.reference || '计算'} · ${record.title}\n\n` + Object.entries(record.arguments).map(([key, value]) => `- ${key}：\`${value}\``).join('\n') +
      '\n' + record.steps.map(step => `- ${step.label}：\`${step.expression}\` = \`${step.result}\``).join('\n') +
      `\n\n结果：${record.result}；精确值：${record.exact_result}。\n\n${record.boundary}`
  }).join('\n\n')
}
