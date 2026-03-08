#!/usr/bin/env node
// check-freshness.js — flags docs with stale <!-- last-reviewed: --> markers
'use strict';

const fs = require('fs');
const path = require('path');

const MARKER_PATTERN = /<!--\s*last-reviewed:\s*(\d{4}-\d{2}-\d{2})\s*-->/;

function walkDocs(docsDir, ignore) {
  const results = [];
  if (!fs.existsSync(docsDir)) return results;
  const entries = fs.readdirSync(docsDir, { withFileTypes: true });
  for (const entry of entries) {
    const full = path.join(docsDir, entry.name);
    if (ignore.some(ig => full.includes(ig))) continue;
    if (entry.isDirectory()) {
      results.push(...walkDocs(full, ignore));
    } else if (entry.name.endsWith('.md')) {
      results.push(full);
    }
  }
  return results;
}

function daysSince(dateStr) {
  const then = new Date(dateStr);
  const now = new Date();
  return Math.floor((now - then) / (1000 * 60 * 60 * 24));
}

function checkFreshness(repoRoot, config) {
  const results = [];
  const warnDays = config.freshness_warn_days || 30;
  const errorDays = config.freshness_error_days || 90;
  const ignore = config.ignore_paths || ['node_modules', '.git', 'dist', 'build'];

  const docsDir = path.join(repoRoot, 'docs');
  const docFiles = walkDocs(docsDir, ignore);

  let checkedCount = 0;

  for (const filePath of docFiles) {
    const content = fs.readFileSync(filePath, 'utf8');
    const match = MARKER_PATTERN.exec(content);
    if (!match) continue; // Only check docs that opt in with the marker

    checkedCount++;
    const days = daysSince(match[1]);
    const relPath = path.relative(repoRoot, filePath);

    if (days >= errorDays) {
      results.push({
        check: 'freshness-marker',
        status: 'error',
        message: `${relPath} last-reviewed ${days} days ago (threshold: ${errorDays})`,
        detail: `Update the <!-- last-reviewed: --> marker after reviewing this doc`,
      });
    } else if (days >= warnDays) {
      results.push({
        check: 'freshness-marker',
        status: 'warn',
        message: `${relPath} last-reviewed ${days} days ago (warn threshold: ${warnDays})`,
      });
    }
  }

  if (results.length === 0) {
    results.push({
      check: 'freshness-marker',
      status: 'ok',
      message: checkedCount > 0
        ? `All ${checkedCount} freshness-tracked docs are current`
        : 'No docs with freshness markers found',
    });
  }

  return results;
}

module.exports = { checkFreshness };
