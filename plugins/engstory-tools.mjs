import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { fileURLToPath } from 'node:url'
import { readFile, writeFile, rename, mkdir } from 'node:fs/promises'
import { dirname, join } from 'node:path'

const execFileAsync = promisify(execFile)

export const name = 'engstory-tools'
export const inject = ['tools']

function runPython(script, args, signal, fsrsRoot) {
  const env = { ...process.env, PYTHONPATH: fsrsRoot }
  return execFileAsync('python', [script, ...args], {
    windowsHide: true,
    signal,
    env,
    maxBuffer: 4 * 1024 * 1024,
  }).then(({ stdout, stderr }) => ({ stdout, stderr }))
}

function textResult(value) {
  return [{ type: 'text', text: value }]
}

function jsonResult(value) {
  return [{ type: 'text', text: JSON.stringify(value, null, 2) }]
}

function statePathOf(vocab, explicit) {
  return explicit || join(dirname(vocab), 'state.json')
}

async function loadState(path) {
  try {
    const parsed = JSON.parse(await readFile(path, 'utf8'))
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

async function saveState(path, data) {
  await mkdir(dirname(path), { recursive: true })
  const tmp = `${path}.tmp`
  await writeFile(tmp, JSON.stringify(data, null, 2), 'utf8')
  await rename(tmp, path)
}

function stamp() {
  return new Date().toISOString().slice(0, 19).replace('T', ' ')
}

function storyFileName(now) {
  const p = (n) => String(n).padStart(2, '0')
  return `story_${now.getFullYear()}${p(now.getMonth() + 1)}${p(now.getDate())}_${p(now.getHours())}${p(now.getMinutes())}.md`
}

export function apply(ctx) {
  const root = new URL('../skills/engstory-domain/', import.meta.url)
  const fsrsRoot = fileURLToPath(new URL('../../vendor', root))
  const script = (name) => fileURLToPath(new URL(`scripts/${name}`, root))

  const run = (name, args, signal) => runPython(script(name), args, signal, fsrsRoot)

  ctx.tools.register({
    name: 'engstory_select_targets',
    description: 'Select learning targets from the FSRS learning vocabulary and open a learning batch.',
    parameters: {
      type: 'object',
      properties: {
        count: { type: 'integer', description: 'Number of targets to select.' },
        vocab: { type: 'string', description: 'Absolute FSRS vocabulary path.' },
        state: { type: 'string', description: 'Optional batch state file path (defaults beside vocab).' },
      },
      required: ['vocab'],
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: (_args, value) => jsonResult(value),
    },
    async execute(args, exec) {
      const call = await run('pick.py', ['--count', String(args.count ?? 7), '--vocab', args.vocab, '--json'], exec.signal)
      const picked = JSON.parse(call.stdout)
      const statePath = statePathOf(args.vocab, args.state)
      const now = stamp()
      const batch = {
        batch_id: `b${Date.now()}`,
        state: 'TARGETS_SELECTED',
        targets: picked.words.map((w) => ({ key: w.key, word: w.word, gloss: w.gloss, score: w.score })),
        story_path: null,
        audit: null,
        discovered_words: [],
        created_at: now,
        updated_at: now,
      }
      await saveState(statePath, batch)
      return { picked_at: picked.picked_at, words: picked.words, batch_id: batch.batch_id, state: batch.state }
    },
  })

  ctx.tools.register({
    name: 'engstory_prepare_story_vocab',
    description: 'Build the allowed vocabulary package for this story round from the range vocabulary.',
    parameters: {
      type: 'object',
      properties: {
        targets: { type: 'string', description: 'Comma-separated exact target keys.' },
        range: { type: 'string', description: 'Absolute range vocabulary path.' },
        vocab: { type: 'string', description: 'Absolute FSRS vocabulary path.' },
        properNames: { type: 'string', description: 'Comma-separated allowed proper nouns.' },
      },
      required: ['targets', 'range'],
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: (_args, value) => jsonResult(value),
    },
    async execute(args, exec) {
      const pyArgs = ['--targets', args.targets, '--range', args.range, '--json']
      if (args.vocab) pyArgs.push('--vocab', args.vocab)
      if (args.properNames) pyArgs.push('--proper-names', args.properNames)
      const call = await run('vocab_distill.py', pyArgs, exec.signal)
      return JSON.parse(call.stdout)
    },
  })

  ctx.tools.register({
    name: 'engstory_audit_story',
    description: 'Audit a story text: every target word present, ordinary words within the allowed range.',
    parameters: {
      type: 'object',
      properties: {
        text: { type: 'string', description: 'Story text to audit.' },
        targets: { type: 'string', description: 'Comma-separated exact target keys.' },
        range: { type: 'string', description: 'Absolute range vocabulary path.' },
        properNames: { type: 'string', description: 'Comma-separated allowed proper nouns.' },
      },
      required: ['text', 'targets', 'range'],
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: (_args, value) => jsonResult(value),
    },
    async execute(args, exec) {
      const pyArgs = ['--text', args.text, '--targets', args.targets, '--range', args.range, '--json']
      if (args.properNames) pyArgs.push('--proper-names', args.properNames)
      const call = await run('story_audit.py', pyArgs, exec.signal)
      return JSON.parse(call.stdout)
    },
  })

  ctx.tools.register({
    name: 'engstory_commit_story',
    description: 'Audit then commit a story: save only if the audit passes, record usage, open the feedback phase.',
    parameters: {
      type: 'object',
      properties: {
        text: { type: 'string', description: 'Story text to commit.' },
        targets: { type: 'string', description: 'Comma-separated exact target keys.' },
        range: { type: 'string', description: 'Absolute range vocabulary path.' },
        vocab: { type: 'string', description: 'Absolute FSRS vocabulary path.' },
        storiesDir: { type: 'string', description: 'Absolute stories directory (defaults beside vocab).' },
        properNames: { type: 'string', description: 'Comma-separated allowed proper nouns.' },
        state: { type: 'string', description: 'Optional batch state file path (defaults beside vocab).' },
      },
      required: ['text', 'targets', 'range', 'vocab'],
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: (_args, value) => jsonResult(value),
    },
    async execute(args, exec) {
      const auditArgs = ['--text', args.text, '--targets', args.targets, '--range', args.range, '--json']
      if (args.properNames) auditArgs.push('--proper-names', args.properNames)
      const auditCall = await run('story_audit.py', auditArgs, exec.signal)
      const audit = JSON.parse(auditCall.stdout)
      if (!audit.pass) {
        return { committed: false, audit }
      }
      const statePath = statePathOf(args.vocab, args.state)
      const state = await loadState(statePath)
      const storiesDir = args.storiesDir || join(dirname(args.vocab), 'stories')
      const now = new Date()
      const filePath = join(storiesDir, storyFileName(now))
      await mkdir(storiesDir, { recursive: true })
      await writeFile(filePath, args.text, 'utf8')

      const markCall = await run('mark.py', ['--file', filePath, '--words', args.targets, '--vocab', args.vocab], exec.signal)

      const next = {
        batch_id: state.batch_id || `b${Date.now()}`,
        state: 'WAITING_FEEDBACK',
        targets: state.targets || [],
        story_path: filePath,
        audit,
        discovered_words: audit.out_of_range || [],
        created_at: state.created_at || stamp(),
        updated_at: stamp(),
      }
      await saveState(statePath, next)
      return {
        committed: true,
        story_path: filePath,
        audit,
        mark_report: markCall.stdout.trim() || markCall.stderr.trim(),
        state: next.state,
      }
    },
  })

  ctx.tools.register({
    name: 'engstory_apply_feedback',
    description: 'Apply explicit user ratings to the FSRS learning vocabulary; only valid after a committed story.',
    parameters: {
      type: 'object',
      properties: {
        words: { type: 'string', description: 'Comma-separated exact keys and ratings.' },
        vocab: { type: 'string', description: 'Absolute FSRS vocabulary path.' },
        state: { type: 'string', description: 'Optional batch state file path (defaults beside vocab).' },
      },
      required: ['words', 'vocab'],
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: (_args, value) => jsonResult(value),
    },
    async execute(args, exec) {
      const statePath = statePathOf(args.vocab, args.state)
      const state = await loadState(statePath)
      if (state.state !== 'WAITING_FEEDBACK') {
        return { applied: false, reason: '没有等待反馈的故事批次；请先写并提交故事。', state: state.state || 'IDLE' }
      }
      const call = await run('feedback.py', ['--words', args.words, '--vocab', args.vocab], exec.signal)
      const report = call.stdout.trim() || call.stderr.trim()
      const discovered = state.discovered_words || []
      const nextState = discovered.length > 0 ? 'WAITING_WORD_CONFIRMATION' : 'IDLE'
      const next = {
        ...state,
        state: nextState,
        updated_at: stamp(),
      }
      await saveState(statePath, next)
      return { applied: true, report, state: nextState, discovered_words: discovered }
    },
  })

  ctx.tools.register({
    name: 'engstory_write_learning_words',
    description: 'Write user-confirmed words into the FSRS learning vocabulary.',
    parameters: {
      type: 'object',
      properties: {
        words: { type: 'string', description: 'Comma-separated words and glosses.' },
        vocab: { type: 'string', description: 'Absolute FSRS vocabulary path.' },
        source: {
          type: 'string',
          enum: ['user', 'story-discovery'],
          description: 'user = direct user import; story-discovery = confirming words found in a story audit.',
        },
        state: { type: 'string', description: 'Optional batch state file path (defaults beside vocab).' },
      },
      required: ['words', 'vocab', 'source'],
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: (_args, value) => jsonResult(value),
    },
    async execute(args, exec) {
      const statePath = statePathOf(args.vocab, args.state)
      const state = await loadState(statePath)
      const requested = args.words.split(',').map((s) => s.trim().toLowerCase()).filter(Boolean)
      if (args.source === 'story-discovery') {
        if (state.state !== 'WAITING_WORD_CONFIRMATION') {
          return { applied: false, reason: '没有待确认的发现词批次；用户尚未通过故事流程确认这些词。', state: state.state || 'IDLE' }
        }
        const discovered = (state.discovered_words || []).map((w) => w.toLowerCase())
        const matched = requested.filter((w) => discovered.some((d) => d === w || d.startsWith(`${w}|`) || w.startsWith(`${d}|`)))
        if (matched.length === 0) {
          return { applied: false, reason: '请求的词不在本批次待确认的发现词列表中。', discovered_words: state.discovered_words }
        }
      }
      const call = await run('add.py', ['--words', args.words, '--vocab', args.vocab], exec.signal)
      const report = call.stdout.trim() || call.stderr.trim()
      if (args.source === 'story-discovery') {
        const remaining = (state.discovered_words || []).filter((w) => {
          const wl = w.toLowerCase()
          return !requested.some((r) => r === wl || wl.startsWith(`${r}|`) || r.startsWith(`${wl}|`))
        })
        const next = {
          ...state,
          discovered_words: remaining,
          state: remaining.length > 0 ? 'WAITING_WORD_CONFIRMATION' : 'IDLE',
          updated_at: stamp(),
        }
        await saveState(statePath, next)
        return { applied: true, report, state: next.state, discovered_words: remaining }
      }
      return { applied: true, report, state: state.state || 'IDLE' }
    },
  })
}
