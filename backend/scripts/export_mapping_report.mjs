import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const dataDir = path.join(root, 'data');
const exportDir = path.join(dataDir, 'exports');
const learnedMappingsPath = path.join(dataDir, 'learned_mappings.json');
const trainingLogPath = path.join(dataDir, 'mapping_training_log.jsonl');

const STOP_PHRASES = new Set([
  '想看','想要','有没有','给我','帮我','这个','那个','左右','预算','价格','推荐','一条','一个','可以','比较','送给','给他','给她','自己'
]);

const CATEGORY_HINTS = ['链','镯','吊','串','环','戒','耳','饰','绳','圈'];
const GIFT_TARGET_HINTS = ['男','女','妈妈','爸爸','闺蜜','姐姐','妹妹','自己','对象','老公','老婆'];
const LUXURY_STYLE_HINTS = ['贵','档次','体面','大牌','轻奢','高级','气质','优雅','复古','法式','中式','小众','百搭','精致'];
const MATERIAL_HINTS = ['金','银','玉','翠','珠','宝石','蜜蜡','玛瑙','和田玉','翡翠'];

function readJson(filePath, fallback) {
  if (!fs.existsSync(filePath)) return fallback;
  try { return JSON.parse(fs.readFileSync(filePath, 'utf8')); } catch { return fallback; }
}

function loadLearnedMappings() {
  const payload = readJson(learnedMappingsPath, {});
  return Array.isArray(payload.mappings) ? payload.mappings : [];
}

function loadTrainingExamples() {
  if (!fs.existsSync(trainingLogPath)) return [];
  const lines = fs.readFileSync(trainingLogPath, 'utf8').split(/\r?\n/).filter(Boolean);
  const out = [];
  for (const line of lines) {
    try { out.push(JSON.parse(line)); } catch {}
  }
  return out;
}

function normalizeText(text) {
  return (text || '')
    .normalize('NFKC')
    .replace(/\ufeff|\u200b/g, '')
    .replace(/\xa0/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function knownPhrases(mappings) {
  const set = new Set();
  for (const item of mappings) {
    if (item?.phrase) set.add(item.phrase);
    if (item?.canonical_value) set.add(item.canonical_value);
  }
  return set;
}

function extractCandidateNgrams(text) {
  const normalized = normalizeText(text);
  const chunks = normalized.match(/[\u4e00-\u9fff]{2,16}/g) || [];
  const candidates = [];
  for (const chunk of chunks) {
    const upper = Math.min(6, chunk.length);
    for (let size = 2; size <= upper; size++) {
      for (let start = 0; start <= chunk.length - size; start++) {
        const cand = chunk.slice(start, start + size);
        if (!STOP_PHRASES.has(cand)) candidates.push(cand);
      }
    }
  }
  return candidates;
}

function classifyCandidatePhrase(phrase) {
  if (CATEGORY_HINTS.some((t) => phrase.includes(t))) return 'category';
  if (GIFT_TARGET_HINTS.some((t) => phrase.includes(t))) return 'gift_target';
  if (MATERIAL_HINTS.some((t) => phrase.includes(t))) return 'material';
  if (LUXURY_STYLE_HINTS.some((t) => phrase.includes(t))) return 'luxury_or_style';
  return 'other';
}

function buildReport() {
  const mappings = loadLearnedMappings();
  const examples = loadTrainingExamples();
  const known = knownPhrases(mappings);

  const recentExamples = examples.slice(-100);
  const counter = new Map();
  const phraseExamples = new Map();

  for (const ex of recentExamples) {
    const extracted = ex?.extracted_conditions || {};
    if (extracted.category || extracted.gift_target || extracted.luxury_intent || extracted.style_preferences) continue;
    const text = ex?.text || '';
    for (const candidate of extractCandidateNgrams(text)) {
      if (known.has(candidate) || STOP_PHRASES.has(candidate)) continue;
      counter.set(candidate, (counter.get(candidate) || 0) + 1);
      const bucket = phraseExamples.get(candidate) || [];
      if (bucket.length < 3 && !bucket.includes(text)) bucket.push(text);
      phraseExamples.set(candidate, bucket);
    }
  }

  const candidatePhrases = [...counter.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 50)
    .filter(([, count]) => count >= 2)
    .map(([phrase, count]) => ({
      phrase,
      count,
      group: classifyCandidatePhrase(phrase),
      examples: phraseExamples.get(phrase) || []
    }));

  const grouped = {
    category: [],
    gift_target: [],
    luxury_or_style: [],
    material: [],
    other: []
  };
  for (const item of candidatePhrases) grouped[item.group].push(item);

  const now = new Date();
  const date = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(now);

  return {
    generated_at: now.toISOString(),
    date,
    stats: {
      learned_mapping_count: mappings.length,
      training_example_count: examples.length,
      candidate_phrase_count: candidatePhrases.length
    },
    learned_mappings: mappings,
    recent_examples: examples.slice(-20),
    candidate_phrases: candidatePhrases,
    grouped_candidate_phrases: grouped
  };
}

function writeOutputs(report) {
  fs.mkdirSync(exportDir, { recursive: true });
  const jsonPath = path.join(exportDir, `mapping-report-${report.date}.json`);
  const mdPath = path.join(exportDir, `mapping-report-${report.date}.md`);

  fs.writeFileSync(jsonPath, JSON.stringify(report, null, 2), 'utf8');

  const labels = {
    category: 'Category Candidates',
    gift_target: 'Gift Target Candidates',
    luxury_or_style: 'Luxury/Style Candidates',
    material: 'Material Candidates',
    other: 'Other Candidates'
  };

  const lines = [
    `# Mapping Report ${report.date}`,
    '',
    '## Overview',
    `- Learned mappings: ${report.stats.learned_mapping_count}`,
    `- Training examples: ${report.stats.training_example_count}`,
    `- Repeated unmapped candidates: ${report.stats.candidate_phrase_count}`,
    '',
    '## Learned Mappings'
  ];

  if (report.learned_mappings.length) {
    for (const m of report.learned_mappings) {
      lines.push(`- \`${m.mapping_type}\`: \`${m.phrase}\` -> \`${m.canonical_value}\``);
    }
  } else {
    lines.push('- None');
  }

  lines.push('', '## Repeated Unmapped Candidate Phrases');
  if (report.candidate_phrases.length) {
    for (const key of ['category', 'gift_target', 'luxury_or_style', 'material', 'other']) {
      lines.push('', `### ${labels[key]}`);
      const items = report.grouped_candidate_phrases[key];
      if (!items.length) {
        lines.push('- None');
        continue;
      }
      for (const item of items) {
        const example = item.examples?.[0] ? ` | example: ${item.examples[0]}` : '';
        lines.push(`- \`${item.phrase}\`: ${item.count}${example}`);
      }
    }
  } else {
    lines.push('- None');
  }

  lines.push('', '## Recent Mapping-Training Examples');
  if (report.recent_examples.length) {
    for (const ex of report.recent_examples.slice(-10)) lines.push(`- \`${ex.text || ''}\``);
  } else {
    lines.push('- None');
  }

  fs.writeFileSync(mdPath, lines.join('\n') + '\n', 'utf8');
  return { jsonPath, mdPath };
}

const report = buildReport();
const { jsonPath, mdPath } = writeOutputs(report);
process.stdout.write(JSON.stringify({ json: jsonPath, markdown: mdPath }, null, 2));
