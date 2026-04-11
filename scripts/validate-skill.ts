#!/usr/bin/env node
import { Command } from 'commander';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, extname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import yaml from 'js-yaml';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..');
const forbiddenFiles = new Set(['README.md', 'CHANGELOG.md', 'NOTES.md', 'IDEAS.md']);
const textExtensions = new Set(['.md', '.ts', '.js', '.json', '.yaml', '.yml', '.sh', '.txt']);
const maxSkillMdLines = 250;
const linkPattern = /\[[^\]]+\]\(([^)]+)\)/g;
const placeholderPatterns = [
  /^\s*name:\s*your-skill-name\s*$/im,
  /^\s*description:\s*Describe what this skill does/im,
  /^\s*State the capability in 1 to 2 lines\.\s*$/im,
  /^\s*- Add concrete trigger examples\s*$/im,
  /^\s*echo "Replace this with a real smoke test"\s*$/im,
];

type ValidationResult = {
  skill: string;
  errors: string[];
  warnings: string[];
};

function displayPath(path: string): string {
  const rel = relative(repoRoot, path);
  return rel === '' || (!rel.startsWith('..') && rel !== '.') ? (rel || '.') : path;
}

function listSkillDirs(dir: string): string[] {
  return readdirSync(dir)
    .map((entry) => join(dir, entry))
    .filter((entry) => statSync(entry).isDirectory() && existsSync(join(entry, 'SKILL.md')));
}

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const stats = statSync(full);
    if (stats.isDirectory()) out.push(...walk(full));
    else out.push(full);
  }
  return out;
}

function extractFrontmatter(content: string): Record<string, unknown> {
  const match = content.match(/^---\n([\s\S]*?)\n---/);
  if (!match) throw new Error('Missing or invalid frontmatter');
  const parsed = yaml.load(match[1]);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Frontmatter must be a YAML object');
  }
  return parsed as Record<string, unknown>;
}

function resolveSkillDirs(targetPath: string): string[] {
  const absolute = resolve(repoRoot, targetPath);
  if (!existsSync(absolute)) throw new Error(`Path not found: ${absolute}`);
  if (existsSync(join(absolute, 'SKILL.md'))) return [absolute];

  const skillsDir = absolute.endsWith('/skills') || absolute === join(repoRoot, 'skills')
    ? absolute
    : join(absolute, 'skills');

  if (existsSync(skillsDir)) {
    const skillDirs = listSkillDirs(skillsDir);
    if (skillDirs.length > 0) return skillDirs;
  }

  const directSkillDirs = listSkillDirs(absolute);
  if (directSkillDirs.length > 0) return directSkillDirs;

  throw new Error(`No skill directory found at: ${absolute}`);
}

function validateFrontmatter(frontmatter: Record<string, unknown>, result: ValidationResult) {
  const allowedKeys = new Set(['name', 'description']);
  const extraKeys = Object.keys(frontmatter).filter((key) => !allowedKeys.has(key));
  if (extraKeys.length > 0) result.errors.push(`Unsupported frontmatter keys: ${extraKeys.join(', ')}`);

  const name = frontmatter.name;
  if (typeof name !== 'string' || name.trim() === '') {
    result.errors.push("Frontmatter must include a non-empty 'name'");
  } else if (!/^[a-z0-9-]+$/.test(name) || name.startsWith('-') || name.endsWith('-') || name.includes('--')) {
    result.errors.push("'name' must be lowercase hyphen-case");
  }

  const description = frontmatter.description;
  if (typeof description !== 'string' || description.trim() === '') {
    result.errors.push("Frontmatter must include a non-empty 'description'");
  } else {
    if (description.length > 1024) result.errors.push('Description is too long, keep it under 1024 characters');
    const lower = description.toLowerCase();
    if (lower.includes('helps with') || lower === 'nz data skill' || lower.includes('stuff')) {
      result.warnings.push('Description looks vague, make the trigger surface more specific');
    }
  }
}

