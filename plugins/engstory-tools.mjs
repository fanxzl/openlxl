import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { fileURLToPath } from 'node:url'
import { readFile, writeFile, rename, mkdir } from 'node:fs/promises'
import { dirname, join } from 'node:path'

const execFileAsync = promisify(execFile)

export const name = 'engstory-tools'
export const inject = ['tools']

function runPython(script, args, signal, fsrsRoot) {
  // PYTHONIOENCODING=utf-8：强制 Python 以 UTF-8 输出。否则被管道捕获 stdout 时
  // Python 会用 GBK(locale) 编码，中文 JSON（摘要/线索/角色）会被 Node 误解码。
  const env = { ...process.env, PYTHONPATH: fsrsRoot, PYTHONIOENCODING: 'utf-8' }
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
    description: 'Select learning targets from the FSRS learning vocabulary and open a learning batch, retrieving active continuous storyline context.',
    parameters: {
      type: 'object',
      properties: {
        count: { type: 'integer', description: 'Number of targets to select.' },
        vocab: { type: 'string', description: 'Absolute FSRS vocabulary path.' },
        state: { type: 'string', description: 'Optional batch state file path (defaults beside vocab).' },
        storyline: { type: 'string', description: 'Optional storyline state file path (defaults beside vocab).' },
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
      
      // 读取当前连载状态
      let storyline = { active: false, current_chapter: 0 }
      try {
        const slArgs = ['--vocab', args.vocab, '--action', 'get', '--json']
        if (args.storyline) slArgs.push('--storyline', args.storyline)
        const slCall = await run('storyline.py', slArgs, exec.signal)
        storyline = JSON.parse(slCall.stdout)
      } catch {
        // 容错降级
      }

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
      return {
        picked_at: picked.picked_at,
        words: picked.words,
        batch_id: batch.batch_id,
        state: batch.state,
        storyline,
      }
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
    description: 'Audit then commit a story: save only if the audit passes, record usage, update storyline continuity, and open the feedback phase.',
    parameters: {
      type: 'object',
      properties: {
        text: { type: 'string', description: 'Story text to commit.' },
        targets: { type: 'string', description: 'Comma-separated exact target keys.' },
        range: { type: 'string', description: 'Absolute range vocabulary path.' },
        vocab: { type: 'string', description: 'Absolute FSRS vocabulary path.' },
        summary: { type: 'string', description: 'One-sentence summary of this chapter for continuous recap.' },
        next_hook: { type: 'string', description: 'Ending scene/hook left for the next chapter.' },
        storiesDir: { type: 'string', description: 'Absolute stories directory (defaults beside vocab).' },
        properNames: { type: 'string', description: 'Comma-separated allowed proper nouns.' },
        state: { type: 'string', description: 'Optional batch state file path (defaults beside vocab).' },
        storyline: { type: 'string', description: 'Optional storyline state file path (defaults beside vocab).' },
        premise: { type: 'string', description: 'If user provided a new script/worldview premise, pass here to initialize a new series (Chapter 1).' },
        series_title: { type: 'string', description: 'Optional series or story title.' },
        chapter_goal: { type: 'string', description: 'This chapter goal: the concrete action the protagonist must complete.' },
        consequence: { type: 'string', description: 'This chapter consequence: the irreversible result of the protagonist choice.' },
        new_threads: { type: 'string', description: 'JSON array: newly opened unresolved threads added this chapter.' },
        resolved_threads: { type: 'string', description: 'JSON array of thread ids resolved this chapter.' },
        style_profile: { type: 'string', description: 'JSON object: user-provided story style profile (new series only).' },
        characters: { type: 'string', description: 'JSON array: main characters (new series only).' },
        open_threads: { type: 'string', description: 'JSON array: initial unresolved threads (new series only).' },
        relationship_state: { type: 'string', description: 'JSON array: relationship states (optional).' },
        obstacle: { type: 'string', description: 'This chapter obstacle.' },
        choice: { type: 'string', description: 'This chapter protagonist choice.' },
        story_arc: { type: 'string', description: 'Story arc id this chapter belongs to.' },
        scene_location: { type: 'string', description: 'Scene location of this chapter.' },
        facts_added: { type: 'string', description: 'JSON array: newly established facts this chapter.' },
        facts_confirmed: { type: 'string', description: 'JSON array: facts now confirmed this chapter.' },
        character_changes: { type: 'string', description: 'JSON array: character changes this chapter.' },
        relationship_changes: { type: 'string', description: 'JSON array: relationship changes this chapter.' },
        ledger: { type: 'string', description: 'Optional chapter-ledger jsonl path (defaults beside vocab).' },
      },
      required: ['text', 'targets', 'range', 'vocab', 'summary', 'next_hook'],
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

      // 提取 summary 与 next_hook，若模型未显式传参则从正文末尾自动兜底
      let summaryText = (args.summary || '').trim()
      let hookText = (args.next_hook || '').trim()
      if (!hookText) {
        // 从正文末尾按句号/标点提取最后 1-2 句话作为镜头钩子兜底
        const sentences = args.text.replace(/\r/g, '').split(/(?<=[.!?])\s+/).filter(Boolean)
        hookText = sentences.slice(-2).join(' ').slice(-200).trim()
      }
      if (!summaryText) {
        summaryText = hookText || '本章剧情推进。'
      }

      // 更新连载状态（storyline.json）
      let storylineResult = null
      try {
        const compactJson = (v) => (typeof v === 'string' ? v.replace(/\r?\n/g, ' ').trim() : v)
        const slArgs = ['--vocab', args.vocab, '--json']
        if (args.storyline) slArgs.push('--storyline', args.storyline)
        if (args.premise && args.premise.trim()) {
          // 开启新连载（Chapter 1）
          slArgs.push('--action', 'start', '--premise', args.premise.trim())
          if (args.series_title) slArgs.push('--title', compactJson(args.series_title))
          slArgs.push('--summary', summaryText)
          slArgs.push('--ending', hookText)
          slArgs.push('--story-file', filePath)
          if (args.style_profile) slArgs.push('--style-profile', compactJson(args.style_profile))
          if (args.characters) slArgs.push('--characters', compactJson(args.characters))
          if (args.open_threads) slArgs.push('--open-threads', compactJson(args.open_threads))
          if (args.relationship_state) slArgs.push('--relationship-state', compactJson(args.relationship_state))
        } else {
          // 推进既有连载
          slArgs.push('--action', 'advance')
          slArgs.push('--summary', summaryText)
          slArgs.push('--ending', hookText)
          slArgs.push('--story-file', filePath)
          if (args.series_title) slArgs.push('--title', compactJson(args.series_title))
        }
        // 章节戏剧结构与线索增删（start 与 advance 都支持）
        if (args.chapter_goal) slArgs.push('--chapter-goal', compactJson(args.chapter_goal))
        if (args.consequence) slArgs.push('--consequence', compactJson(args.consequence))
        if (args.new_threads) slArgs.push('--new-threads', compactJson(args.new_threads))
        if (args.resolved_threads) slArgs.push('--resolved-threads', compactJson(args.resolved_threads))
        if (args.relationship_state) slArgs.push('--relationship-state', compactJson(args.relationship_state))
        const slCall = await run('storyline.py', slArgs, exec.signal)
        storylineResult = JSON.parse(slCall.stdout)
      } catch (err) {
        // 连载更新失败不阻断核心提交流程
      }

      // 追加章节事实账本（ledger.jsonl）：只在提供了结构化字段时写入
      let ledgerResult = null
      try {
        const hasLedgerFields = args.facts_added || args.facts_confirmed || args.character_changes ||
          args.relationship_changes || args.obstacle || args.choice || args.story_arc
        if (hasLedgerFields) {
          const ch = (storylineResult && storylineResult.current_chapter) || 1
          const ledArgs = ['--action', 'append', '--vocab', args.vocab, '--chapter', String(ch), '--json']
          ledArgs.push('--summary', summaryText)
          ledArgs.push('--next-hook', hookText)
          if (args.chapter_goal) ledArgs.push('--chapter-goal', compactJson(args.chapter_goal))
          if (args.obstacle) ledArgs.push('--obstacle', compactJson(args.obstacle))
          if (args.choice) ledArgs.push('--choice', compactJson(args.choice))
          if (args.consequence) ledArgs.push('--consequence', compactJson(args.consequence))
          if (args.story_arc) ledArgs.push('--story-arc', compactJson(args.story_arc))
          if (args.scene_location) ledArgs.push('--scene-location', compactJson(args.scene_location))
          ledArgs.push('--story-file', filePath)
          if (args.facts_added) ledArgs.push('--facts-added', compactJson(args.facts_added))
          if (args.facts_confirmed) ledArgs.push('--facts-confirmed', compactJson(args.facts_confirmed))
          if (args.character_changes) ledArgs.push('--character-changes', compactJson(args.character_changes))
          if (args.relationship_changes) ledArgs.push('--relationship-changes', compactJson(args.relationship_changes))
          if (args.new_threads) ledArgs.push('--new-threads', compactJson(args.new_threads))
          if (args.resolved_threads) ledArgs.push('--resolved-threads', compactJson(args.resolved_threads))
          if (args.ledger) ledArgs.push('--ledger', args.ledger)
          const ledCall = await run('ledger.py', ledArgs, exec.signal)
          ledgerResult = JSON.parse(ledCall.stdout)
        }
      } catch (err) {
        // 账本写入失败不阻断核心提交流程
      }

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
        storyline: storylineResult,
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

  // 通用：把 JSON 字符串压缩成单行（去换行），避免 Windows 参数拆分；校验失败则返回 null
  const compactJson = (v) => {
    if (typeof v !== 'string') return v
    try { return JSON.stringify(JSON.parse(v.replace(/\r?\n/g, ' '))) } catch { return null }
  }

  ctx.tools.register({
    name: 'engstory_extract_style',
    description: 'Generate a candidate style profile from reference fragments + reader impressions. Does NOT write the official profile; returns candidates for confirmation.',
    parameters: {
      type: 'object',
      properties: {
        samples: { type: 'string', description: 'JSON array: [{id, text}] reference fragments from the same book.' },
        impressions: { type: 'string', description: 'Reader impressions in natural language (what you like / dislike).' },
      },
      required: ['samples'],
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: (_args, value) => jsonResult(value),
    },
    async execute(args, exec) {
      const samples = JSON.parse(args.samples)
      let candidates = []
      for (const s of samples) {
        const text = typeof s === 'string' ? s : s.text
        const id = typeof s === 'string' ? '' : (s.id || '')
        // 单片段占位分析：真正语义归纳交给模型，脚本只给出每片段的分析骨架字段
        candidates.push({
          sample_id: id,
          preview: (text || '').slice(0, 200),
          dimensions: { undetermined: true },
        })
      }
      const scaffold = {
        sample_ids: samples.map((s) => (typeof s === 'string' ? '' : s.id || '')),
        reader_impressions: args.impressions || '',
        per_sample_analysis: candidates,
        dimensions: ['pov', 'tone', 'pace', 'sentence_rhythm', 'dialogue', 'plot_movement', 'chapter_endings'],
        merge_guidance: '找出至少两个片段重复出现的特征；单片段偶发特征不作为稳定风格。',
        confidence_scale: { high: '多个片段一致', medium: '部分片段支持', low: '证据不足' },
      }
      return { candidate_profile: null, scaffold, note: '请基于 scaffold 由模型填充分析并产出候选风格（dimensions/must_do/avoid），确认后再用 engstory_confirm_style 落盘。' }
    },
  })

  ctx.tools.register({
    name: 'engstory_confirm_style',
    description: 'Validate and persist a confirmed style profile into style-profile.json. Safe gate: only writes after user confirmation.',
    parameters: {
      type: 'object',
      properties: {
        vocab: { type: 'string', description: 'Absolute FSRS vocabulary path (defaults style path beside it).' },
        style: { type: 'string', description: 'Absolute style-profile.json path.' },
        data: { type: 'string', description: 'JSON object: the confirmed style profile (dimensions/must_do/avoid/confidence).' },
      },
      required: ['vocab', 'data'],
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: (_args, value) => jsonResult(value),
    },
    async execute(args, exec) {
      const dataBody = compactJson(args.data)
      if (!dataBody) return { saved: false, reason: 'data 不是合法 JSON。' }
      const pyArgs = ['--action', 'save', '--vocab', args.vocab, '--data', dataBody, '--json']
      if (args.style) pyArgs.push('--style', args.style)
      const call = await run('style.py', pyArgs, exec.signal)
      const saved = JSON.parse(call.stdout)
      return { saved: true, profile: saved }
    },
  })

  ctx.tools.register({
    name: 'engstory_build_context',
    description: 'Assemble the bounded writing-context package (style + plot outline + facts + current state + targets) for this chapter.',
    parameters: {
      type: 'object',
      properties: {
        vocab: { type: 'string', description: 'Absolute FSRS vocabulary path.' },
        targets: { type: 'string', description: 'Comma-separated target keys.' },
        storyline: { type: 'string', description: 'Optional storyline state json path.' },
        outline: { type: 'string', description: 'Optional plot-outline json path.' },
        ledger: { type: 'string', description: 'Optional chapter-ledger jsonl path.' },
        style: { type: 'string', description: 'Optional style-profile.json path.' },
        chapter: { type: 'integer', description: 'Optional current chapter number (defaults from state).' },
        arc_id: { type: 'string', description: 'Optional story arc id.' },
      },
      required: ['vocab'],
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: (_args, value) => jsonResult(value),
    },
    async execute(args, exec) {
      const pyArgs = ['--vocab', args.vocab, '--json']
      if (args.targets) pyArgs.push('--targets', args.targets)
      if (args.storyline) pyArgs.push('--storyline', args.storyline)
      if (args.outline) pyArgs.push('--outline', args.outline)
      if (args.ledger) pyArgs.push('--ledger', args.ledger)
      if (args.style) pyArgs.push('--style', args.style)
      if (args.chapter) pyArgs.push('--chapter', String(args.chapter))
      if (args.arc_id) pyArgs.push('--arc-id', args.arc_id)
      const call = await run('context.py', pyArgs, exec.signal)
      return JSON.parse(call.stdout)
    },
  })
}
