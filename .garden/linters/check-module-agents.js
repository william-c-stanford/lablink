#!/usr/bin/env node
// check-module-agents.js — validates per-module CLAUDE.md presence and structure
'use strict';

const fs = require('fs');
const path = require('path');

function getFilesRecursive(dir, ignore) {
  const results = [];
  if (!fs.existsSync(dir)) return results;
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (ignore.some(ig => full.includes(ig))) continue;
    if (entry.isDirectory()) {
      results.push(...getFilesRecursive(full, ignore));
    } else {
      results.push(full);
    }
  }
  return results;
}

const REQUIRED_SECTIONS = ['## Purpose', '## Coding Conventions', '## Patterns'];

function checkModuleAgents(repoRoot, config) {
  const results = [];
  const sourceDirs = config.source_dirs || ['src', 'app', 'lib'];
  const ignore = config.ignore_paths || ['node_modules', '.git', 'dist', 'build'];
  const maxLines = config.module_md_max_lines || 150;
  const requiredAbove = config.module_md_required_above_file_count || 10;

  for (const srcDir of sourceDirs) {
    const srcPath = path.join(repoRoot, srcDir);
    if (!fs.existsSync(srcPath)) continue;

    const topLevelEntries = fs.readdirSync(srcPath, { withFileTypes: true });
    const modules = topLevelEntries.filter(e => e.isDirectory() && !ignore.includes(e.name));

    for (const mod of modules) {
      const modPath = path.join(srcPath, mod.name);
      const agentsMdPath = path.join(modPath, 'CLAUDE.md');
      const files = getFilesRecursive(modPath, ignore);
      const sourceFileCount = files.filter(f => !f.endsWith('.md')).length;

      if (!fs.existsSync(agentsMdPath)) {
        if (sourceFileCount >= requiredAbove) {
          results.push({
            check: 'module-agents-md-required',
            status: 'warn',
            message: `${srcDir}/${mod.name}/ has ${sourceFileCount} files but no CLAUDE.md`,
            detail: `Run: /garden:scaffold-module ${srcDir}/${mod.name}/`,
          });
        }
        continue;
      }

      // Validate existing CLAUDE.md
      const content = fs.readFileSync(agentsMdPath, 'utf8');
      const lines = content.split('\n');
      const lineCount = lines.filter((l, i) => i < lines.length - 1 || l.trim() !== '').length;

      if (lineCount > maxLines) {
        results.push({
          check: 'module-agents-md-length',
          status: 'error',
          message: `${srcDir}/${mod.name}/CLAUDE.md is ${lineCount} lines (max ${maxLines})`,
          detail: 'Module guides should be focused. Move detailed docs to docs/',
        });
      } else {
        results.push({
          check: 'module-agents-md-length',
          status: 'ok',
          message: `${srcDir}/${mod.name}/CLAUDE.md OK (${lineCount} lines)`,
        });
      }

      // Check required sections
      const missingSections = REQUIRED_SECTIONS.filter(s => !content.includes(s));
      if (missingSections.length > 0) {
        results.push({
          check: 'module-agents-md-structure',
          status: 'warn',
          message: `${srcDir}/${mod.name}/CLAUDE.md missing sections: ${missingSections.join(', ')}`,
        });
      }
    }
  }

  if (results.length === 0) {
    results.push({ check: 'module-agents-md', status: 'ok', message: 'No source modules found to check' });
  }

  return results;
}

module.exports = { checkModuleAgents };
