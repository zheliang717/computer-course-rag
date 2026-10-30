import { spawnSync } from 'node:child_process'
import { setTimeout as delay } from 'node:timers/promises'
import { fileURLToPath } from 'node:url'

const frontendDir = fileURLToPath(new URL('../', import.meta.url))
const cli = fileURLToPath(new URL('../node_modules/@playwright/test/cli.js', import.meta.url))
const extraArgs = process.argv.slice(2)

function run(args) {
  const result = spawnSync(process.execPath, [cli, 'test', ...args], {
    cwd: frontendDir,
    stdio: 'inherit',
    windowsHide: true,
  })
  if (result.error) throw result.error
  if (result.status !== 0) process.exit(result.status ?? 1)
}

// A complete run reuses the same demo teacher across browsers. Keep each
// project's reads out of the next project's real 60-second account window.
if (extraArgs.length > 0) {
  run(extraArgs)
} else {
  const projects = ['chrome-desktop', 'edge-desktop', 'chrome-mobile']
  for (const [index, project] of projects.entries()) {
    if (index > 0) {
      process.stdout.write('等待共享演示账号的 60 秒限流窗口结束，再运行下一浏览器。\n')
      await delay(61_000)
    }
    run([`--project=${project}`])
  }
}
