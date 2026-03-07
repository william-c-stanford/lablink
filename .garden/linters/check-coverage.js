#!/usr/bin/env node
// check-coverage.js — warns when source files change without any doc changes
'use strict';

const { execSync } = require('child_process');
const path = require('path');

function getStagedFiles(repoRoot) {
  try {
    const output = execSync('git diff --cached --name-only', { cwd: repoRoot, encoding: 'utf8' });
    return output.trim().split('\n').filter(Boolean);
  } catch {
    return [];
  }
}

function getPrChangedFiles(repoRoot) {
  try {
    const base = process.env.GARDEN_BASE_BRANCH || 'origin/main';
    const output = execSync(`git diff ${base}...HEAD --name-only`, { cwd: repoRoot, encoding: 'utf8' });
    return output.trim().split('\n').filter(Boolean);
  } catch {
    return [];
  }
}

function checkCoverage(repoRoot, config, mode = 'pre-commit') {
  const results = [];
  const sourceDirs = config.source_dirs || ['src', 'app', 'lib'];
  const ignore = config.ignore_paths || ['node_modules', '.git', 'dist', 'build'];

  const changedFiles = mode === 'pre-commit' ? getStagedFiles(repoRoot) : getPrChangedFiles(repoRoot);

  if (changedFiles.length === 0) {
    return [{ check: 'doc-coverage', status: 'ok', message: 'No staged files' }];
  }

  const changedSource = changedFiles.filter(f => {
    if (ignore.some(ig => f.includes(ig))) return false;
    return sourceDirs.some(d => f.startsWith(d + '/') || f.startsWith(d + '\\'));
  });

  const changedDocs = changedFiles.filter(f => {
    return f.startsWith('docs/') || f === 'CLAUDE.md' || f === 'ARCHITECTURE.md' ||
      /\/AGENTS\.md$/.test(f) || f.endsWith('.md');
  });

  if (changedSource.length > 0 && changedDocs.length === 0) {
    // Find the most likely docs to update based on source paths
    const suggestions = new Set();
    for (const f of changedSource) {
      const parts = f.split('/');
      if (parts.length >= 2) {
        suggestions.add(`${parts[0]}/${parts[1]}/CLAUDE.md`);
      }
      if (/auth|security|oauth|jwt|session/i.test(f)) suggestions.add('docs/SECURITY.md');
      if (/api|route|endpoint|controller/i.test(f)) suggestions.add('docs/DESIGN.md');
      if (/component|ui|view|page/i.test(f)) suggestions.add('docs/FRONTEND.md');
      if (/test|spec/i.test(f)) suggestions.add('docs/RELIABILITY.md');
      if (/migration|schema|model/i.test(f)) suggestions.add('docs/generated/db-schema.md');
    }

    results.push({
      check: 'doc-coverage',
      status: 'warn',
      message: `${changedSource.length} source file(s) changed, no docs updated`,
      detail: `Consider updating:\n${[...suggestions].map(s => `  → ${s}`).join('\n')}`,
    });
  } else {
    results.push({
      check: 'doc-coverage',
      status: 'ok',
      message: changedSource.length > 0
        ? `Source changes accompanied by doc changes`
        : 'No source files changed',
    });
  }

  return results;
}

module.exports = { checkCoverage };
