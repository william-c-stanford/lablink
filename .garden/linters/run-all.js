#!/usr/bin/env node
// run-all.js — orchestrates all linter checks, called by git hooks
'use strict';

const fs = require('fs');
const path = require('path');

const { checkClaudeMd } = require('./check-claude-md');
const { checkModuleAgents } = require('./check-module-agents');
const { checkCoverage } = require('./check-coverage');
const { checkFreshness } = require('./check-freshness');
const { checkCrossLinks } = require('./check-cross-links');

// Resolve repo root by walking up from cwd until we find .git
function findRepoRoot(startDir) {
  let dir = startDir;
  while (dir !== path.parse(dir).root) {
    if (fs.existsSync(path.join(dir, '.git'))) return dir;
    dir = path.dirname(dir);
  }
  return startDir;
}

function loadConfig(repoRoot) {
  const configPath = path.join(repoRoot, '.garden', 'config.json');
  if (!fs.existsSync(configPath)) return {};
  try {
    return JSON.parse(fs.readFileSync(configPath, 'utf8'));
  } catch {
    return {};
  }
}

function formatResult(result) {
  const icons = { ok: 'OK  ', warn: 'WARN', error: 'ERR ' };
  const icon = icons[result.status] || '    ';
  const line = `  ${icon} ${result.check.padEnd(30)} ${result.message}`;
  if (result.detail) return line + '\n' + result.detail.split('\n').map(l => '       ' + l).join('\n');
  return line;
}

function main() {
  const args = process.argv.slice(2);
  const mode = args.find(a => a.startsWith('--'))?.replace('--', '') || 'pre-commit';
  const jsonOutput = args.includes('--json');

  const repoRoot = findRepoRoot(process.cwd());
  const config = loadConfig(repoRoot);

  let allResults = [];

  // Pre-commit checks (fast, local)
  allResults.push(...checkClaudeMd(repoRoot, config));
  allResults.push(...checkModuleAgents(repoRoot, config));
  allResults.push(...checkCoverage(repoRoot, config, mode === 'pre-push' ? 'pr' : 'pre-commit'));
  allResults.push(...checkFreshness(repoRoot, config));

  // Pre-push / CI checks (slower, more thorough)
  if (mode === 'pre-push' || mode === 'ci' || mode === 'status') {
    allResults.push(...checkCrossLinks(repoRoot, config));
  }

  if (jsonOutput || mode === 'status') {
    process.stdout.write(JSON.stringify(allResults, null, 2) + '\n');
    process.exit(0);
  }

  // Human-readable output
  const errors = allResults.filter(r => r.status === 'error');
  const warnings = allResults.filter(r => r.status === 'warn');

  console.log(`\ngarden lint (${mode})`);
  for (const result of allResults) {
    console.log(formatResult(result));
  }
  console.log('');

  if (errors.length > 0 || warnings.length > 0) {
    console.log(`${errors.length} error(s), ${warnings.length} warning(s).${errors.length === 0 ? ' Warnings are non-blocking.' : ''}`);
  } else {
    console.log('All checks passed.');
  }
  console.log('');

  // Only errors block commits
  process.exit(errors.length > 0 ? 1 : 0);
}

main();
