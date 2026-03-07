#!/usr/bin/env node
// check-claude-md.js — validates CLAUDE.md line count and link integrity
'use strict';

const fs = require('fs');
const path = require('path');

function checkClaudeMd(repoRoot, config) {
  const results = [];
  const claudeMdPath = path.join(repoRoot, 'CLAUDE.md');

  if (!fs.existsSync(claudeMdPath)) {
    return [{ check: 'claude-md-exists', status: 'warn', message: 'CLAUDE.md not found. Run /garden:init to scaffold.' }];
  }

  const content = fs.readFileSync(claudeMdPath, 'utf8');
  const lines = content.split('\n');
  const nonEmptyLines = lines.filter((l, i) => i < lines.length - 1 || l.trim() !== '');
  const lineCount = nonEmptyLines.length;
  const maxLines = config.claude_md_max_lines || 250;

  // Check line count
  if (lineCount > maxLines) {
    results.push({
      check: 'claude-md-length',
      status: 'error',
      message: `CLAUDE.md is ${lineCount} lines (max ${maxLines}). It should be a map, not a manual.`,
      detail: `Trim to ${maxLines} lines or increase claude_md_max_lines in .garden/config.json`,
    });
  } else {
    results.push({
      check: 'claude-md-length',
      status: 'ok',
      message: `CLAUDE.md is ${lineCount} lines`,
    });
  }

  // Extract and validate all markdown links
  const linkPattern = /\[([^\]]+)\]\(([^)]+)\)/g;
  const links = [];
  let match;
  while ((match = linkPattern.exec(content)) !== null) {
    const href = match[2];
    // Skip external URLs and anchors
    if (href.startsWith('http') || href.startsWith('#') || href.startsWith('mailto:')) continue;
    // Strip anchor fragments
    const filePath = href.split('#')[0];
    if (!filePath) continue;
    links.push({ text: match[1], href: filePath });
  }

  const brokenLinks = [];
  for (const link of links) {
    const resolved = path.resolve(repoRoot, link.href);
    if (!fs.existsSync(resolved)) {
      brokenLinks.push(link);
    }
  }

  if (brokenLinks.length > 0) {
    results.push({
      check: 'claude-md-links',
      status: 'error',
      message: `CLAUDE.md has ${brokenLinks.length} broken link(s)`,
      detail: brokenLinks.map(l => `  [${l.text}](${l.href})`).join('\n'),
    });
  } else {
    results.push({
      check: 'claude-md-links',
      status: 'ok',
      message: `CLAUDE.md links OK (${links.length} checked)`,
    });
  }

  return results;
}

module.exports = { checkClaudeMd };
