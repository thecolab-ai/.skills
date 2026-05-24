#!/usr/bin/env python3
"""Validate that the README skills table is in sync with the skills/ directory."""

import os
import re
import sys


def normalize(text):
    """Trim and collapse internal whitespace for loose comparison."""
    return re.sub(r'\s+', ' ', text.strip())


def parse_frontmatter(path):
    """Return dict of key:value from the YAML frontmatter block of a file."""
    with open(path, encoding='utf-8') as f:
        content = f.read()
    if not content.startswith('---'):
        return {}
    # Find the closing ---
    end = content.find('\n---', 3)
    if end == -1:
        return {}
    block = content[3:end]
    result = {}
    for line in block.splitlines():
        if ':' in line:
            key, _, value = line.partition(':')
            result[key.strip()] = value.strip()
    return result


def collect_skills(skills_dir):
    """Walk skills/ and return {folder_name: {name, description}} for each SKILL.md."""
    skills = {}
    for entry in sorted(os.listdir(skills_dir)):
        skill_md = os.path.join(skills_dir, entry, 'SKILL.md')
        if not os.path.isfile(skill_md):
            continue
        fm = parse_frontmatter(skill_md)
        skills[entry] = {
            'name': fm.get('name', ''),
            'description': fm.get('description', ''),
            'path': skill_md,
        }
    return skills


def parse_readme_table(readme_path):
    """
    Parse the ## Available skills table from the README.
    Returns list of {folder, description} dicts.
    """
    with open(readme_path, encoding='utf-8') as f:
        lines = f.readlines()

    in_table = False
    rows = []
    for line in lines:
        stripped = line.strip()
        if re.match(r'^##\s+Available skills', stripped, re.IGNORECASE):
            in_table = True
            continue
        if in_table:
            # Stop at next heading
            if stripped.startswith('#'):
                break
            # Skip header / separator rows
            if not stripped.startswith('|') or re.match(r'^\|[-| ]+\|$', stripped):
                continue
            # Parse data row: | [name](link) | description |
            parts = [p.strip() for p in stripped.strip('|').split('|')]
            if len(parts) < 2:
                continue
            link_cell = parts[0]
            description = parts[1]
            # Extract folder name from markdown link: [text](skills/<folder>/SKILL.md)
            m = re.search(r'\(skills/([^/]+)/SKILL\.md\)', link_cell)
            if not m:
                continue
            rows.append({'folder': m.group(1), 'description': description})

    return rows


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    skills_dir = os.path.join(repo_root, 'skills')
    readme_path = os.path.join(repo_root, 'README.md')

    if not os.path.isdir(skills_dir):
        print(f'error: skills/ directory not found at {skills_dir}')
        sys.exit(1)
    if not os.path.isfile(readme_path):
        print(f'error: README.md not found at {readme_path}')
        sys.exit(1)

    skills = collect_skills(skills_dir)
    readme_rows = parse_readme_table(readme_path)

    readme_folders = {row['folder'] for row in readme_rows}

    errors = []

    # 1. Skills in skills/ with no README row
    for folder in sorted(skills):
        if folder not in readme_folders:
            errors.append(
                f'error: skill folder "{folder}" exists in skills/ but has no row in the README table'
            )

    # 2. README rows pointing to non-existent skill folders
    for row in readme_rows:
        folder = row['folder']
        if folder not in skills:
            errors.append(
                f'error: README row "{folder}" points to a skill folder that does not exist'
            )

    # 3. Description mismatch
    for row in readme_rows:
        folder = row['folder']
        if folder not in skills:
            continue  # already reported above
        skill_desc = normalize(skills[folder]['description'])
        readme_desc = normalize(row['description'])
        if skill_desc != readme_desc:
            errors.append(
                f'error: description mismatch for "{folder}"\n'
                f'  SKILL.md : {skill_desc}\n'
                f'  README   : {readme_desc}'
            )

    if errors:
        for e in errors:
            print(e)
        print(f'\n{len(errors)} problem(s) found. Fix the README table or SKILL.md files above.')
        sys.exit(1)
    else:
        print(f'OK: {len(skills)} skills checked, README table is in sync.')
        sys.exit(0)


if __name__ == '__main__':
    main()