function validateLinks(skillDir: string, filePath: string, content: string, result: ValidationResult) {
  for (const match of content.matchAll(linkPattern)) {
    const target = match[1];
    if (!target || target.startsWith('http://') || target.startsWith('https://') || target.startsWith('mailto:') || target.startsWith('#')) continue;
    const resolvedTarget = resolve(dirname(filePath), target);
    if (!resolvedTarget.startsWith(resolve(skillDir))) {
      result.errors.push(`Link escapes skill root in ${relative(skillDir, filePath)}: ${target}`);
      continue;
    }
    if (!existsSync(resolvedTarget)) {
      result.errors.push(`Broken local link in ${relative(skillDir, filePath)}: ${target}`);
    }
  }
}

function validateSkill(skillDir: string): ValidationResult {
  const result: ValidationResult = {
    skill: displayPath(skillDir),
    errors: [],
    warnings: [],
  };

  const skillMdPath = join(skillDir, 'SKILL.md');
  const skillMd = readFileSync(skillMdPath, 'utf8');

  try {
    validateFrontmatter(extractFrontmatter(skillMd), result);
  } catch (error) {
    result.errors.push((error as Error).message);
  }

  if (skillMd.split(/\r?\n/).length > maxSkillMdLines) {
    result.warnings.push(`SKILL.md is long, consider splitting detail into references/ (${skillMd.split(/\r?\n/).length} lines)`);
  }

  if (existsSync(join(skillDir, 'references')) && !skillMd.includes('references/')) {
    result.warnings.push('references/ exists but SKILL.md does not mention it');
  }
  if (existsSync(join(skillDir, 'scripts')) && !skillMd.includes('scripts/')) {
    result.warnings.push('scripts/ exists but SKILL.md does not mention it');
  }

  const files = walk(skillDir);
  for (const filePath of files) {
    const relativePath = relative(skillDir, filePath);
    const base = relativePath.split('/').pop() ?? relativePath;
    if (forbiddenFiles.has(base)) {
      result.errors.push(`Forbidden clutter file: ${relativePath}`);
    }

    const ext = extname(filePath).toLowerCase();
    if (!textExtensions.has(ext) && !filePath.endsWith('SKILL.md')) continue;

    const content = readFileSync(filePath, 'utf8');
    validateLinks(skillDir, filePath, content, result);
    for (const pattern of placeholderPatterns) {
      if (pattern.test(content)) {
        result.errors.push(`Placeholder scaffold text found in ${relativePath}`);
        break;
      }
    }
  }

  return result;
}

function printHuman(results: ValidationResult[]) {
  let errorCount = 0;
  let warningCount = 0;

  for (const result of results) {
    if (result.errors.length === 0 && result.warnings.length === 0) {
      console.log(`[OK] ${result.skill}`);
      continue;
    }

    console.log(`\n${result.skill}`);
    for (const error of result.errors) {
      console.log(`  [ERROR] ${error}`);
      errorCount += 1;
    }
    for (const warning of result.warnings) {
      console.log(`  [WARN] ${warning}`);
      warningCount += 1;
    }
  }

  if (errorCount === 0 && warningCount === 0) {
    console.log('[OK] All skills passed validation with no issues.');
  } else if (errorCount === 0) {
    console.log(`\n[OK] Validation passed with ${warningCount} warning(s).`);
  }
}

const program = new Command();
program
  .name('validate-skill')
  .description('Validate one skill or all skills in the repo')
  .argument('[path]', 'skill path or repo root', 'skills')
  .option('--json', 'print machine-readable output', false)
  .option('--strict', 'treat warnings as errors', false)
  .action((targetPath: string, options: { json: boolean; strict: boolean }) => {
    try {
      const results = resolveSkillDirs(targetPath).map(validateSkill);
      if (options.strict) {
        for (const result of results) {
          result.errors.push(...result.warnings.map((warning) => `Strict mode: ${warning}`));
          result.warnings = [];
        }
      }

      if (options.json) {
        console.log(JSON.stringify(results, null, 2));
      } else {
        printHuman(results);
      }

      const hasErrors = results.some((result) => result.errors.length > 0);
      process.exit(hasErrors ? 1 : 0);
    } catch (error) {
      console.error(`[ERROR] ${(error as Error).message}`);
      process.exit(1);
    }
  });

program.parse();
